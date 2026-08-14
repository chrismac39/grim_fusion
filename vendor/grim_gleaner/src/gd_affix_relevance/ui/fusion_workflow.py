"""UI workflow wrapper for grim_fusion CLI actions."""

from __future__ import annotations

from dataclasses import dataclass
import re
import tempfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QProcess, QSettings, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.profile_store import save_profile
from gd_affix_relevance.ui.settings import (
    GAME_FOLDER_SETTING,
    GRIM_FUSION_ROOT_SETTING,
    NPM_COMMAND_SETTING,
    sanitize_path,
)

ITEMS_PATH_SETTING = "fusion/items_path"
PALETTE_PATH_SETTING = "fusion/palette_path"
PLAN_NAME_SETTING = "fusion/plan_name"
FORCE_APPLY_SETTING = "fusion/force_apply"
USE_DEFAULT_PALETTE_SETTING = "fusion/use_default_palette"
LAST_ACTIVE_PROFILE_PATH_SETTING = "profiles/active_path"


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    label: str
    pattern: re.Pattern[str] | None = None


class FusionWorkflowPage(QWidget):
    """Run grim_fusion npm workflows without leaving the Gleaner UI."""

    def __init__(
        self,
        profile: BuildProfile,
        *,
        settings: QSettings | None = None,
        open_profile_page: Callable[[], None] | None = None,
        open_export_page: Callable[[], None] | None = None,
        open_settings_page: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self.settings = settings
        self.open_profile_page = open_profile_page
        self.open_export_page = open_export_page
        self.open_settings_page = open_settings_page
        self._process: QProcess | None = None
        self._temp_profile_path: Path | None = None
        self._active_steps: tuple[WorkflowStep, ...] = ()
        self._completed_step_count = 0
        self._stop_requested = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        heading = QLabel("Fusion Workflow", self)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)

        hint = QLabel(
            "Run grim_fusion generation and apply flows directly in the UI. "
            "This replaces terminal-driven npm commands for normal usage.",
            self,
        )
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()

        self.grim_dawn_path_edit = QLineEdit(self._game_folder_value(), self)
        self.grim_dawn_path_edit.setObjectName("outputPath")
        self.grim_dawn_path_edit.setPlaceholderText(
            r"Example: C:\Program Files (x86)\Steam\steamapps\common\Grim Dawn"
        )
        self.grim_dawn_path_edit.editingFinished.connect(
            self._save_game_folder_value
        )
        game_row = QWidget(self)
        game_layout = QHBoxLayout(game_row)
        game_layout.setContentsMargins(0, 0, 0, 0)
        game_layout.setSpacing(8)
        game_layout.addWidget(self.grim_dawn_path_edit, 1)
        self.browse_game_button = QPushButton("Browse...", game_row)
        self.browse_game_button.setObjectName("profileAction")
        self.browse_game_button.clicked.connect(self._browse_game_folder)
        game_layout.addWidget(self.browse_game_button)
        form.addRow("Grim Dawn folder", game_row)

        self.items_path_edit = QLineEdit(self._saved_items_path(), self)
        self.items_path_edit.setObjectName("outputPath")
        self.items_path_edit.editingFinished.connect(self._save_items_path)
        items_row = QWidget(self)
        items_layout = QHBoxLayout(items_row)
        items_layout.setContentsMargins(0, 0, 0, 0)
        items_layout.setSpacing(8)
        items_layout.addWidget(self.items_path_edit, 1)
        self.browse_items_button = QPushButton("Browse...", items_row)
        self.browse_items_button.setObjectName("profileAction")
        self.browse_items_button.clicked.connect(self._browse_items_path)
        items_layout.addWidget(self.browse_items_button)
        form.addRow("Items JSON", items_row)

        self.use_default_palette = QCheckBox("Use default gdse palette", self)
        self.use_default_palette.setChecked(self._saved_use_default_palette())
        self.use_default_palette.toggled.connect(self._palette_mode_changed)
        form.addRow("Palette mode", self.use_default_palette)

        self.palette_path_edit = QLineEdit(self._saved_palette_path(), self)
        self.palette_path_edit.setObjectName("outputPath")
        self.palette_path_edit.editingFinished.connect(self._save_palette_path)
        palette_row = QWidget(self)
        palette_layout = QHBoxLayout(palette_row)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(8)
        palette_layout.addWidget(self.palette_path_edit, 1)
        self.browse_palette_button = QPushButton("Browse...", palette_row)
        self.browse_palette_button.setObjectName("profileAction")
        self.browse_palette_button.clicked.connect(self._browse_palette_path)
        palette_layout.addWidget(self.browse_palette_button)
        form.addRow("Custom palette", palette_row)

        self.plan_name_edit = QLineEdit(self._saved_plan_name(), self)
        self.plan_name_edit.setObjectName("outputPath")
        self.plan_name_edit.setPlaceholderText("Example: Cold Wereraven")
        self.plan_name_edit.editingFinished.connect(self._save_plan_name)
        form.addRow("Plan name", self.plan_name_edit)

        self.output_path_edit = QLineEdit(self._saved_output_path(), self)
        self.output_path_edit.setObjectName("outputPath")
        self.output_path_edit.setPlaceholderText("Optional: path for generated JSON output")
        self.output_path_edit.editingFinished.connect(self._save_output_path)
        output_row = QWidget(self)
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        output_layout.addWidget(self.output_path_edit, 1)
        self.browse_output_button = QPushButton("Browse...", output_row)
        self.browse_output_button.setObjectName("profileAction")
        self.browse_output_button.clicked.connect(self._browse_output_path)
        output_layout.addWidget(self.browse_output_button)
        form.addRow("Output JSON", output_row)

        self.force_apply = QCheckBox(
            "Force apply even when generated hash matches last run",
            self,
        )
        self.force_apply.setChecked(self._saved_force_apply())
        self.force_apply.toggled.connect(self._save_force_apply)
        form.addRow("Apply mode", self.force_apply)

        layout.addLayout(form)

        actions = QHBoxLayout()
        self.generate_button = QPushButton("Generate Output", self)
        self.generate_button.setObjectName("primaryAction")
        self.generate_button.clicked.connect(self._run_generate_output)
        actions.addWidget(self.generate_button)

        self.apply_active_button = QPushButton("Apply Active Profile", self)
        self.apply_active_button.setObjectName("profileAction")
        self.apply_active_button.clicked.connect(self._run_apply_active_profile)
        actions.addWidget(self.apply_active_button)

        self.apply_plan_button = QPushButton("Apply Saved Plan", self)
        self.apply_plan_button.setObjectName("profileAction")
        self.apply_plan_button.clicked.connect(self._run_apply_saved_plan)
        actions.addWidget(self.apply_plan_button)

        self.stop_button = QPushButton("Stop", self)
        self.stop_button.setObjectName("profileAction")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_process)
        actions.addWidget(self.stop_button)
        actions.addStretch()
        layout.addLayout(actions)

        page_actions = QHBoxLayout()
        self.open_profile_button = QPushButton("Profile", self)
        self.open_profile_button.setObjectName("profileAction")
        self.open_profile_button.clicked.connect(self._open_profile_page)
        page_actions.addWidget(self.open_profile_button)
        self.open_export_button = QPushButton("Export", self)
        self.open_export_button.setObjectName("profileAction")
        self.open_export_button.clicked.connect(self._open_export_page)
        page_actions.addWidget(self.open_export_button)
        self.open_settings_button = QPushButton("Settings", self)
        self.open_settings_button.setObjectName("profileAction")
        self.open_settings_button.clicked.connect(self._open_settings_page)
        page_actions.addWidget(self.open_settings_button)
        page_actions.addStretch()
        layout.addLayout(page_actions)

        self.status = QLabel(self)
        self.status.setObjectName("pageHint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.step_status = QLabel(self)
        self.step_status.setObjectName("pageHint")
        self.step_status.setWordWrap(True)
        layout.addWidget(self.step_status)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.backend_task = QLabel("Backend orchestration: idle", self)
        self.backend_task.setObjectName("pageHint")
        self.backend_task.setWordWrap(True)
        layout.addWidget(self.backend_task)

        self.log_output = QPlainTextEdit(self)
        self.log_output.setObjectName("outputPreview")
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(220)
        layout.addWidget(self.log_output, 1)

        self._palette_mode_changed(self.use_default_palette.isChecked())
        self._refresh_status()

    def _default_output_path(self) -> str:
        root = self._grim_fusion_root_value()
        if not root:
            return ""
        return str(Path(root) / "artifacts" / "fusion-output.ui.json")

    def _workflow_steps_for(self, mode: str) -> tuple[WorkflowStep, ...]:
        if mode == "generate":
            return (
                WorkflowStep("Validating inputs"),
                WorkflowStep("Preparing active profile snapshot"),
                WorkflowStep("Scoring and composing output", re.compile(r"Scored .* items", re.IGNORECASE)),
                WorkflowStep("Writing output JSON", re.compile(r"Wrote fusion output", re.IGNORECASE)),
                WorkflowStep("Done"),
            )
        if mode == "apply-active":
            return (
                WorkflowStep("Validating inputs"),
                WorkflowStep("Preparing active profile snapshot"),
                WorkflowStep("Generating fusion output", re.compile(r"Wrote fusion output", re.IGNORECASE)),
                WorkflowStep("Applying generated text", re.compile(r"Applied generated text|No localization changes", re.IGNORECASE)),
                WorkflowStep("Saving plan metadata"),
                WorkflowStep("Done"),
            )
        return (
            WorkflowStep("Validating saved plan"),
            WorkflowStep("Loading plan"),
            WorkflowStep("Applying generated text", re.compile(r"Applied generated text|No localization changes", re.IGNORECASE)),
            WorkflowStep("Done"),
        )

    def _set_active_steps(self, steps: tuple[WorkflowStep, ...]) -> None:
        self._active_steps = steps
        self._completed_step_count = 0
        total = max(1, len(steps))
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self._refresh_step_status()

    def _advance_step(self) -> None:
        if self._completed_step_count >= len(self._active_steps):
            return
        self._completed_step_count += 1
        self.progress.setValue(self._completed_step_count)
        self._refresh_step_status()

    def _refresh_step_status(self) -> None:
        if not self._active_steps:
            self.step_status.setText("Workflow steps: none")
            return
        completed = self._completed_step_count
        total = len(self._active_steps)
        current = (
            self._active_steps[min(completed, total - 1)].label
            if completed < total
            else self._active_steps[-1].label
        )
        self.step_status.setText(
            f"Step progress: {completed}/{total}. Current: {current}."
        )

    def _scan_step_progress(self, text: str) -> None:
        if not self._active_steps:
            return
        for index in range(self._completed_step_count, len(self._active_steps)):
            pattern = self._active_steps[index].pattern
            if pattern is None:
                continue
            if pattern.search(text):
                self._completed_step_count = index + 1
                self.progress.setValue(self._completed_step_count)
        self._refresh_step_status()

    def _run_generate_output(self) -> None:
        invalid_reason = self._validate_common_inputs(require_palette=not self.use_default_palette.isChecked())
        if invalid_reason:
            QMessageBox.warning(self, "Cannot Run Fusion Workflow", invalid_reason)
            return

        output_path = self.output_path_edit.text().strip() or self._default_output_path()
        self.output_path_edit.setText(output_path)
        args = [
            "run",
            "dev",
            "--",
            "run",
            "--profile",
            str(self._write_temp_profile()),
            "--items",
            self.items_path_edit.text().strip(),
            "--grim-dawn-path",
            self.grim_dawn_path_edit.text().strip(),
            "--out",
            output_path,
        ]
        palette_path = self.palette_path_edit.text().strip()
        if not self.use_default_palette.isChecked() and palette_path:
            args.extend(["--palette", palette_path])

        self._start_process(
            args,
            "Generating fusion output JSON...",
            mode="generate",
            task="grim_fusion run",
        )

    def refresh_game_folder(self, game_folder: str = "") -> None:
        configured = sanitize_path(game_folder)
        if configured:
            self.grim_dawn_path_edit.setText(configured)
            self._save_game_folder_value()
            return

        saved = self._game_folder_value()
        self.grim_dawn_path_edit.setText(saved)
        self._refresh_status()

    def refresh_profile_path(self, profile_path: object) -> None:
        if self.settings is None:
            return
        if profile_path is None:
            self.settings.remove(LAST_ACTIVE_PROFILE_PATH_SETTING)
        else:
            self.settings.setValue(
                LAST_ACTIVE_PROFILE_PATH_SETTING,
                str(Path(profile_path).resolve()),
            )
        self.settings.sync()

    def _run_apply_active_profile(self) -> None:
        invalid_reason = self._validate_common_inputs(require_palette=not self.use_default_palette.isChecked())
        if invalid_reason:
            QMessageBox.warning(self, "Cannot Run Fusion Workflow", invalid_reason)
            return

        plan_name = self.plan_name_edit.text().strip()
        if not plan_name:
            QMessageBox.warning(
                self,
                "Cannot Run Fusion Workflow",
                "Enter a plan name before applying the active profile.",
            )
            return

        temp_profile_path = self._write_temp_profile()
        args = [
            "run",
            "dev",
            "--",
            "run-with-gleaner",
            "--no-launch",
            "--save-plan",
            "--plan-name",
            plan_name,
            "--profile",
            str(temp_profile_path),
            "--items",
            self.items_path_edit.text().strip(),
            "--grim-dawn-path",
            self.grim_dawn_path_edit.text().strip(),
        ]
        palette_path = self.palette_path_edit.text().strip()
        if not self.use_default_palette.isChecked() and palette_path:
            args.extend(["--palette", palette_path])
        if self.force_apply.isChecked():
            args.append("--force-apply")

        self._start_process(
            args,
            f"Applying active profile using plan '{plan_name}'...",
            mode="apply-active",
            task="grim_fusion run-with-gleaner",
        )

    def _run_apply_saved_plan(self) -> None:
        root = self._grim_fusion_root_value()
        npm_command = self._npm_command_value()
        if not root:
            QMessageBox.warning(
                self,
                "Cannot Run Fusion Workflow",
                "Set grim_fusion repo root in Settings first.",
            )
            return
        if not npm_command:
            QMessageBox.warning(
                self,
                "Cannot Run Fusion Workflow",
                "Set npm command in Settings first.",
            )
            return

        plan_name = self.plan_name_edit.text().strip()
        if not plan_name:
            QMessageBox.warning(
                self,
                "Cannot Run Fusion Workflow",
                "Enter a plan name before applying a saved plan.",
            )
            return

        args = ["run", "dev", "--", "apply-plan", "--plan-name", plan_name]
        if self.force_apply.isChecked():
            args.append("--force-apply")

        self._start_process(
            args,
            f"Applying saved plan '{plan_name}'...",
            mode="apply-plan",
            task="grim_fusion apply-plan",
        )

    def _start_process(
        self,
        npm_args: list[str],
        status: str,
        *,
        mode: str,
        task: str,
    ) -> None:
        if self._process is not None:
            QMessageBox.information(
                self,
                "Fusion Workflow Busy",
                "Another fusion action is already running.",
            )
            return

        npm_command = self._npm_command_value()
        grim_fusion_root = self._grim_fusion_root_value()
        if not npm_command or not grim_fusion_root:
            QMessageBox.warning(
                self,
                "Cannot Run Fusion Workflow",
                "Configure npm command and grim_fusion repo root on the Settings page.",
            )
            return

        self._save_items_path()
        self._save_palette_path()
        self._save_plan_name()
        self._save_output_path()
        self._save_force_apply()
        self._stop_requested = False
        self.log_output.clear()
        self._set_active_steps(self._workflow_steps_for(mode))
        self._advance_step()

        process = QProcess(self)
        process.setProgram(npm_command)
        process.setArguments(npm_args)
        process.setWorkingDirectory(grim_fusion_root)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_process_output)
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)

        self._process = process
        self._set_running(True)
        self.status.setText(status)
        self.backend_task.setText(f"Backend orchestration: {task}")
        process.start()
        self._advance_step()

    def _read_process_output(self) -> None:
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        if text:
            self.log_output.appendPlainText(text.rstrip("\n"))
            self._scan_step_progress(text)

    def _process_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self._process is not None:
            self._read_process_output()

        self._scan_step_progress(self.log_output.toPlainText())

        success = (
            exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        )
        if success:
            self._completed_step_count = len(self._active_steps)
            self.progress.setValue(self._completed_step_count)
            self._refresh_step_status()
            self.status.setText("Fusion workflow completed successfully.")
        elif self._stop_requested:
            self.status.setText("Fusion workflow canceled.")
        else:
            self.status.setText(
                f"Fusion workflow failed (exit code {exit_code})."
            )

        self._cleanup_temp_profile()
        self._set_running(False)
        self._process = None

    def _process_error(self, _error: QProcess.ProcessError) -> None:
        self.status.setText(
            "Failed to start fusion workflow process. Check npm command and repo root settings."
        )
        self.step_status.setText("Workflow did not start. Check Settings paths.")
        self._cleanup_temp_profile()
        self._set_running(False)
        self._process = None

    def _stop_process(self) -> None:
        if self._process is None:
            return
        self._stop_requested = True
        self.status.setText("Cancel requested. Waiting for backend process to stop...")
        self._process.terminate()
        QTimer.singleShot(3000, self._kill_process_if_running)

    def _kill_process_if_running(self) -> None:
        if self._process is None:
            return
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def _set_running(self, running: bool) -> None:
        self.apply_active_button.setEnabled(not running)
        self.generate_button.setEnabled(not running)
        self.apply_plan_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.open_profile_button.setEnabled(not running)
        self.open_export_button.setEnabled(not running)
        self.open_settings_button.setEnabled(not running)

    def _write_temp_profile(self) -> Path:
        with tempfile.NamedTemporaryFile(
            prefix="grim-gleaner-profile-",
            suffix=".json",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        save_profile(self.profile, temp_path)
        self._temp_profile_path = temp_path
        return temp_path

    def _cleanup_temp_profile(self) -> None:
        if self._temp_profile_path is None:
            return
        try:
            self._temp_profile_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._temp_profile_path = None

    def _refresh_status(self) -> None:
        if not self._game_folder_value():
            self.status.setText(
                "Configure Grim Dawn folder before running fusion workflow actions."
            )
            return
        if not self._grim_fusion_root_value():
            self.status.setText(
                "Configure grim_fusion repo root in Settings before running fusion workflow actions."
            )
            return
        self.status.setText("Ready.")

    def _validate_common_inputs(self, *, require_palette: bool) -> str:
        grim_dawn = self.grim_dawn_path_edit.text().strip()
        if not grim_dawn:
            return "Grim Dawn folder is required."
        if not Path(grim_dawn).is_dir():
            return f"Grim Dawn folder does not exist: {grim_dawn}"

        items = self.items_path_edit.text().strip()
        if not items:
            return "Items JSON path is required."
        if not Path(items).is_file():
            return f"Items JSON file not found: {items}"

        if require_palette:
            palette = self.palette_path_edit.text().strip()
            if not palette:
                return "Custom palette file is required when default palette is disabled."
            if not Path(palette).is_file():
                return f"Palette file not found: {palette}"

        return ""

    def _game_folder_value(self) -> str:
        if self.settings is None:
            return ""
        return sanitize_path(self.settings.value(GAME_FOLDER_SETTING, "", type=str))

    def _save_game_folder_value(self) -> None:
        if self.settings is None:
            return
        value = sanitize_path(self.grim_dawn_path_edit.text())
        self.grim_dawn_path_edit.setText(value)
        if value:
            self.settings.setValue(GAME_FOLDER_SETTING, value)
        else:
            self.settings.remove(GAME_FOLDER_SETTING)
        self.settings.sync()
        self._refresh_status()

    def _grim_fusion_root_value(self) -> str:
        if self.settings is None:
            return ""
        return sanitize_path(
            self.settings.value(GRIM_FUSION_ROOT_SETTING, "", type=str)
        )

    def _npm_command_value(self) -> str:
        if self.settings is None:
            return ""
        return sanitize_path(self.settings.value(NPM_COMMAND_SETTING, "", type=str))

    def _saved_items_path(self) -> str:
        if self.settings is not None:
            stored = sanitize_path(self.settings.value(ITEMS_PATH_SETTING, "", type=str))
            if stored:
                return stored

        root = self._grim_fusion_root_value()
        if root:
            return str(Path(root) / "fixtures" / "shared" / "items.json")
        return ""

    def _save_items_path(self) -> None:
        if self.settings is None:
            return
        value = sanitize_path(self.items_path_edit.text())
        self.items_path_edit.setText(value)
        if value:
            self.settings.setValue(ITEMS_PATH_SETTING, value)
        else:
            self.settings.remove(ITEMS_PATH_SETTING)
        self.settings.sync()

    def _saved_palette_path(self) -> str:
        if self.settings is not None:
            return sanitize_path(
                self.settings.value(PALETTE_PATH_SETTING, "", type=str)
            )
        return ""

    def _save_palette_path(self) -> None:
        if self.settings is None:
            return
        value = sanitize_path(self.palette_path_edit.text())
        self.palette_path_edit.setText(value)
        if value:
            self.settings.setValue(PALETTE_PATH_SETTING, value)
        else:
            self.settings.remove(PALETTE_PATH_SETTING)
        self.settings.sync()

    def _saved_plan_name(self) -> str:
        if self.settings is None:
            return ""
        return sanitize_path(self.settings.value(PLAN_NAME_SETTING, "", type=str))

    def _save_plan_name(self) -> None:
        if self.settings is None:
            return
        value = self.plan_name_edit.text().strip()
        self.plan_name_edit.setText(value)
        if value:
            self.settings.setValue(PLAN_NAME_SETTING, value)
        else:
            self.settings.remove(PLAN_NAME_SETTING)
        self.settings.sync()

    def _saved_output_path(self) -> str:
        if self.settings is None:
            return self._default_output_path()
        stored = sanitize_path(
            self.settings.value("fusion/output_path", "", type=str)
        )
        return stored or self._default_output_path()

    def _save_output_path(self) -> None:
        if self.settings is None:
            return
        value = sanitize_path(self.output_path_edit.text())
        self.output_path_edit.setText(value)
        if value:
            self.settings.setValue("fusion/output_path", value)
        else:
            self.settings.remove("fusion/output_path")
        self.settings.sync()

    def _saved_force_apply(self) -> bool:
        if self.settings is None:
            return False
        return bool(self.settings.value(FORCE_APPLY_SETTING, False, type=bool))

    def _save_force_apply(self, checked: bool = False) -> None:
        if self.settings is None:
            return
        self.settings.setValue(FORCE_APPLY_SETTING, checked)
        self.settings.sync()

    def _saved_use_default_palette(self) -> bool:
        if self.settings is None:
            return True
        return bool(self.settings.value(USE_DEFAULT_PALETTE_SETTING, True, type=bool))

    def _palette_mode_changed(self, checked: bool) -> None:
        if self.settings is not None:
            self.settings.setValue(USE_DEFAULT_PALETTE_SETTING, checked)
            self.settings.sync()
        self.palette_path_edit.setEnabled(not checked)
        self.browse_palette_button.setEnabled(not checked)

    def _browse_game_folder(self) -> None:
        starting_path = self.grim_dawn_path_edit.text().strip() or str(Path.cwd())
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Grim Dawn Folder",
            starting_path,
        )
        if not selected:
            return
        self.grim_dawn_path_edit.setText(selected)
        self._save_game_folder_value()

    def _browse_items_path(self) -> None:
        starting_path = self.items_path_edit.text().strip() or str(Path.cwd())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select Items JSON",
            starting_path,
            "JSON Files (*.json);;All Files (*)",
        )
        if not selected:
            return
        self.items_path_edit.setText(selected)
        self._save_items_path()

    def _browse_palette_path(self) -> None:
        starting_path = self.palette_path_edit.text().strip() or str(Path.cwd())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select Palette File",
            starting_path,
            "Text Files (*.txt);;All Files (*)",
        )
        if not selected:
            return
        self.palette_path_edit.setText(selected)
        self._save_palette_path()

    def _browse_output_path(self) -> None:
        starting_path = self.output_path_edit.text().strip() or str(Path.cwd())
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Select Fusion Output JSON",
            starting_path,
            "JSON Files (*.json);;All Files (*)",
        )
        if not selected:
            return
        self.output_path_edit.setText(selected)
        self._save_output_path()

    def _open_profile_page(self) -> None:
        if self.open_profile_page is not None:
            self.open_profile_page()

    def _open_export_page(self) -> None:
        if self.open_export_page is not None:
            self.open_export_page()

    def _open_settings_page(self) -> None:
        if self.open_settings_page is not None:
            self.open_settings_page()
