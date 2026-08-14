"""Application-level settings page."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gd_affix_relevance.grade_export import validate_grim_dawn_folder

GAME_FOLDER_SETTING = "paths/grim_dawn_folder"
GRIM_FUSION_ROOT_SETTING = "paths/grim_fusion_root"
NPM_COMMAND_SETTING = "tools/npm_command"
GAME_FOLDER_ENV = "GRIM_DAWN_INSTALL_PATH"
WINDOWS_DEFAULT_GAME_FOLDER = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Grim Dawn"
)


def sanitize_path(value: str) -> str:
    trimmed = value.strip()
    if (
        len(trimmed) >= 2
        and trimmed[0] == trimmed[-1]
        and trimmed[0] in {'"', "'"}
    ):
        return trimmed[1:-1].strip()
    return trimmed


def detect_default_grim_fusion_root() -> Path:
    candidates = (
        Path(__file__).resolve().parents[5],
        Path(r"C:\repos\grim_fusion"),
    )
    for candidate in candidates:
        if (candidate / "package.json").is_file() and (
            candidate / "apps" / "cli" / "package.json"
        ).is_file():
            return candidate
    return candidates[1]


class SettingsPage(QWidget):
    """Store application paths that are not part of a build profile."""

    game_folder_changed = Signal(str)

    def __init__(
        self,
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        heading = QLabel("Settings", self)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)

        hint = QLabel(
            "Application-level paths and preferences. These settings are "
            "stored separately from build profiles.",
            self,
        )
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.game_folder_edit = QLineEdit(self._saved_game_folder(), self)
        self.game_folder_edit.setObjectName("outputPath")
        self.game_folder_edit.setPlaceholderText(
            r"Example: C:\Program Files (x86)\Steam\steamapps\common\Grim Dawn"
        )
        self.game_folder_edit.editingFinished.connect(self._save_game_folder)

        path_row = QWidget(self)
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(8)
        path_layout.addWidget(self.game_folder_edit, 1)
        self.browse_button = QPushButton("Browse...", path_row)
        self.browse_button.setObjectName("profileAction")
        self.browse_button.clicked.connect(self._browse_game_folder)
        path_layout.addWidget(self.browse_button)
        form.addRow("Grim Dawn folder location", path_row)

        self.grim_fusion_root_edit = QLineEdit(
            self._saved_grim_fusion_root(),
            self,
        )
        self.grim_fusion_root_edit.setObjectName("outputPath")
        self.grim_fusion_root_edit.setPlaceholderText(
            r"Example: C:\repos\grim_fusion"
        )
        self.grim_fusion_root_edit.editingFinished.connect(
            self._save_grim_fusion_root
        )
        fusion_row = QWidget(self)
        fusion_layout = QHBoxLayout(fusion_row)
        fusion_layout.setContentsMargins(0, 0, 0, 0)
        fusion_layout.setSpacing(8)
        fusion_layout.addWidget(self.grim_fusion_root_edit, 1)
        self.browse_fusion_button = QPushButton("Browse...", fusion_row)
        self.browse_fusion_button.setObjectName("profileAction")
        self.browse_fusion_button.clicked.connect(self._browse_grim_fusion_root)
        fusion_layout.addWidget(self.browse_fusion_button)
        form.addRow("grim_fusion repo root", fusion_row)

        self.npm_command_edit = QLineEdit(self._saved_npm_command(), self)
        self.npm_command_edit.setObjectName("outputPath")
        self.npm_command_edit.setPlaceholderText("Example: npm or C:\\Program Files\\nodejs\\npm.cmd")
        self.npm_command_edit.editingFinished.connect(self._save_npm_command)
        form.addRow("npm command", self.npm_command_edit)
        layout.addLayout(form)

        self.game_folder_status = QLabel(self)
        self.game_folder_status.setWordWrap(True)
        layout.addWidget(self.game_folder_status)

        self.grim_fusion_root_status = QLabel(self)
        self.grim_fusion_root_status.setWordWrap(True)
        layout.addWidget(self.grim_fusion_root_status)

        self.npm_command_status = QLabel(self)
        self.npm_command_status.setWordWrap(True)
        layout.addWidget(self.npm_command_status)

        note = QLabel(
            "Export Grades checks this folder's settings/text_en directory for "
            "existing item-tag files. Installed files take precedence and the "
            "bundled clean-install tags fill any missing files. Export writes "
            "the graded files there after preserving an original-state backup.",
            self,
        )
        note.setObjectName("pageHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self._refresh_game_folder_status()
        self._refresh_grim_fusion_root_status()
        self._refresh_npm_command_status()

    @staticmethod
    def _sanitize_path(value: str) -> str:
        return sanitize_path(value)

    def _saved_game_folder(self) -> str:
        stored = ""
        if self.settings is not None:
            stored = self._sanitize_path(
                self.settings.value(GAME_FOLDER_SETTING, "", type=str)
            )
        if stored:
            self._persist_game_folder(stored)
            return stored

        env_path = self._sanitize_path(os.environ.get(GAME_FOLDER_ENV, ""))
        if env_path and Path(env_path).exists():
            self._persist_game_folder(env_path)
            return env_path

        if Path(WINDOWS_DEFAULT_GAME_FOLDER).exists():
            self._persist_game_folder(WINDOWS_DEFAULT_GAME_FOLDER)
            return WINDOWS_DEFAULT_GAME_FOLDER

        return ""

    def _persist_game_folder(self, value: str) -> None:
        if self.settings is None:
            return
        if value:
            self.settings.setValue(GAME_FOLDER_SETTING, value)
        else:
            self.settings.remove(GAME_FOLDER_SETTING)
        self.settings.sync()

    def _saved_grim_fusion_root(self) -> str:
        stored = ""
        if self.settings is not None:
            stored = self._sanitize_path(
                self.settings.value(GRIM_FUSION_ROOT_SETTING, "", type=str)
            )
        if stored:
            self._persist_grim_fusion_root(stored)
            return stored

        detected = detect_default_grim_fusion_root()
        self._persist_grim_fusion_root(str(detected))
        return str(detected)

    def _persist_grim_fusion_root(self, value: str) -> None:
        if self.settings is None:
            return
        if value:
            self.settings.setValue(GRIM_FUSION_ROOT_SETTING, value)
        else:
            self.settings.remove(GRIM_FUSION_ROOT_SETTING)
        self.settings.sync()

    def _saved_npm_command(self) -> str:
        if self.settings is not None:
            stored = self._sanitize_path(
                self.settings.value(NPM_COMMAND_SETTING, "", type=str)
            )
            if stored:
                self._persist_npm_command(stored)
                return stored
        command = "npm.cmd" if os.name == "nt" else "npm"
        self._persist_npm_command(command)
        return command

    def _persist_npm_command(self, value: str) -> None:
        if self.settings is None:
            return
        if value:
            self.settings.setValue(NPM_COMMAND_SETTING, value)
        else:
            self.settings.remove(NPM_COMMAND_SETTING)
        self.settings.sync()

    def _save_game_folder(self) -> None:
        value = self._sanitize_path(self.game_folder_edit.text())
        self.game_folder_edit.setText(value)
        self._persist_game_folder(value)
        self._refresh_game_folder_status()
        self.game_folder_changed.emit(value)

    def prompt_for_game_folder(self) -> bool:
        """Ask for an install root and return whether it was confirmed."""

        starting_path = self.game_folder_edit.text().strip() or str(Path.cwd())
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Grim Dawn Folder (contains Grim Dawn.exe)",
            starting_path,
        )
        if not selected:
            return False
        self.game_folder_edit.setText(selected)
        self._save_game_folder()
        if not self.has_valid_game_folder():
            QMessageBox.warning(
                self,
                "Grim Dawn Not Found",
                "That folder does not contain Grim Dawn.exe. Select the Grim "
                "Dawn installation folder itself.",
            )
            return False
        return True

    def _browse_game_folder(self) -> None:
        self.prompt_for_game_folder()

    def _save_grim_fusion_root(self) -> None:
        value = self._sanitize_path(self.grim_fusion_root_edit.text())
        self.grim_fusion_root_edit.setText(value)
        self._persist_grim_fusion_root(value)
        self._refresh_grim_fusion_root_status()

    def _browse_grim_fusion_root(self) -> None:
        starting_path = self.grim_fusion_root_edit.text().strip() or str(Path.cwd())
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select grim_fusion Repository Root",
            starting_path,
        )
        if not selected:
            return
        self.grim_fusion_root_edit.setText(selected)
        self._save_grim_fusion_root()

    def _save_npm_command(self) -> None:
        value = self._sanitize_path(self.npm_command_edit.text())
        self.npm_command_edit.setText(value)
        self._persist_npm_command(value)
        self._refresh_npm_command_status()

    def has_valid_game_folder(self) -> bool:
        game, _ = self._game_folder_validation()
        return game is not None

    def _refresh_game_folder_status(self) -> None:
        game, error = self._game_folder_validation()
        if game is None:
            self.game_folder_status.setObjectName("gameFolderWarning")
            self.game_folder_status.setText(error)
        else:
            self.game_folder_status.setObjectName("gameFolderConfirmed")
            self.game_folder_status.setText(
                f"Confirmed Grim Dawn installation: {game}"
            )
        self.game_folder_status.style().unpolish(self.game_folder_status)
        self.game_folder_status.style().polish(self.game_folder_status)

    def _refresh_grim_fusion_root_status(self) -> None:
        value = self.grim_fusion_root_edit.text().strip()
        if not value:
            self.grim_fusion_root_status.setObjectName("gameFolderWarning")
            self.grim_fusion_root_status.setText(
                "grim_fusion repo root not configured. Fusion workflow actions are unavailable."
            )
        else:
            root = Path(value)
            if (root / "package.json").is_file() and (
                root / "apps" / "cli" / "package.json"
            ).is_file():
                self.grim_fusion_root_status.setObjectName("gameFolderConfirmed")
                self.grim_fusion_root_status.setText(
                    f"Detected grim_fusion repository: {root}"
                )
            else:
                self.grim_fusion_root_status.setObjectName("gameFolderWarning")
                self.grim_fusion_root_status.setText(
                    "Not confirmed: expected package.json and apps/cli/package.json at repo root."
                )
        self.grim_fusion_root_status.style().unpolish(self.grim_fusion_root_status)
        self.grim_fusion_root_status.style().polish(self.grim_fusion_root_status)

    def _refresh_npm_command_status(self) -> None:
        value = self.npm_command_edit.text().strip()
        if not value:
            self.npm_command_status.setObjectName("gameFolderWarning")
            self.npm_command_status.setText(
                "npm command is blank. Fusion workflow actions are unavailable."
            )
        else:
            self.npm_command_status.setObjectName("gameFolderConfirmed")
            self.npm_command_status.setText(
                f"Configured npm command: {value}"
            )
        self.npm_command_status.style().unpolish(self.npm_command_status)
        self.npm_command_status.style().polish(self.npm_command_status)

    def _game_folder_validation(self) -> tuple[Path | None, str]:
        value = self.game_folder_edit.text().strip()
        if not value:
            return (
                None,
                "Not configured. Select the folder containing Grim Dawn.exe.",
            )
        try:
            return validate_grim_dawn_folder(Path(value)), ""
        except (OSError, ValueError) as error:
            return None, f"Not confirmed: {error}"
