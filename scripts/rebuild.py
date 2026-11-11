"""Rebuild in a temporary directory, validate, then publish. No model/API calls."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from build import build as build_raw
from build_v2 import build as build_app
from data_utils import ROOT, SCHEMA_VERSION, dump, load
from validate_data import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT.parent / "poems-db")
    parser.add_argument("--app-only", action="store_true", help="Reuse raw data; merge existing generation records")
    parser.add_argument("--check-only", action="store_true", help="Validate staged output without publishing")
    args = parser.parse_args()
    baseline = ROOT / "backups/pre-v3/app-data/poems.json"
    if not baseline.exists() and (ROOT / "app-data/poems.json").exists():
        snapshot = baseline.parent.parent
        if snapshot.exists():
            raise SystemExit("Incomplete backups/pre-v3 snapshot; preserve or repair it before rebuilding")
        snapshot.mkdir(parents=True)
        for name in ("app-data", "raw", "scripts"):
            if (ROOT / name).exists():
                shutil.copytree(ROOT / name, snapshot / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "README.md", snapshot / "README.md")
        dump(snapshot / "sha256.json", {str(p.relative_to(snapshot)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in snapshot.rglob("*") if p.is_file()})
    with tempfile.TemporaryDirectory(prefix=".stage-", dir=ROOT) as folder:
        staging = Path(folder).resolve()
        staging.relative_to(ROOT.resolve())  # Verify cleanup remains inside this workspace.
        app = staging / "app-data"
        app.mkdir()
        generated = ROOT / "app-data/generated.jsonl"
        if generated.exists():
            shutil.copy2(generated, app / generated.name)
        if args.app_only:
            raw = ROOT / "raw"
        else:
            raw = staging / "raw"
            build_raw(args.source_dir, raw)
            for name in ("editorial_fixes.json", "content_review.json", "author_overrides.json", "annotation_additions.jsonl", "content_reviews.jsonl", "review_triage.jsonl", "approved_review_edits.json", "review_resolutions.json", "final_content_decisions.json", "source_evidence.json", "famous_lines.json", "famous_line_selections.jsonl"):
                if (ROOT / "raw" / name).is_file():
                    shutil.copy2(ROOT / "raw" / name, raw / name)
        stats = build_app(raw, app, generated_path=app / "generated.jsonl")
        report = validate(app, baseline=baseline if baseline.exists() else None)
        current = load(ROOT / "app-data/manifest.json", {})
        staged_manifest = load(app / "manifest.json")
        report["rebuild_comparison"] = dict(
            current_data_version=current.get("data_version"),
            staged_data_version=staged_manifest["data_version"],
            manifest_identical=current == staged_manifest,
            changed_files=[name for name, info in staged_manifest["files"].items()
                           if current.get("files", {}).get(name, {}).get("sha256") != info["sha256"]])
        (ROOT / "reports").mkdir(exist_ok=True)
        dump(ROOT / "reports/staged-audit.json", report)
        print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
        if report["errors"]:
            raise SystemExit("Staging checks failed; existing dataset was not replaced. See reports/staged-audit.json")
        if args.check_only:
            print("Staging passed; --check-only kept the current dataset unchanged.")
            return
        if any((ROOT / "app-data" / name).exists() for name in ("poems.db-wal", "poems.db-shm")):
            raise SystemExit("Close current database users before publishing; SQLite sidecar files are present")
        # Each file is replaced only after the full staged package passes validation.
        # Run the builder while the App/backend is stopped; the package is a release artifact.
        for directory in ([raw] if not args.app_only else []) + [app]:
            target = ROOT / directory.name
            target.mkdir(exist_ok=True)
            for path in sorted(directory.iterdir()):
                if path.is_file():
                    os.replace(path, target / path.name)
        dump(ROOT / "reports/app-data-audit.json", report)
        print(f"Published schema v{SCHEMA_VERSION} data. Baseline remains in backups/pre-v3.")


if __name__ == "__main__":
    main()
