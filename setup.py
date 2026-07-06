"""Legacy setup.py shim for setuptools < 61 (no PEP 621 support).

Modern setuptools (>=61) reads all package metadata from pyproject.toml's
[project] table and ignores the args passed here. This shim exists only so that
older setuptools (notably the 59.5.0 pinned in Yocto kirkstone) can build a
wheel with correct name, version, packages, and console script from the sdist.
Without it, the legacy build reads nothing from [tool.setuptools.packages.find]
or [project.scripts] and emits a wheel with the right name/version but zero
modules and no cta2045-proxy entry point (see the python-cta2045 / python-sdk
kirkstone history for the full saga).

find_packages is used so every subpackage (cta2045_proxy.ucm, ...) is included;
a hand-listed packages=["cta2045_proxy"] would silently drop them. The version
is read from the package so it cannot drift; bump it in
src/cta2045_proxy/__init__.py (and keep pyproject.toml's [project].version in
sync for the modern build path).
"""

import re
from pathlib import Path

from setuptools import find_packages, setup

version = re.search(
    r'^__version__ = "([^"]+)"',
    Path("src/cta2045_proxy/__init__.py").read_text(encoding="utf-8"),
    re.M,
).group(1)

setup(
    name="cta2045-proxy",
    version=version,
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={
        "console_scripts": [
            "cta2045-proxy = cta2045_proxy.cli:main",
        ],
    },
)
