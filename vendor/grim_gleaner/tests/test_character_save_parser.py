from __future__ import annotations

from pathlib import Path

from gd_affix_relevance.importers.character_save_parser import (
    extract_skill_references,
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
