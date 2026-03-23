"""Generate translation drafts from English strings using Ollama."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = REPO_ROOT / "app" / "i18n"
LANGUAGE_NAMES_PATH = I18N_DIR / "languages.json"
DEFAULT_ENV_PATH = REPO_ROOT / ".env.ollama"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Generate translation drafts from app/i18n/en.json using Ollama.",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        help="Target language codes to update. Defaults to all non-English languages.",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="Path to a local env file. Defaults to .env.ollama in the repo root.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name. Defaults to OLLAMA_MODEL from the env file or environment, then llama3.1.",
    )
    parser.add_argument(
        "--ollama-url",
        default=None,
        help="Ollama base URL. Defaults to OLLAMA_URL from the env file or environment, then http://localhost:11434.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate all keys instead of only filling missing ones.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Model temperature for translation generation.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Request timeout in seconds.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated translations instead of writing files.",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs into the process environment."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_json(path: Path) -> dict[str, str]:
    """Read a JSON object from disk."""

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, payload: dict[str, str]) -> None:
    """Write a JSON object to disk."""

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def choose_targets(requested_targets: list[str] | None, language_names: dict[str, str]) -> list[str]:
    """Choose which language files to update."""

    valid_targets = [code for code in language_names if code != "en"]
    if not requested_targets:
        return valid_targets

    unknown_targets = sorted(set(requested_targets) - set(language_names))
    if unknown_targets:
        raise SystemExit(f"Unknown language codes: {', '.join(unknown_targets)}")
    return [code for code in requested_targets if code != "en"]


def build_prompt(source_strings: dict[str, str], target_code: str, target_name: str) -> str:
    """Build a strict translation prompt for Ollama."""

    return (
        "You are translating UI strings for a Flask web app.\n"
        f"Translate the JSON values from English into {target_name} ({target_code}).\n"
        "Rules:\n"
        "- Return JSON only.\n"
        "- Keep every key exactly the same.\n"
        "- Preserve placeholders like {user} and {entity} exactly.\n"
        "- Preserve product names, alliance names, and abbreviations like TNO, TON, TCF, and Main.\n"
        "- Keep short button labels concise.\n"
        "- Do not add explanations or comments.\n"
        f"JSON to translate:\n{json.dumps(source_strings, ensure_ascii=True, sort_keys=True)}"
    )


def request_translation(
    source_strings: dict[str, str],
    target_code: str,
    target_name: str,
    model: str,
    ollama_url: str,
    temperature: float,
    timeout: int,
) -> dict[str, str]:
    """Call Ollama and return translated strings."""

    prompt = build_prompt(source_strings, target_code, target_name)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
        },
    }
    request = Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise SystemExit(f"Ollama request failed with HTTP {error.code}") from error
    except URLError as error:
        raise SystemExit(f"Unable to reach Ollama at {ollama_url}: {error.reason}") from error

    raw_response = body.get("response", "")
    try:
        translated = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise SystemExit("Ollama returned invalid JSON. Try a stronger model or rerun with --force.") from error

    if set(translated) != set(source_strings):
        missing = sorted(set(source_strings) - set(translated))
        extra = sorted(set(translated) - set(source_strings))
        details: list[str] = []
        if missing:
            details.append(f"missing keys: {', '.join(missing)}")
        if extra:
            details.append(f"extra keys: {', '.join(extra)}")
        raise SystemExit(f"Ollama returned an invalid translation payload ({'; '.join(details)}).")

    return {key: str(value) for key, value in translated.items()}


def main() -> int:
    """Generate one or more translation files."""

    args = parse_args()
    load_env_file(Path(args.env_file))
    ollama_url = args.ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = args.model or os.getenv("OLLAMA_MODEL", "llama3.1")
    language_names = load_json(LANGUAGE_NAMES_PATH)
    english_strings = load_json(I18N_DIR / "en.json")
    targets = choose_targets(args.targets, language_names)

    for target_code in targets:
        target_path = I18N_DIR / f"{target_code}.json"
        existing_strings = load_json(target_path) if target_path.exists() else {}
        source_subset = english_strings if args.force else {
            key: value for key, value in english_strings.items() if key not in existing_strings
        }
        if not source_subset:
            print(f"{target_code}: no missing keys")
            continue

        translated_subset = request_translation(
            source_subset,
            target_code,
            language_names[target_code],
            model,
            ollama_url,
            args.temperature,
            args.timeout,
        )
        merged_strings = dict(existing_strings)
        merged_strings.update(translated_subset)

        if args.dry_run:
            print(f"--- {target_code}")
            print(json.dumps(translated_subset, indent=2, ensure_ascii=True, sort_keys=True))
            continue

        save_json(target_path, merged_strings)
        print(f"{target_code}: wrote {len(translated_subset)} key(s) to {target_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
