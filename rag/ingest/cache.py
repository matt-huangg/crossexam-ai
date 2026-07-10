"""Read/write helpers for the two local ingestion cache layers.

  data/raw/       — raw HTML/XML as fetched from the source sites
  data/processed/ — parsed LegalSection / LegalChunk records as JSON

Both directories are gitignored (see repo .gitignore); only .gitkeep is
tracked. Delete cached files to force a fresh fetch on the next run.
"""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from models import LegalSection

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

T = TypeVar("T", bound=BaseModel)


def ensure_data_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_models(path: Path, model: type[T]) -> list[T] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return [model.model_validate(item) for item in data]


def save_models(path: Path, records: list[BaseModel]) -> None:
    ensure_data_dirs()
    payload = [record.model_dump() for record in records]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_processed(path: Path) -> list[LegalSection] | None:
    return load_models(path, LegalSection)


def save_processed(path: Path, sections: list[LegalSection]) -> None:
    save_models(path, sections)


def load_raw_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_raw_text(path: Path, text: str) -> None:
    ensure_data_dirs()
    path.write_text(text, encoding="utf-8")


def load_meta(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(path: Path, meta: dict) -> None:
    ensure_data_dirs()
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
