"""
Command-line interface for ga4gh2abusua.

Reconstruct an Abusua Pedigree Studio session (.json) from a GA4GH Pedigree
Standard message and/or a Phenopackets v2 Family.

Examples
--------
From both inputs (most complete)::

    ga4gh2abusua --family fam.family.json --pedigree fam.ga4gh-pedigree.json -o fam.json

From a Family alone::

    ga4gh2abusua --family fam.family.json -o fam.json

From a GA4GH Pedigree alone, printing to stdout::

    ga4gh2abusua --pedigree fam.ga4gh-pedigree.json --stdout
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Optional

from .convert import to_abusua_session


def _load(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _emit_warnings(warns: List[str], stream=sys.stderr) -> None:
    if warns:
        print(f"[notes] {len(warns)}:", file=stream)
        for w in warns:
            print(f"  - {w}", file=stream)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ga4gh2abusua",
        description="Reconstruct an Abusua session from a GA4GH Pedigree and/or Phenopackets Family.")
    ap.add_argument("--family", help="Path to a Phenopackets v2 Family JSON file")
    ap.add_argument("--pedigree", help="Path to a GA4GH Pedigree Standard JSON file")
    ap.add_argument("-o", "--out", help="Output path for the Abusua .json session")
    ap.add_argument("--stdout", action="store_true",
                    help="Print the session to stdout instead of writing a file")
    ap.add_argument("--family-id", default=None,
                    help="Override the family id used in the session")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default: 2)")
    args = ap.parse_args(argv)

    if not args.family and not args.pedigree:
        print("error: provide at least one of --family or --pedigree", file=sys.stderr)
        return 2

    try:
        family = _load(args.family)
        pedigree = _load(args.pedigree)
    except Exception as e:  # noqa: BLE001
        print(f"error: could not read input: {e}", file=sys.stderr)
        return 2

    session, warns = to_abusua_session(
        ga4gh_pedigree=pedigree, family=family, family_id=args.family_id)
    _emit_warnings(warns)

    text = json.dumps(session, indent=args.indent)

    if args.stdout or not args.out:
        if not args.out:
            # default to a sensible filename derived from an input when not piping
            if not args.stdout:
                stem = pathlib.Path(args.family or args.pedigree).stem
                # strip our known suffixes
                for suff in (".family", ".ga4gh-pedigree", ".pedigree"):
                    if stem.endswith(suff):
                        stem = stem[: -len(suff)]
                out_path = pathlib.Path(stem + ".json")
                out_path.write_text(text, encoding="utf-8")
                print(f"wrote {out_path}")
                return 0
        print(text)
        return 0

    out_path = pathlib.Path(args.out)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
