import hashlib
from pathlib import Path

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)


def get_cache_path(file_path):
    digest = hashlib.md5(
        Path(file_path).read_bytes()
    ).hexdigest()

    return CACHE_DIR / f"{digest}.txt"