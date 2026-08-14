from __future__ import annotations

from pathlib import Path
import zlib

from gd_affix_relevance.importers.character_save_parser import (
    describe_gdstash_compatibility,
    extract_skill_references,
    parse_character_save,
)


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


def test_parse_character_save_reports_partial_parse_and_diagnostics(
    tmp_path: Path,
) -> None:
    source = tmp_path / "player.gdc"
    source.write_bytes(b"not-a-gd-save")

    result = parse_character_save(source)

    assert result.references == ()
    assert result.metadata.partial_parse
    assert result.metadata.references_found == 0
    assert result.metadata.files_scanned == ("player.gdc",)
    assert result.metadata.confidence < 0.5
    assert any(
        diag.code == "unknown_character_version"
        for diag in result.metadata.diagnostics
    )


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
