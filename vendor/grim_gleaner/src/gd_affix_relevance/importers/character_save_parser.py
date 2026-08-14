"""Best-effort extraction of learned skill references from Grim Dawn save files."""

from __future__ import annotations

from dataclasses import dataclass
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
GDSTASH_SUPPORTED_CHARACTER_VERSIONS = frozenset({6, 7, 8})


@dataclass(frozen=True, slots=True)
class GDStashCompatibilityReport:
    """Minimal compatibility signal aligned to GDStash's character parser."""

    character_version: int | None
    supported_by_gdstash: bool | None
    source: str

    def as_text(self) -> str:
        if self.character_version is None:
            return (
                "Could not decode character format version from save header; "
                "GDStash compatibility could not be verified."
            )
        support = (
            "is" if self.supported_by_gdstash else "is not"
        )
        return (
            f"Decoded character format version {self.character_version} "
            f"from save header and it {support} in GDStash's known "
            f"supported versions {sorted(GDSTASH_SUPPORTED_CHARACTER_VERSIONS)} "
            f" ({self.source})."
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

    found: set[str] = set()
    for file_path in _candidate_character_files(source):
        raw = file_path.read_bytes()
        for view in _candidate_byte_views(raw):
            for match in SKILL_REFERENCE_PATTERN.finditer(view):
                text = match.group().decode("ascii", "ignore")
                for parsed in _extract_text_references(text):
                    found.add(_normalize_record_reference(parsed))
    return tuple(sorted(reference for reference in found if reference))


def describe_gdstash_compatibility(
    save_path: Path,
    *,
    parser_root: Path | None = None,
) -> GDStashCompatibilityReport:
    """Report whether *save_path* matches GDStash's known char-format support."""

    source = Path(save_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"character save file does not exist: {source}")

    char_version = _decode_character_version(source)
    supported = (
        char_version in GDSTASH_SUPPORTED_CHARACTER_VERSIONS
        if char_version is not None
        else None
    )
    gdstash_root = _resolve_gdstash_root(parser_root)
    source_text = (
        f"{gdstash_root / 'GDStash.jar'}"
        if gdstash_root is not None
        else "bundled compatibility profile"
    )
    return GDStashCompatibilityReport(
        character_version=char_version,
        supported_by_gdstash=supported,
        source=source_text,
    )


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


def _resolve_gdstash_root(parser_root: Path | None) -> Path | None:
    candidates: list[Path] = []
    if parser_root is not None:
        candidates.append(Path(parser_root).expanduser().resolve())
    candidates.append(Path(r"C:\GDStash"))

    for candidate in candidates:
        if (candidate / "GDStash.jar").is_file():
            return candidate
    return None


def _normalize_record_reference(value: str) -> str:
    return value.strip().replace("\\", "/").lower()


def _extract_text_references(value: str) -> tuple[str, ...]:
    return tuple(SKILL_REFERENCE_TEXT_PATTERN.findall(value))


class _GDStashCryptoReader:
    """Minimal Grim Dawn crypto stream reader modeled after GDStash behavior."""

    XOR_BITMAP = 0x55555555
    TABLE_MULT = 39916801

    def __init__(self, data: bytes) -> None:
        if len(data) < 8:
            raise ValueError("save payload too small")
        self.data = data
        self.pos = 0
        key_seed_raw = self._read_uint_raw()
        key_seed = key_seed_raw ^ self.XOR_BITMAP
        self.key = key_seed & 0xFFFFFFFF
        self.table = self._build_table(key_seed)

    @classmethod
    def _build_table(cls, key: int) -> tuple[int, ...]:
        values: list[int] = []
        current = key & 0xFFFFFFFF
        for _ in range(256):
            current = ((current >> 1) | ((current & 1) << 31)) & 0xFFFFFFFF
            current = (current * cls.TABLE_MULT) & 0xFFFFFFFF
            values.append(current)
        return tuple(values)

    def _read_uint_raw(self) -> int:
        if self.pos + 4 > len(self.data):
            raise ValueError("unexpected end of save while reading uint")
        value = int.from_bytes(self.data[self.pos : self.pos + 4], "little")
        self.pos += 4
        return value

    def _update_key_raw_bytes(self, raw: bytes) -> None:
        for byte in raw:
            self.key ^= self.table[byte]
            self.key &= 0xFFFFFFFF

    def read_int(self, *, update_key: bool = True) -> int:
        start = self.pos
        raw = self._read_uint_raw()
        decoded = (raw ^ self.key) & 0xFFFFFFFF
        if update_key:
            self._update_key_raw_bytes(self.data[start : start + 4])
        return decoded

    def read_byte(self) -> int:
        if self.pos >= len(self.data):
            raise ValueError("unexpected end of save while reading byte")
        raw = self.data[self.pos]
        self.pos += 1
        decoded = (raw ^ (self.key & 0xFF)) & 0xFF
        self._update_key_raw_bytes(bytes((raw,)))
        return decoded

    def read_string(self) -> str:
        length = self.read_int()
        if length <= 0:
            return ""
        if self.pos + length > len(self.data):
            raise ValueError("unexpected end of save while reading string")
        raw = self.data[self.pos : self.pos + length]
        self.pos += length
        out = bytearray(length)
        for index, value in enumerate(raw):
            out[index] = (value ^ (self.key & 0xFF)) & 0xFF
            self._update_key_raw_bytes(bytes((value,)))
        return out.decode("ascii", "ignore")

    def read_wide_string(self) -> str:
        length = self.read_int()
        if length <= 0:
            return ""
        byte_len = length * 2
        if self.pos + byte_len > len(self.data):
            raise ValueError("unexpected end of save while reading wide string")
        raw = self.data[self.pos : self.pos + byte_len]
        self.pos += byte_len
        out = bytearray(byte_len)
        for index, value in enumerate(raw):
            out[index] = (value ^ (self.key & 0xFF)) & 0xFF
            self._update_key_raw_bytes(bytes((value,)))
        return out.decode("utf-8", "ignore")


def _decode_character_version(source: Path) -> int | None:
    """Decode the top-level character format version from *player.gdc*."""

    if source.name.casefold() != "player.gdc":
        source = source.parent / "player.gdc"
    if not source.is_file():
        return None

    try:
        reader = _GDStashCryptoReader(source.read_bytes())
        if reader.read_int() != 0x58434447:
            return None
        reader.read_int()  # historical marker
        reader.read_wide_string()  # character name
        reader.read_byte()  # sex
        reader.read_string()  # class/tag
        reader.read_int()  # level
        reader.read_byte()  # hardcore
        reader.read_byte()  # start byte marker (typically 3)
        reader.read_int(update_key=False)  # marker value (typically 0)
        return reader.read_int()
    except (OSError, ValueError):
        return None
