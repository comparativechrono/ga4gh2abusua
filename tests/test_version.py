"""The version in pyproject.toml and the package's __version__ must agree."""
import os
import re

import ga4gh2abusua

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_versions_agree():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        version = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M).group(1)
    assert ga4gh2abusua.__version__ == version
