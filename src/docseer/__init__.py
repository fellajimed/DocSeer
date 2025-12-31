# from platformdirs import user_cache_path
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError


# CACHE_FOLDER = user_cache_path("docseer")
CACHE_FOLDER = Path(__file__).resolve().absolute().parents[2] / ".cache"
CACHE_FOLDER.mkdir(parents=True, exist_ok=True)


try:
    __version__ = version("docseer")
except PackageNotFoundError:
    __version__ = "0.0.0"


__all__ = ["CACHE_FOLDER"]
