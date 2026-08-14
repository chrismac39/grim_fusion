import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.ui.fusion_workflow import FusionWorkflowPage
from gd_affix_relevance.ui.settings import (
    GAME_FOLDER_SETTING,
    GRIM_FUSION_ROOT_SETTING,
    NPM_COMMAND_SETTING,
)


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _settings(tmp_path: Path) -> QSettings:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue(NPM_COMMAND_SETTING, "npm")
    settings.sync()
    return settings


def test_generate_output_uses_ui_inputs_and_backend_orchestration(
    tmp_path: Path,
) -> None:
    _application()
    settings = _settings(tmp_path)

    game_folder = tmp_path / "Grim Dawn"
    game_folder.mkdir(parents=True)
    items_path = tmp_path / "items.json"
    items_path.write_text("[]", encoding="utf-8")

    fusion_root = tmp_path / "fusion"
    (fusion_root / "apps" / "cli").mkdir(parents=True)
    (fusion_root / "package.json").write_text("{}", encoding="utf-8")
    (fusion_root / "apps" / "cli" / "package.json").write_text("{}", encoding="utf-8")

    settings.setValue(GAME_FOLDER_SETTING, str(game_folder))
    settings.setValue(GRIM_FUSION_ROOT_SETTING, str(fusion_root))
    settings.sync()

    captured: dict[str, object] = {}
    page = FusionWorkflowPage(BuildProfile(), settings=settings)
    page.items_path_edit.setText(str(items_path))
    page.output_path_edit.setText(str(tmp_path / "out.json"))

    def fake_start_process(
        npm_args: list[str],
        status: str,
        *,
        mode: str,
        task: str,
    ) -> None:
        captured["npm_args"] = npm_args
        captured["status"] = status
        captured["mode"] = mode
        captured["task"] = task

    page._start_process = fake_start_process  # type: ignore[method-assign]

    page._run_generate_output()

    args = captured["npm_args"]
    assert isinstance(args, list)
    assert "run" in args
    assert "--items" in args
    assert str(items_path) in args
    assert "--out" in args
    assert str(tmp_path / "out.json") in args
    assert captured["mode"] == "generate"
    assert captured["task"] == "grim_fusion run"


def test_cancel_requests_graceful_shutdown_before_force_kill() -> None:
    _application()
    page = FusionWorkflowPage(BuildProfile())

    events: list[str] = []

    class FakeProcess:
        def terminate(self) -> None:
            events.append("terminate")

        def kill(self) -> None:
            events.append("kill")

        def state(self):
            return 2

    page._process = FakeProcess()  # type: ignore[assignment]
    page._stop_process()

    assert page._stop_requested
    assert events[0] == "terminate"
