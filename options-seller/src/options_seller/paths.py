"""Server-owned runtime storage, independent of the launcher's working directory."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    value = Path(os.environ.get("PULSE_DATA_DIR", PROJECT_ROOT / "data")).expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value
