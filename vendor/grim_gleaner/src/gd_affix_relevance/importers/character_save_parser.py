"""Best-effort extraction of learned skill references from Grim Dawn save files."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zlib
from pathlib import Path

# Grim Dawn character saves are binary. This parser intentionally uses a
# conservative byte-pattern scan for skill DBR references instead of trying to
# fully decode the save format.
SKILL_REFERENCE_PATTERN = re.compile(
    rb"records[\\/]+skills[\\/]+[a-z0-9_./\\-]+?\.dbr",
    re.IGNORECASE,
)
SKILL_REFERENCE_TEXT_PATTERN = re.compile(
    r"records[\\/]+skills[\\/]+[a-z0-9_./\\-]+?\.dbr",
    re.IGNORECASE,
)


def extract_skill_references(
    save_path: Path,
    *,
    parser_root: Path | None = None,
) -> tuple[str, ...]:
    """Return unique skill DBR references found in *save_path* bytes.

    The result is normalized to lowercase forward-slash record paths.
    """

    source = Path(save_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"character save file does not exist: {source}")

    external = _extract_with_grim_save_parser(source, parser_root)
    if external:
        return external

    found: set[str] = set()
    for file_path in _candidate_character_files(source):
        raw = file_path.read_bytes()
        for view in _candidate_byte_views(raw):
            for match in SKILL_REFERENCE_PATTERN.finditer(view):
                text = match.group().decode("ascii", "ignore")
                for parsed in _extract_text_references(text):
                    found.add(_normalize_record_reference(parsed))
    return tuple(sorted(reference for reference in found if reference))


def _candidate_character_files(source: Path) -> tuple[Path, ...]:
    """Return save files that can contain character skill references."""

    files = [source]
    # Cloud saves frequently split character payload across companion chunks
    # such as player.g00/player.g01 where skill references are stored.
    siblings = sorted(
        candidate
        for candidate in source.parent.glob("player.g*")
        if candidate.is_file()
    )
    if siblings:
        files.extend(siblings)
    return tuple(dict.fromkeys(files))


def _candidate_byte_views(raw: bytes) -> tuple[bytes, ...]:
    # Some save sections may encode paths with interleaved null bytes (UTF-16-like).
    # Scanning both views catches those without needing a full save decoder.
    views: list[bytes] = [raw]

    compact = raw.replace(b"\x00", b"")
    if compact != raw:
        views.append(compact)

    for inflated in _inflated_byte_views(raw):
        views.append(inflated)
        inflated_compact = inflated.replace(b"\x00", b"")
        if inflated_compact != inflated:
            views.append(inflated_compact)

    return tuple(views)


def _inflated_byte_views(raw: bytes) -> tuple[bytes, ...]:
    """Return best-effort zlib-inflated payloads from a binary save blob."""

    outputs: list[bytes] = []
    seen: set[bytes] = set()
    max_candidates = 128
    max_output_size = 8 * 1024 * 1024

    for index, byte in enumerate(raw):
        if byte != 0x78:
            continue
        if len(outputs) >= max_candidates:
            break
        try:
            stream = zlib.decompressobj()
            inflated = stream.decompress(raw[index:], max_output_size)
        except zlib.error:
            continue
        if len(inflated) < 64:
            continue
        if inflated in seen:
            continue
        seen.add(inflated)
        outputs.append(inflated)

    return tuple(outputs)


def _normalize_record_reference(value: str) -> str:
    return value.strip().replace("\\", "/").lower()


def _extract_text_references(value: str) -> tuple[str, ...]:
    return tuple(SKILL_REFERENCE_TEXT_PATTERN.findall(value))


def _extract_with_grim_save_parser(
    save_path: Path,
    parser_root: Path | None,
) -> tuple[str, ...]:
    executable = _resolve_grim_save_parser_executable(parser_root)
    if executable is None:
        return ()

    command = [
        str(executable),
        "--entity-type",
        "character",
        "--filepath",
        str(save_path),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()

    output = result.stdout.strip()
    if not output.startswith("{"):
        return ()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return ()

    found: set[str] = set()
    for reference in _walk_skill_names(payload):
        for parsed in _extract_text_references(reference):
            found.add(_normalize_record_reference(parsed))
    return tuple(sorted(found))


def _resolve_grim_save_parser_executable(
    parser_root: Path | None,
) -> Path | None:
    env_override = os.environ.get("GRIM_SAVE_PARSER_EXE", "").strip()
    if env_override:
        candidate = Path(env_override).expanduser().resolve()
        if candidate.is_file():
            return candidate

    search_roots: list[Path] = []
    if parser_root is not None:
        search_roots.append(Path(parser_root).expanduser().resolve())
    env_root = os.environ.get("GRIM_SAVE_PARSER_ROOT", "").strip()
    if env_root:
        search_roots.append(Path(env_root).expanduser().resolve())
    search_roots.extend(
        [
            Path(r"C:\repos\grim-save-parser"),
            Path(__file__).resolve().parents[4] / "vendor" / "grim-save-parser",
        ]
    )

    for root in search_roots:
        candidate = root / "target" / "debug" / "console-app.exe"
        if candidate.is_file():
            return candidate
        cargo = shutil.which("cargo")
        if cargo and (root / "Cargo.toml").is_file():
            try:
                result = subprocess.run(
                    [
                        cargo,
                        "build",
                        "-p",
                        "console-app",
                    ],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode == 0 and candidate.is_file():
                return candidate
    return None


def _walk_skill_names(payload: object) -> tuple[str, ...]:
    names: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "name" and isinstance(nested, str):
                    names.append(nested)
                walk(nested)
            return
        if isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(payload)
    return tuple(names)
