from __future__ import annotations

from pathlib import Path
import zlib

from gd_affix_relevance.importers.character_save_parser import (
    describe_gdstash_compatibility,
    extract_skill_references,
    parse_character_save,
)


def _encrypt_like_gdstash(decoded: bytes, *, seed_raw: int = 0x12345678) -> bytes:
    """Build a synthetic stream compatible with _GDStashCryptoReader decoding."""

    xor_bitmap = 0x55555555
    table_mult = 39916801
    key_seed = seed_raw ^ xor_bitmap
    key = key_seed & 0xFFFFFFFF
    table: list[int] = []
    current = key_seed & 0xFFFFFFFF
    for _ in range(256):
        current = ((current >> 1) | ((current & 1) << 31)) & 0xFFFFFFFF
        current = (current * table_mult) & 0xFFFFFFFF
        table.append(current)

    encrypted = bytearray(seed_raw.to_bytes(4, "little"))
    for value in decoded:
        raw = (value ^ (key & 0xFF)) & 0xFF
        encrypted.append(raw)
        key ^= table[raw]
        key &= 0xFFFFFFFF
    return bytes(encrypted)


def test_extract_skill_references_normalizes_and_deduplicates(tmp_path: Path) -> None:
    payload = (
        b"noise"
        b"records/skills/playerclass02/flamestrike1.dbr"
        b"\x00"
        b"records\\skills\\playerclass02\\flamestrike1.dbr"
        b"\x00"
        b"records/skills/playerclass07/doombolt1.dbr"
    )
    source = tmp_path / "player.gdc"
    source.write_bytes(payload)

    references = extract_skill_references(source)

    assert references == (
        "records/skills/playerclass02/flamestrike1.dbr",
        "records/skills/playerclass07/doombolt1.dbr",
    )


def test_extract_skill_references_handles_null_interleaved_bytes(
    tmp_path: Path,
) -> None:
    text = "records/skills/playerclass01/cadence1.dbr"
    wide_like = b"".join(bytes((byte, 0)) for byte in text.encode("ascii"))
    source = tmp_path / "player.gdc"
    source.write_bytes(b"prefix" + wide_like + b"suffix")

    references = extract_skill_references(source)

    assert references == ("records/skills/playerclass01/cadence1.dbr",)


def test_extract_skill_references_reads_player_companion_chunks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "char"
    root.mkdir(parents=True)
    # Selected file has no references.
    (root / "player.gdc").write_bytes(b"header-only")
    # Companion chunk carries actual skill references.
    (root / "player.g00").write_bytes(
        b"records/skills/playerclass03/curse1.dbr\x00"
        b"records/skills/playerclass10/werewolf1.dbr"
    )

    references = extract_skill_references(root / "player.gdc")

    assert references == (
        "records/skills/playerclass03/curse1.dbr",
        "records/skills/playerclass10/werewolf1.dbr",
    )


def test_parse_character_save_extracts_references_from_compressed_block(
    tmp_path: Path,
) -> None:
    reference = b"records/skills/playerclass08/shamanstrike1.dbr"
    payload = b"prefix" + zlib.compress(reference + b"\x00") + b"suffix"
    source = tmp_path / "player.gdc"
    source.write_bytes(payload)

    result = parse_character_save(source)

    assert result.references == (
        "records/skills/playerclass08/shamanstrike1.dbr",
    )
    assert result.metadata.references_found == 1
    assert result.metadata.confidence > 0.4


def test_parse_character_save_extracts_references_from_crypto_decoded_stream(
    tmp_path: Path,
) -> None:
    decoded = (
        b"prefix\x00"
        b"records/skills/playerclass04/bloodburst1.dbr\x00"
        b"suffix"
    )
    payload = _encrypt_like_gdstash(decoded)
    source = tmp_path / "player.g00"
    source.write_bytes(payload)

    result = parse_character_save(source)

    assert "records/skills/playerclass04/bloodburst1.dbr" in result.references


def test_parse_character_save_reports_partial_parse_and_diagnostics(
    tmp_path: Path,
) -> None:
    source = tmp_path / "player.gdc"
    source.write_bytes(b"not-a-gd-save")

    result = parse_character_save(source)

    assert result.references == ()
    assert result.metadata.partial_parse
    assert result.metadata.references_found == 0
    assert result.metadata.character_level is None
    assert result.metadata.files_scanned == ("player.gdc",)
    assert result.metadata.confidence < 0.5
    assert any(
        diag.code == "unknown_character_version"
        for diag in result.metadata.diagnostics
    )


def test_parse_character_save_infers_masteries_without_skill_references(
    tmp_path: Path,
) -> None:
    source = tmp_path / "player.gdc"
    source.write_bytes(b"prefix-playerclass02-middle-playerclass08-suffix")

    result = parse_character_save(source)

    assert result.references == ()
    assert result.metadata.inferred_masteries == (
        "playerclass02",
        "playerclass08",
    )


def test_parse_character_save_deduplicates_zlib_no_payload_diagnostics(
    tmp_path: Path,
) -> None:
    source = tmp_path / "player.gdc"
    source.write_bytes(b"x" * 2048)

    result = parse_character_save(source)

    codes = [diag.code for diag in result.metadata.diagnostics]
    assert codes.count("zlib_scan_no_payload") <= 1


def test_gdstash_compatibility_report_handles_unknown_header(
    tmp_path: Path,
) -> None:
    source = tmp_path / "player.gdc"
    source.write_bytes(b"not-a-gd-save")

    report = describe_gdstash_compatibility(source)

    assert report.character_version is None
    assert report.supported_by_gdstash is None
    assert "Could not decode" in report.as_text()


def test_gdstash_compatibility_report_prefers_configured_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "GDStash"
    root.mkdir(parents=True)
    (root / "GDStash.jar").write_bytes(b"jar")
    source = tmp_path / "player.gdc"
    source.write_bytes(b"not-a-gd-save")

    report = describe_gdstash_compatibility(source, parser_root=root)

    assert "GDStash.jar" in report.source
