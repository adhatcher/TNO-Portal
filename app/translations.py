"""Load translations from JSON files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

I18N_DIR = Path(__file__).with_name("i18n")
LANGUAGE_NAMES_PATH = I18N_DIR / "languages.json"


def _load_json(path: Path) -> dict[str, str]:
    """Load a translation mapping from disk."""

    with path.open(encoding="utf-8") as file:
        return json.load(file)


@lru_cache
def load_language_names() -> dict[str, str]:
    """Return the configured language display names."""

    return _load_json(LANGUAGE_NAMES_PATH)


@lru_cache
def load_translations() -> dict[str, dict[str, str]]:
    """Return all configured translation mappings."""

    translations: dict[str, dict[str, str]] = {}
    for path in sorted(I18N_DIR.glob("*.json")):
        if path.name == LANGUAGE_NAMES_PATH.name:
            continue
        translations[path.stem] = _load_json(path)
    return translations


LANGUAGE_NAMES = load_language_names()
TRANSLATIONS = load_translations()
