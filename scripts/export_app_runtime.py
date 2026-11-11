"""Build a separate, lossless SQLite package for an App. Never modify app-data."""
import argparse
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path

from data_utils import ROOT, SCHEMA_VERSION, dump, load
from runtime_db import APPLICATION_ID, RUNTIME_SCHEMA, ARCHIVE_CODEC, connect_readonly, write_runtime, validate_runtime


def verify_source(source):
    manifest = load(source / "manifest.json")
    if not manifest or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Expected full schema v{SCHEMA_VERSION} source package")
    for name, info in manifest["files"].items():
        if Path(name).name != name or hashlib.sha256((source / name).read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError(f"Source checksum failed: {name}")
    return manifest


def verify_search(runtime, full, poems):
    from search import search
    queries = [("明月", None), ("床前明月光", "content"), ("𠮷", None), ("静夜思", "title"),
        ("除放", "title"), ("除夜自石湖归苕溪", "title"), ("国色返春魂", "content"),
        ("李白", "author"), ("香莲", "title"), ("则明月", "content"), ('" OR *', None), ("", None),
        ("春", None), ("月", "content")]
    queries += [(p["title"], "title") for p in poems[::60]]
    for keyword, column in queries:
        if search(runtime, keyword, column) != search(full, keyword, column):
            raise ValueError(f"Runtime search differs: {keyword}:{column}")
    if search(runtime, "月", limit=5, offset=5) != search(full, "月", limit=5, offset=5):
        raise ValueError("Runtime search pagination differs")
    return len(queries) + 1


def export(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError("App runtime output must be separate from the full source package")
    # An existing unrelated database may never be overwritten by this exporter.
    if (output / "poems.db").exists() and load(output / "manifest.json", {}).get("profile") != "app-runtime":
        raise ValueError("Output contains a database that is not an App runtime export")
    if (output / "poems.db").exists():
        con = connect_readonly(output / "poems.db")
        try:
            if con.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise ValueError("Output database signature is not an App runtime export")
        finally:
            con.close()
    manifest = verify_source(source)
    poems, authors, aliases, evidence = [load(source / name) for name in ("poems.json", "authors.json", "id_map.json", "source_evidence.json")]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stage-runtime-", dir=output.parent) as folder:
        stage = Path(folder).resolve()
        stage.relative_to(output.parent)
        database = stage / "poems.db"
        write_runtime(database, poems, authors, aliases, manifest, evidence)
        report = validate_runtime(database, poems, authors, aliases, manifest, evidence)
        report["search_comparisons"] = verify_search(database, source / "poems.db", poems)
        report["search_results_equal"] = True
        payload = database.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        full_bytes = (source / "poems.db").stat().st_size
        meta = dict(profile="app-runtime", runtime_schema=RUNTIME_SCHEMA, application_id=APPLICATION_ID,
            source_data_version=manifest["data_version"], data_version=f"runtime{RUNTIME_SCHEMA}.{digest[:16]}",
            read_only_corpus=True, counts={k: report[k] for k in ("poems", "authors", "editions", "units", "aliases", "cautions", "author_sections", "famous_lines", "poems_with_famous_lines")},
            famous_lines_policy=manifest.get("famous_lines_policy", {}),
            files={"poems.db":dict(bytes=len(payload), sha256=digest)},
            source_package_sha256=hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest(),
            preservation="All poem/author fields and source evidence preserved; full metadata uses text references plus zlib compression",
            archive=dict(table="record_archives", codec=ARCHIVE_CODEC, kinds=["poem", "author", "package"]),
            search=dict(fts5=True, contentless=True, join="poems.rowid = poems_fts.rowid", query_helper="scripts/search.py"))
        dump(stage / "manifest.json", meta, newline="\n")
        report.update(database_bytes=len(payload), full_database_bytes=full_bytes,
            reduction_percent=round(100 * (1-len(payload)/full_bytes), 2),
            gzip_bytes=len(gzip.compress(payload, compresslevel=6, mtime=0)), data_version=meta["data_version"])
        if verify_source(source) != manifest:
            raise ValueError("Source package changed during export")
        report["source_package_unchanged"] = True
        if any((output / name).exists() for name in ("poems.db-wal", "poems.db-shm")):
            raise ValueError("Close runtime database connections before replacing the export")
        # A validated read-only release; full source files are never opened for writing.
        for name in ("poems.db", "manifest.json"):
            os.replace(stage / name, output / name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "app-data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "app-runtime")
    args = parser.parse_args()
    report = export(args.source_dir, args.output_dir)
    (ROOT / "reports").mkdir(exist_ok=True)
    dump(ROOT / "reports/app-runtime-audit.json", report, newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
