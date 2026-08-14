"""Best-effort extraction of learned skill references from Grim Dawn save files."""

from __future__ import annotations

import re
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


def extract_skill_references(save_path: Path) -> tuple[str, ...]:
    """Return unique skill DBR references found in *save_path* bytes.

    The result is normalized to lowercase forward-slash record paths.
    """

    source = Path(save_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"character save file does not exist: {source}")

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
