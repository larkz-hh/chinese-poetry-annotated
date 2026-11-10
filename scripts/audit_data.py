"""Audit the current schema v3 package, writing only the requested report directory."""
import argparse
import json
from pathlib import Path

from data_utils import ROOT, dump
from validate_data import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, default=ROOT / "app-data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    report = validate(args.app_dir, baseline=ROOT / "backups/pre-v3/app-data/poems.json")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dump(args.output_dir / "app-data-audit.json", report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
