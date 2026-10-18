"""ga4gh2abusua: rebuild Abusua Pedigree Studio sessions from GA4GH files.

It reads a GA4GH Pedigree or a Phenopackets Family through pedigree-ga4gh,
the one GA4GH implementation the lab's pedigree tools share, and is the
reverse of abusua2ga4gh: a session converted to GA4GH and back keeps its
family, its parentage (biological and social) and its conditions.

Quick start::

    import json
    from ga4gh2abusua import to_abusua_session

    with open("asante.ga4gh-pedigree.json") as fh:
        pedigree = json.load(fh)
    session, notes = to_abusua_session(ga4gh_pedigree=pedigree)

Or from the command line::

    ga4gh2abusua asante.ga4gh-pedigree.json -o asante.json
"""
from __future__ import annotations

__version__ = "0.4.0"

from .convert import (LegacyFileError, apply_family, apply_ga4gh_pedigree, apply_kindred,  # noqa: E402
                      read_notes, to_abusua_session, to_session)
from .session import BuildPerson, SessionBuilder  # noqa: E402

__all__ = [
    "to_abusua_session",
    "to_session",
    "apply_ga4gh_pedigree",
    "apply_family",
    "apply_kindred",
    "read_notes",
    "LegacyFileError",
    "SessionBuilder",
    "BuildPerson",
    "__version__",
]
