from __future__ import annotations

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore


def load(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)
