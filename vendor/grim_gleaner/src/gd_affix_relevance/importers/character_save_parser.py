"""GDStash-style character-save parsing and skill reference extraction."""

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
MASTERY_ID_PATTERN = re.compile(rb"playerclass\d{2}", re.IGNORECASE)
GDSTASH_SUPPORTED_CHARACTER_VERSIONS = frozenset({6, 7, 8})


@dataclass(frozen=True, slots=True)
class ParseDiagnostic:
    severity: str
    code: str
    message: str
    source_file: str = ""


@dataclass(frozen=True, slots=True)
class CharacterSaveParseMetadata:
    character_version: int | None
    character_level: int | None
    supported_by_gdstash: bool | None
    source: str
    files_scanned: tuple[str, ...]
    bytes_scanned: int
    references_found: int
    inferred_masteries: tuple[str, ...]
    partial_parse: bool
    confidence: float
    diagnostics: tuple[ParseDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CharacterSaveParseResult:
    references: tuple[str, ...]
    metadata: CharacterSaveParseMetadata


@dataclass(frozen=True, slots=True)
class CharacterHeaderInfo:
    character_version: int
    character_level: int


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
    """Return unique skill DBR references extracted from *save_path*."""

    return parse_character_save(save_path, parser_root=parser_root).references


def parse_character_save(
    save_path: Path,
    *,
    parser_root: Path | None = None,
) -> CharacterSaveParseResult:
    """Parse a Grim Dawn character save into references plus diagnostics."""

    source = Path(save_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"character save file does not exist: {source}")

    gdstash_root = _resolve_gdstash_root(parser_root)
    source_text = (
        f"{gdstash_root / 'GDStash.jar'}"
        if gdstash_root is not None
        else "bundled compatibility profile"
    )
    header = _decode_character_header(source)
    character_version = header.character_version if header is not None else None
    character_level = header.character_level if header is not None else None
    supported = (
        character_version in GDSTASH_SUPPORTED_CHARACTER_VERSIONS
        if character_version is not None
        else None
    )

    diagnostics: list[ParseDiagnostic] = []
    if character_version is None:
        diagnostics.append(
            ParseDiagnostic(
                severity="warning",
                code="unknown_character_version",
                message=(
                    "Could not decode character format version from player.gdc. "
                    "Continuing with best-effort block scanning."
                ),
                source_file="player.gdc",
            )
        )
    elif not supported:
        diagnostics.append(
            ParseDiagnostic(
                severity="warning",
                code="unsupported_character_version",
                message=(
                    "Character format version is outside GDStash's known support "
                    "window; partial parsing is expected."
                ),
                source_file="player.gdc",
            )
        )

    files = _candidate_character_files(source)
    references: set[str] = set()
    inferred_masteries: set[str] = set()
    bytes_scanned = 0
    files_scanned: list[str] = []
    for file_path in files:
        files_scanned.append(file_path.name)
        try:
            raw = file_path.read_bytes()
        except OSError as error:
            _append_diagnostic_once(
                diagnostics,
                ParseDiagnostic(
                    severity="error",
                    code="read_error",
                    message=f"Could not read save chunk: {error}",
                    source_file=file_path.name,
                ),
            )
            continue
        bytes_scanned += len(raw)
        for view in _candidate_byte_views(raw, diagnostics, file_path):
            for match in SKILL_REFERENCE_PATTERN.finditer(view):
                text = match.group().decode("ascii", "ignore")
                for parsed in _extract_text_references(text):
                    references.add(_normalize_record_reference(parsed))
            for match in MASTERY_ID_PATTERN.finditer(view):
                inferred_masteries.add(match.group().decode("ascii", "ignore").casefold())

    normalized = tuple(sorted(reference for reference in references if reference))
    companion_count = len(
        [name for name in files_scanned if name.casefold() != "player.gdc"]
    )
    if not normalized and companion_count == 0:
        _append_diagnostic_once(
            diagnostics,
            ParseDiagnostic(
                severity="warning",
                code="packed_save_without_companions",
                message=(
                    "Character folder has no player.g00/player.g01 companion chunks; "
                    "packed saves may omit extractable skill DBR references."
                ),
                source_file="player.gdc",
            ),
        )

    partial_parse = (
        not normalized
        or supported is False
        or any(diag.severity == "error" for diag in diagnostics)
    )
    confidence = _parse_confidence(
        reference_count=len(normalized),
        supported=supported,
        partial_parse=partial_parse,
        diagnostics=diagnostics,
        companion_count=companion_count,
    )
    metadata = CharacterSaveParseMetadata(
        character_version=character_version,
        character_level=character_level,
        supported_by_gdstash=supported,
        source=source_text,
        files_scanned=tuple(files_scanned),
        bytes_scanned=bytes_scanned,
        references_found=len(normalized),
        inferred_masteries=tuple(sorted(inferred_masteries)),
        partial_parse=partial_parse,
        confidence=confidence,
        diagnostics=tuple(diagnostics),
    )
    return CharacterSaveParseResult(references=normalized, metadata=metadata)


def describe_gdstash_compatibility(
    save_path: Path,
    *,
    parser_root: Path | None = None,
) -> GDStashCompatibilityReport:
    """Report whether *save_path* matches GDStash's known char-format support."""

    source = Path(save_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"character save file does not exist: {source}")

    header = _decode_character_header(source)
    char_version = header.character_version if header is not None else None
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


def _append_diagnostic_once(
    diagnostics: list[ParseDiagnostic],
    entry: ParseDiagnostic,
) -> None:
    key = (entry.severity, entry.code, entry.message, entry.source_file)
    for existing in diagnostics:
        existing_key = (
            existing.severity,
            existing.code,
            existing.message,
            existing.source_file,
        )
        if existing_key == key:
            return
    diagnostics.append(entry)


def _candidate_byte_views(
    raw: bytes,
    diagnostics: list[ParseDiagnostic],
    source_file: Path,
) -> tuple[bytes, ...]:
    # Some save sections may encode paths with interleaved null bytes (UTF-16-like).
    # Scanning both views catches those without needing a full save decoder.
    views: list[bytes] = [raw]

    compact = raw.replace(b"\x00", b"")
    if compact != raw:
        views.append(compact)

    for inflated in _inflated_byte_views(raw, diagnostics, source_file):
        views.append(inflated)
        inflated_compact = inflated.replace(b"\x00", b"")
        if inflated_compact != inflated:
            views.append(inflated_compact)

    for decrypted in _decrypted_byte_views(raw, diagnostics, source_file):
        views.append(decrypted)
        decrypted_compact = decrypted.replace(b"\x00", b"")
        if decrypted_compact != decrypted:
            views.append(decrypted_compact)

        for inflated in _inflated_byte_views(decrypted, diagnostics, source_file):
            views.append(inflated)
            inflated_compact = inflated.replace(b"\x00", b"")
            if inflated_compact != inflated:
                views.append(inflated_compact)

    return tuple(views)


def _decrypted_byte_views(
    raw: bytes,
    diagnostics: list[ParseDiagnostic],
    source_file: Path,
) -> tuple[bytes, ...]:
    """Return best-effort crypto-decoded byte views for encrypted save chunks."""

    if len(raw) < 12:
        return ()

    outputs: list[bytes] = []
    seen: set[bytes] = set()

    # Some save blocks are encrypted independently and begin at nontrivial
    # offsets inside player.gdc. Probe a bounded set of plausible offsets.
    candidate_offsets: list[int] = [0, 4, 8]
    scan_limit = min(len(raw) - 8, 64 * 1024)
    step = 4
    for offset in range(12, scan_limit, step):
        candidate_offsets.append(offset)

    max_candidates = 96
    selected = 0
    for offset in candidate_offsets:
        if selected >= max_candidates:
            break
        if len(raw) - offset < 12:
            continue
        segment = raw[offset:]
        try:
            reader = _GDStashCryptoReader(segment)
            decoded = reader.decode_remaining()
        except ValueError:
            continue
        if len(decoded) < 24:
            continue
        # Keep views with explicit skill path signals or mastery identifiers.
        if (
            b"records/skills/" not in decoded.lower()
            and b"records\\skills\\" not in decoded.lower()
            and b"playerclass" not in decoded.lower()
        ):
            continue
        if decoded in seen:
            continue
        seen.add(decoded)
        outputs.append(decoded)
        selected += 1

    if not outputs and source_file.name.casefold().startswith("player.g"):
        _append_diagnostic_once(
            diagnostics,
            ParseDiagnostic(
                severity="info",
                code="crypto_decode_no_payload",
                message=(
                    "No useful crypto-decoded payload was detected in this chunk."
                ),
                source_file=source_file.name,
            ),
        )

    return tuple(outputs)


def _inflated_byte_views(
    raw: bytes,
    diagnostics: list[ParseDiagnostic],
    source_file: Path,
) -> tuple[bytes, ...]:
    """Return best-effort zlib-inflated payloads from a binary save blob."""

    outputs: list[bytes] = []
    seen: set[bytes] = set()
    max_candidates = 128
    max_output_size = 8 * 1024 * 1024

    failures = 0
    for index, byte in enumerate(raw):
        # Common zlib/deflate stream starts. We still rely on successful
        # decompression to accept a candidate.
        if byte not in {0x78, 0x58, 0x68, 0x08}:
            continue
        if len(outputs) >= max_candidates:
            break
        inflated_candidate: bytes | None = None
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, zlib.MAX_WBITS | 32):
            try:
                stream = zlib.decompressobj(wbits)
                inflated = stream.decompress(raw[index:], max_output_size)
            except zlib.error:
                continue
            if len(inflated) < 24:
                continue
            inflated_candidate = inflated
            break

        if inflated_candidate is None:
            failures += 1
            continue
        if inflated_candidate in seen:
            continue
        seen.add(inflated_candidate)
        outputs.append(inflated_candidate)

    if failures and not outputs:
        _append_diagnostic_once(
            diagnostics,
            ParseDiagnostic(
                severity="info",
                code="zlib_scan_no_payload",
                message=(
                    "Detected compressed-looking blocks but no usable zlib payload "
                    "could be inflated."
                ),
                source_file=source_file.name,
            ),
        )

    return tuple(outputs)


def _parse_confidence(
    *,
    reference_count: int,
    supported: bool | None,
    partial_parse: bool,
    diagnostics: list[ParseDiagnostic],
    companion_count: int,
) -> float:
    score = 0.25
    if reference_count > 0:
        score += 0.45
    if companion_count > 0:
        score += 0.1
    if supported is True:
        score += 0.15
    if supported is False:
        score -= 0.2
    if partial_parse:
        score -= 0.15
    if any(diag.severity == "error" for diag in diagnostics):
        score -= 0.2
    return max(0.0, min(1.0, round(score, 3)))


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

    def decode_remaining(self, *, max_output_size: int = 16 * 1024 * 1024) -> bytes:
        """Decode remaining stream bytes using GDStash-style rolling key updates."""

        out = bytearray()
        while self.pos < len(self.data):
            if len(out) >= max_output_size:
                break
            raw = self.data[self.pos]
            self.pos += 1
            out.append((raw ^ (self.key & 0xFF)) & 0xFF)
            self._update_key_raw_bytes(bytes((raw,)))
        return bytes(out)


def _decode_character_header(source: Path) -> CharacterHeaderInfo | None:
    """Decode top-level header fields (version and level) from *player.gdc*."""

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
        level = reader.read_int()  # level
        reader.read_byte()  # hardcore
        reader.read_byte()  # start byte marker (typically 3)
        reader.read_int(update_key=False)  # marker value (typically 0)
        version = reader.read_int()
        return CharacterHeaderInfo(character_version=version, character_level=level)
    except (OSError, ValueError):
        return None
