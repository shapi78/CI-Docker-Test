#!/usr/bin/env python3
"""
gen-deps.py — regenerate an umbrella chart's `dependencies:` section from the
subcharts under charts/, taking each dependency's version from that subchart's
own Chart.yaml.

Behaviour:
  * Existing dependency entries are updated IN PLACE — only the version is
    refreshed; condition / alias / tags / repository / comments are preserved.
  * Subcharts with no existing entry are appended.
  * Dependencies that have NO matching folder (e.g. remote charts pulled from
    Artifactory) are left untouched, unless --prune is given, which removes
    only stale *local* file:// entries.

Run `helm dependency update <root>` afterwards to refresh Chart.lock.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ
except ImportError:
    sys.exit("This script needs ruamel.yaml:  pip install ruamel.yaml")


def load_subcharts(charts_dir: Path):
    """Return [(folder, chart_name, version)] for each immediate subchart."""
    reader = YAML(typ="safe")
    found = []
    if not charts_dir.is_dir():
        return found
    for sub in sorted(p for p in charts_dir.iterdir() if p.is_dir()):
        cf = sub / "Chart.yaml"
        if not cf.exists():
            continue
        meta = reader.load(cf.read_text()) or {}
        version = meta.get("version")
        if version is None:
            print(f"  WARN: {cf} has no 'version' — skipping", file=sys.stderr)
            continue
        found.append((sub.name, str(meta.get("name", sub.name)), str(version)))
    return found


def is_local_file_repo(repo) -> bool:
    return isinstance(repo, str) and repo.startswith("file://") and "charts/" in repo


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Regenerate root Chart.yaml dependencies from charts/ subcharts."
    )
    ap.add_argument("-r", "--root", default=".", help="umbrella chart root (default: .)")
    ap.add_argument(
        "--repo",
        default="file://charts/{dir}",
        help="repository for NEW deps; {dir} and {name} are substituted "
        "(default: file://charts/{dir}). Use '@myco' or "
        "'oci://host/helm-local' for an Artifactory-backed umbrella.",
    )
    ap.add_argument(
        "--prune",
        action="store_true",
        help="drop existing local file:// deps whose folder no longer exists",
    )
    ap.add_argument("--dry-run", action="store_true", help="print result, do not write")
    args = ap.parse_args()

    root = Path(args.root)
    chart_file = root / "Chart.yaml"
    if not chart_file.is_file():
        return _err(f"no Chart.yaml at '{root}'")

    subcharts = load_subcharts(root / "charts")
    if not subcharts:
        return _err(f"no subcharts with a Chart.yaml under '{root}/charts'")

    yaml = YAML()  # round-trip: preserves comments, quoting and key order
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(chart_file.read_text()) or CommentedMap()

    deps = data.get("dependencies")
    if not isinstance(deps, (list, CommentedSeq)):
        deps = CommentedSeq()
        data["dependencies"] = deps

    by_name = {d.get("name"): d for d in deps if isinstance(d, dict)}
    folder_chart_names = {name for _, name, _ in subcharts}

    added, updated = [], []
    for folder, name, version in subcharts:
        entry = by_name.get(name)
        if entry is not None:  # update in place, keep everything else
            if str(entry.get("version")) != version:
                updated.append((name, entry.get("version"), version))
            entry["version"] = DQ(version)
            if not entry.get("repository"):
                entry["repository"] = DQ(args.repo.format(dir=folder, name=name))
        else:  # brand-new subchart
            entry = CommentedMap()
            entry["name"] = name
            entry["version"] = DQ(version)
            entry["repository"] = DQ(args.repo.format(dir=folder, name=name))
            deps.append(entry)
            added.append(name)

    pruned = []
    if args.prune:
        kept = CommentedSeq()
        for d in deps:
            nm = d.get("name") if isinstance(d, dict) else None
            repo = d.get("repository") if isinstance(d, dict) else None
            if nm not in folder_chart_names and is_local_file_repo(repo):
                pruned.append(nm)
                continue
            kept.append(d)
        data["dependencies"] = kept

    for n, old, new in updated:
        print(f"  update  {n}: {old} -> {new}")
    for n in added:
        print(f"  add     {n}")
    for n in pruned:
        print(f"  prune   {n}")
    if not (updated or added or pruned):
        print("  no changes (already in sync)")

    if args.dry_run:
        print("\n--- dry run (not written) ---")
        yaml.dump(data, sys.stdout)
        return 0

    with chart_file.open("w") as fh:
        yaml.dump(data, fh)
    print(f"\nWrote {chart_file}.  Next: helm dependency update {root}")
    return 0


def _err(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
