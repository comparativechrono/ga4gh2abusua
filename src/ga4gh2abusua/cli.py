"""Command line: ga4gh2abusua FILE [-o SESSION.json]

FILE is a GA4GH Pedigree or a Phenopackets Family. The options of version
0.3, ``--pedigree FILE`` and ``--family FILE``, still work, and can be given
together: the GA4GH Pedigree is then read first and the Family fills in what
it lacks.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Optional

from pedigree_ga4gh import detect
from pedigree_ga4gh.io import load

from . import __version__
from .convert import LegacyFileError, to_abusua_session

_SUFFIXES = (".ga4gh-pedigree.json", "_ga4gh-pedigree.json", ".family.json", "_phenopackets-family.json",
             ".pedigree.json", ".json")


def default_output(source: str) -> pathlib.Path:
    """``asante.ga4gh-pedigree.json`` -> ``asante.json``, in the current folder, as in version 0.3."""
    name = pathlib.Path(source).name
    for suffix in _SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    return pathlib.Path(name + ".json")


def _emit(notes: List[str]) -> None:
    if notes:
        print("[notes] {}:".format(len(notes)), file=sys.stderr)
        for n in notes:
            print("  - {}".format(n), file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ga4gh2abusua",
        description="Rebuild an Abusua Pedigree Studio session from a GA4GH Pedigree or a Phenopackets Family.")
    ap.add_argument("input", nargs="?", help="a GA4GH Pedigree or a Phenopackets Family (.json)")
    ap.add_argument("--pedigree", help="a GA4GH Pedigree (version 0.3's option)")
    ap.add_argument("--family", help="a Phenopackets Family (version 0.3's option)")
    ap.add_argument("-o", "--out", help="the session to write (default: the input's name, in the current folder; "
                                         "an existing file of that name is not replaced unless you give --force)")
    ap.add_argument("--force", action="store_true", help="replace the default output file if it already exists")
    ap.add_argument("--stdout", action="store_true", help="print the session instead of writing a file")
    ap.add_argument("--family-id", default=None, help="the family id to give the session")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default: 2)")
    ap.add_argument("--version", action="version", version="ga4gh2abusua " + __version__)
    args = ap.parse_args(argv)

    if not (args.input or args.pedigree or args.family):
        print("ga4gh2abusua: give a GA4GH Pedigree or a Phenopackets Family", file=sys.stderr)
        return 2
    pedigree_path, family_path = args.pedigree, args.family
    try:
        if args.input:
            kind = detect(load(args.input))
            if kind not in ("family", "pedigree"):
                print("ga4gh2abusua: {} is not a GA4GH Pedigree or a Phenopackets Family".format(args.input),
                      file=sys.stderr)
                return 2
            if (family_path if kind == "family" else pedigree_path):
                print("ga4gh2abusua: two {} were given".format(
                    "Families" if kind == "family" else "GA4GH Pedigrees"), file=sys.stderr)
                return 2
            if kind == "family":
                family_path = args.input
            else:
                pedigree_path = args.input
        pedigree = load(pedigree_path) if pedigree_path else None
        family = load(family_path) if family_path else None
    except FileNotFoundError as exc:
        print("ga4gh2abusua: cannot find {}".format(exc.filename), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("ga4gh2abusua: could not read the file: {}".format(exc), file=sys.stderr)
        return 2

    try:
        session, notes = to_abusua_session(ga4gh_pedigree=pedigree, family=family, family_id=args.family_id)
    except LegacyFileError as exc:
        print("ga4gh2abusua: {}".format(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print("ga4gh2abusua: {}".format(exc), file=sys.stderr)
        return 1
    _emit(notes)
    text = json.dumps(session, indent=args.indent, ensure_ascii=False) + "\n"
    if args.stdout:
        sys.stdout.write(text)
        return 0
    out = pathlib.Path(args.out) if args.out else default_output(pedigree_path or family_path)
    inputs = {pathlib.Path(p).resolve() for p in (pedigree_path, family_path) if p}
    if out.resolve() in inputs:
        print("ga4gh2abusua: {} is the file being read; give the session another name with -o".format(out),
              file=sys.stderr)
        return 2
    if not args.out and out.exists() and not args.force:
        # the default name is the session's own (asante.json for asante.ga4gh-pedigree.json), which may well be
        # the session these files came from, with its names and notes: never replace it unasked
        print("ga4gh2abusua: {} already exists (it may be the session the file came from); give -o to choose "
              "another name, or --force to replace it".format(out), file=sys.stderr)
        return 2
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    people = len(session["people"])
    print("{} {}, {} union{}.".format(people, "person" if people == 1 else "people", len(session["unions"]),
                                      "" if len(session["unions"]) == 1 else "s"))
    print("  wrote {}".format(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
