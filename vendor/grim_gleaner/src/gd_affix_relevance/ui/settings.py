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
CHARACTER_SAVE_ROOT_SETTING = "paths/character_save_root"
GRIM_SAVE_PARSER_ROOT_SETTING = "paths/grim_save_parser_root"
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


def steam_cloud_save_candidates(game_folder: Path | None = None) -> tuple[Path, ...]:
    app_id = "219990"
    candidates: list[Path] = []

    if game_folder is not None:
        # .../Steam/steamapps/common/Grim Dawn -> .../Steam
        steam_root = game_folder.parent.parent.parent
        if steam_root.name.casefold() == "steam":
            candidates.extend(
                (steam_root / "userdata").glob(f"*/{app_id}/remote/save/main")
            )

    for steam_root in (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ):
        if steam_root.is_dir():
            candidates.extend(
                (steam_root / "userdata").glob(f"*/{app_id}/remote/save/main")
            )

    existing = [path for path in candidates if path.is_dir()]
    return tuple(
        sorted(
            set(existing),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    )


def detect_default_character_save_root(game_folder: Path | None = None) -> Path:
    cloud_candidates = steam_cloud_save_candidates(game_folder)
    if cloud_candidates:
        return cloud_candidates[0]
    return Path.home() / "Documents" / "My Games" / "Grim Dawn" / "save"


def detect_default_grim_save_parser_root() -> Path:
    candidates = (
        Path(r"C:\repos\grim-save-parser"),
        Path(__file__).resolve().parents[4] / "vendor" / "grim-save-parser",
    )
    for candidate in candidates:
        if (candidate / "Cargo.toml").is_file():
            return candidate
    return candidates[0]


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

        self.character_save_root_edit = QLineEdit(self._saved_character_save_root(), self)
        self.character_save_root_edit.setObjectName("outputPath")
        self.character_save_root_edit.setPlaceholderText(
            r"Example: C:\Program Files (x86)\Steam\userdata\<steam-id>\219990\remote\save\main"
        )
        self.character_save_root_edit.editingFinished.connect(
            self._save_character_save_root
        )
        save_row = QWidget(self)
        save_layout = QHBoxLayout(save_row)
        save_layout.setContentsMargins(0, 0, 0, 0)
        save_layout.setSpacing(8)
        save_layout.addWidget(self.character_save_root_edit, 1)
        self.browse_save_button = QPushButton("Browse...", save_row)
        self.browse_save_button.setObjectName("profileAction")
        self.browse_save_button.clicked.connect(self._browse_character_save_root)
        save_layout.addWidget(self.browse_save_button)
        form.addRow("Character save folder", save_row)

        self.grim_save_parser_root_edit = QLineEdit(
            self._saved_grim_save_parser_root(),
            self,
        )
        self.grim_save_parser_root_edit.setObjectName("outputPath")
        self.grim_save_parser_root_edit.setPlaceholderText(
            r"Example: C:\repos\grim-save-parser"
        )
        self.grim_save_parser_root_edit.editingFinished.connect(
            self._save_grim_save_parser_root
        )
        parser_row = QWidget(self)
        parser_layout = QHBoxLayout(parser_row)
        parser_layout.setContentsMargins(0, 0, 0, 0)
        parser_layout.setSpacing(8)
        parser_layout.addWidget(self.grim_save_parser_root_edit, 1)
        self.browse_parser_button = QPushButton("Browse...", parser_row)
        self.browse_parser_button.setObjectName("profileAction")
        self.browse_parser_button.clicked.connect(self._browse_grim_save_parser_root)
        parser_layout.addWidget(self.browse_parser_button)
        form.addRow("Grim save parser root", parser_row)
        layout.addLayout(form)

        self.game_folder_status = QLabel(self)
        self.game_folder_status.setWordWrap(True)
        layout.addWidget(self.game_folder_status)

        self.character_save_root_status = QLabel(self)
        self.character_save_root_status.setWordWrap(True)
        layout.addWidget(self.character_save_root_status)

        self.grim_save_parser_root_status = QLabel(self)
        self.grim_save_parser_root_status.setWordWrap(True)
        layout.addWidget(self.grim_save_parser_root_status)

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
        self._refresh_character_save_root_status()
        self._refresh_grim_save_parser_root_status()

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

    def _saved_character_save_root(self) -> str:
        stored = ""
        if self.settings is not None:
            stored = self._sanitize_path(
                self.settings.value(CHARACTER_SAVE_ROOT_SETTING, "", type=str)
            )
        if stored:
            self._persist_character_save_root(stored)
            return stored

        game_folder = self._saved_game_folder()
        detected = detect_default_character_save_root(
            Path(game_folder) if game_folder else None
        )
        self._persist_character_save_root(str(detected))
        return str(detected)

    def _persist_character_save_root(self, value: str) -> None:
        if self.settings is None:
            return
        if value:
            self.settings.setValue(CHARACTER_SAVE_ROOT_SETTING, value)
        else:
            self.settings.remove(CHARACTER_SAVE_ROOT_SETTING)
        self.settings.sync()

    def _saved_grim_save_parser_root(self) -> str:
        stored = ""
        if self.settings is not None:
            stored = self._sanitize_path(
                self.settings.value(GRIM_SAVE_PARSER_ROOT_SETTING, "", type=str)
            )
        if stored:
            self._persist_grim_save_parser_root(stored)
            return stored

        detected = detect_default_grim_save_parser_root()
        self._persist_grim_save_parser_root(str(detected))
        return str(detected)

    def _persist_grim_save_parser_root(self, value: str) -> None:
        if self.settings is None:
            return
        if value:
            self.settings.setValue(GRIM_SAVE_PARSER_ROOT_SETTING, value)
        else:
            self.settings.remove(GRIM_SAVE_PARSER_ROOT_SETTING)
        self.settings.sync()

    def _save_game_folder(self) -> None:
        value = self._sanitize_path(self.game_folder_edit.text())
        self.game_folder_edit.setText(value)
        self._persist_game_folder(value)
        self._refresh_game_folder_status()
        if not self.character_save_root_edit.text().strip():
            detected = str(
                detect_default_character_save_root(Path(value) if value else None)
            )
            self.character_save_root_edit.setText(detected)
            self._persist_character_save_root(detected)
            self._refresh_character_save_root_status()
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

    def _save_character_save_root(self) -> None:
        value = self._sanitize_path(self.character_save_root_edit.text())
        self.character_save_root_edit.setText(value)
        self._persist_character_save_root(value)
        self._refresh_character_save_root_status()

    def _browse_character_save_root(self) -> None:
        starting_path = (
            self.character_save_root_edit.text().strip()
            or str(Path.cwd())
        )
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Character Save Folder",
            starting_path,
        )
        if not selected:
            return
        self.character_save_root_edit.setText(selected)
        self._save_character_save_root()

    def _save_grim_save_parser_root(self) -> None:
        value = self._sanitize_path(self.grim_save_parser_root_edit.text())
        self.grim_save_parser_root_edit.setText(value)
        self._persist_grim_save_parser_root(value)
        self._refresh_grim_save_parser_root_status()

    def _browse_grim_save_parser_root(self) -> None:
        starting_path = (
            self.grim_save_parser_root_edit.text().strip() or str(Path.cwd())
        )
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Grim Save Parser Repository Root",
            starting_path,
        )
        if not selected:
            return
        self.grim_save_parser_root_edit.setText(selected)
        self._save_grim_save_parser_root()

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

    def _refresh_character_save_root_status(self) -> None:
        value = self.character_save_root_edit.text().strip()
        if not value:
            self.character_save_root_status.setObjectName("gameFolderWarning")
            self.character_save_root_status.setText(
                "Character save folder not configured. Import defaults may be incorrect."
            )
        else:
            candidate = Path(value)
            if candidate.is_dir():
                self.character_save_root_status.setObjectName(
                    "gameFolderConfirmed"
                )
                self.character_save_root_status.setText(
                    f"Confirmed character save folder: {candidate}"
                )
            else:
                self.character_save_root_status.setObjectName("gameFolderWarning")
                self.character_save_root_status.setText(
                    f"Not confirmed: folder does not exist: {candidate}"
                )
        self.character_save_root_status.style().unpolish(
            self.character_save_root_status
        )
        self.character_save_root_status.style().polish(
            self.character_save_root_status
        )

    def _refresh_grim_save_parser_root_status(self) -> None:
        value = self.grim_save_parser_root_edit.text().strip()
        if not value:
            self.grim_save_parser_root_status.setObjectName("gameFolderWarning")
            self.grim_save_parser_root_status.setText(
                "Grim save parser root not configured. Character import will use built-in fallback scanning only."
            )
        else:
            root = Path(value)
            if (root / "Cargo.toml").is_file():
                self.grim_save_parser_root_status.setObjectName("gameFolderConfirmed")
                self.grim_save_parser_root_status.setText(
                    f"Detected grim-save-parser project: {root}"
                )
            else:
                self.grim_save_parser_root_status.setObjectName("gameFolderWarning")
                self.grim_save_parser_root_status.setText(
                    "Not confirmed: expected Cargo.toml at parser root. Built-in fallback scanning will still be used."
                )
        self.grim_save_parser_root_status.style().unpolish(
            self.grim_save_parser_root_status
        )
        self.grim_save_parser_root_status.style().polish(
            self.grim_save_parser_root_status
        )

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
