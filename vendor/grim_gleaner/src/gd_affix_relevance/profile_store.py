"""Versioned JSON persistence for user-created build profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.io_utils import atomic_write_text

PROFILE_FILE_SCHEMA_VERSION = 4
SUPPORTED_PROFILE_FILE_SCHEMA_VERSIONS = frozenset({1, 2, 3, 4})
PROFILE_CORE_KEYS = frozenset(
    {
        "schema_version",
        "name",
        "weights",
        "masteries",
        "skill_weights",
        "excluded_conversion_sources",
        "resistance_cap_enabled",
        "resistance_cap_weights",
    }
)


class ProfileFormatError(ValueError):
    """A profile file is not valid or uses an unsupported schema."""


def save_profile(profile: BuildProfile, path: Path) -> Path:
    """Atomically save *profile* and return the normalized destination path."""

    destination = _with_json_suffix(Path(path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    passthrough: dict[str, Any] = {}
    if destination.is_file():
        try:
            existing_payload: Any = json.loads(
                destination.read_text(encoding="utf-8-sig")
            )
            if isinstance(existing_payload, dict):
                passthrough = {
                    key: value
                    for key, value in existing_payload.items()
                    if key not in PROFILE_CORE_KEYS
                }
        except (OSError, UnicodeError, json.JSONDecodeError):
            passthrough = {}

    payload = {
        **passthrough,
        "schema_version": PROFILE_FILE_SCHEMA_VERSION,
        **profile.to_dict(),
    }
    atomic_write_text(
        destination,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return destination


def load_profile(path: Path) -> BuildProfile:
    """Load and validate a build profile from *path*."""

    source = Path(path)
    try:
        payload: Any = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileFormatError(f"Could not read profile: {error}") from error
    if not isinstance(payload, dict):
        raise ProfileFormatError("Profile file must contain a JSON object")

    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in SUPPORTED_PROFILE_FILE_SCHEMA_VERSIONS
    ):
        raise ProfileFormatError(
            f"Unsupported profile schema version: {schema_version!r}"
        )
    try:
        return BuildProfile.from_dict(payload)
    except (TypeError, ValueError) as error:
        raise ProfileFormatError(f"Invalid profile data: {error}") from error


def _with_json_suffix(path: Path) -> Path:
    if path.suffix:
        return path
    return path.with_suffix(".json")
