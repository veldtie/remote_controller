import importlib.util
import subprocess
import sys
from dataclasses import dataclass
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
            self._persist_team_id_file()
            output = str(self.options.output_dir / f"{self.options.output_name}.exe")
            self.finished.emit(True, output, "")
        else:
            self.finished.emit(False, "", "failed")

    def _persist_team_id_file(self) -> None:
        team_id = (self.options.team_id or "").strip()
        output_dir = self.options.output_dir
        if self.options.mode == "onedir":
            output_dir = output_dir / self.options.output_name
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.log_line.emit("Failed to prepare the team id directory.")
            return
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


class CompilerPage(QtWidgets.QWidget):
    def __init__(self, i18n: I18n, settings: SettingsStore, logger: EventLogger):
        super().__init__()
        self.i18n = i18n
        self.settings = settings
        self.logger = logger
        self.worker: Optional[BuilderWorker] = None

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

        self.team_id_label = QtWidgets.QLabel()
        self.team_id_input = QtWidgets.QLineEdit()

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
        form_layout.addWidget(self.team_id_label, 3, 0)
        form_layout.addWidget(self.team_id_input, 3, 1, 1, 2)
        form_layout.addWidget(self.output_dir_label, 4, 0)
        form_layout.addWidget(self.output_dir_input, 4, 1)
        form_layout.addWidget(self.output_dir_button, 4, 2)
        form_layout.addWidget(self.icon_label, 5, 0)
        form_layout.addWidget(self.icon_input, 5, 1)
        form_layout.addWidget(self.icon_button, 5, 2)
        form_layout.addWidget(self.mode_label, 6, 0)
        form_layout.addWidget(self.mode_combo, 6, 1)
        form_layout.addWidget(self.console_check, 6, 2)

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

    def load_state(self) -> None:
        builder = self.settings.get("builder", {})
        self.source_input.setText(builder.get("source_dir", ""))
        self.entry_input.setText(builder.get("entrypoint", ""))
        self.output_name_input.setText(builder.get("output_name", "RemoteControllerClient"))
        self.team_id_input.setText(builder.get("team_id", ""))
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
        self.team_id_label.setText(self.i18n.t("compiler_team_id"))
        self.team_id_input.setPlaceholderText(self.i18n.t("compiler_team_placeholder"))
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
        team_id = self.team_id_input.text().strip()
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

    def persist_builder_state(self, options: BuildOptions) -> None:
        self.settings.set(
            "builder",
            {
                "source_dir": str(options.source_dir),
                "entrypoint": str(options.entrypoint),
                "output_name": options.output_name,
                "team_id": options.team_id,
                "output_dir": str(options.output_dir),
                "icon_path": str(options.icon_path) if options.icon_path else "",
                "mode": options.mode,
                "console": options.console,
            },
        )
        self.settings.save()
