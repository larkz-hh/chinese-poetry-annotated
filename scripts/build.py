"""Build raw corpus from NDJSON, preserving distinct same-title works."""
import argparse
import gzip
import io
import json
import re
from pathlib import Path

from data_utils import ROOT, FIELDS, clean_lines, compact, dump, identity_body, load, source_key, unique, work_body

CURATED = {"唐诗三百首", "宋词三百首", "古诗三百首", "元曲三百首", "古文观止",
           "诗经", "乐府", "小学古诗", "初中古诗", "高中古诗"}


def norm(row):
    title = (row.get("name") or row.get("title") or "").strip()
    content = clean_lines(row.get("content"))
    if not title or not content:
        return None
    oid = row.get("_id")
    oid = oid.get("$oid") if isinstance(oid, dict) else oid
    if not oid:
        raise ValueError("Original record has no ID")
    collection = row.get("type") or ""
    if re.search(r"[\ue000-\uf8ff]|鍏|鐨|涓ゆ|銆", collection):
        collection = ""
    return dict(id=str(oid), title=title, author=(row.get("author") or "佚名").strip(),
                dynasty=(row.get("dynasty") or "未知").strip(), format=(row.get("format") or "").strip(),
                collection=collection, collections=[collection] if collection else [],
                tags=unique(t.strip() for t in row.get("tags", []) if isinstance(t, str)),
                content=content, **{k: clean_lines(row.get(k)) for k in FIELDS},
                reference=clean_lines(row.get("reference")), source=row.get("sourceLink") or "",
                sources=[row["sourceLink"]] if row.get("sourceLink") else [],
                source_ids=[str(oid)], aliases=[], alternate_contents=[])


def score(row):
    return sum(bool(row[k]) and compact(row[k]) != compact(row["content"]) for k in FIELDS)


def combine(left, right, preferred):
    def rank(row):
        return (row["id"] in preferred, -preferred.get(row["id"], 10**9), score(row))
    winner, other = (left, right) if rank(left) >= rank(right) else (right, left)
    for key in ("tags", "collections", "sources", "source_ids"):
        winner[key] = unique(winner[key] + other[key])
    winner["aliases"] = unique(winner["aliases"] + other["aliases"] + [other["title"]])
    winner["aliases"] = [s for s in winner["aliases"] if s != winner["title"]]
    for key in FIELDS:
        if not winner[key] or compact(winner[key]) == compact(winner["content"]):
            if other[key] and compact(other[key]) != compact(other["content"]):
                winner[key] = other[key]
    alternates = winner["alternate_contents"] + other["alternate_contents"]
    if identity_body(winner["content"]) != identity_body(other["content"]):
        alternates.append(dict(source_id=other["id"], content=other["content"], source=other["source"]))
    seen = {identity_body(winner["content"])}
    winner["alternate_contents"] = []
    for alternative in alternates:
        key = identity_body(alternative["content"])
        if key not in seen:
            seen.add(key)
            winner["alternate_contents"].append(alternative)
    return winner


def build(source, output, legacy_path=ROOT / "app-data/poems.json"):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    legacy = load(legacy_path, [])
    preferred = {p["id"]: i for i, p in enumerate(legacy)}
    selection = load(ROOT / "raw/selection.json")
    if selection is None:
        baseline = load(ROOT / "backups/pre-v3/app-data/poems.json", legacy)
        selection = dict(same_title_scope=sorted({(p.get("source_title", p["title"]), p["author"]) for p in baseline}))
    legacy_titles = {tuple(item) for item in selection["same_title_scope"]}
    # Merged variants may lose their own App ID and have neither curated tags
    # nor an exact baseline title. Explicit review references remain in scope.
    reviewed_ids = set(load(ROOT / "raw/content_review.json", {}).get("works", {}))
    dump(output / "selection.json", selection)
    records, by_source, by_body, redirects = {}, {}, {}, {}

    def root(index):
        while index in redirects:
            index = redirects[index]
        return index

    count = dropped = 0
    for number in range(1, 5):
        path = source / f"poems{number}.json"
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = norm(json.loads(line))
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc
                count += 1
                if not row:
                    dropped += 1
                    continue
                sk = (row["author"], source_key(row["source"])) if row["source"] else None
                bk = (row["author"], row["dynasty"], work_body(row["content"]))
                matches = {root(value) for value in (by_source.get(sk), by_body.get(bk)) if value is not None}
                index = min(matches) if matches else count
                for other_index in sorted(matches - {index}):
                    records[index] = combine(records[index], records.pop(other_index), preferred)
                    redirects[other_index] = index
                records[index] = combine(records[index], row, preferred) if index in records else row
                if sk:
                    by_source[sk] = index
                by_body[bk] = index
        print(f"Read {path.name}: {count} records", flush=True)
    poems = sorted(records.values(), key=lambda p: p["id"])
    lite = [p for p in poems if CURATED.intersection(p["tags"] + p["collections"])
            or p["appreciation"] or (p["title"], p["author"]) in legacy_titles
            or (preferred.keys() | reviewed_ids) & set(p["source_ids"])]
    lite.sort(key=lambda p: (-len(p["appreciation"]), -len(p["translate"]), p["title"], p["id"]))
    with (output / "poems_all.jsonl.gz").open("wb") as binary, \
            gzip.GzipFile(filename="", fileobj=binary, mode="wb", mtime=0) as compressed, \
            io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as handle:
        for poem in poems:
            handle.write(json.dumps(poem, ensure_ascii=False) + "\n")
    dump(output / "poems_lite.json", lite)
    annotated = [p for p in poems if all(p[k] and compact(p[k]) != compact(p["content"]) for k in FIELDS)]
    dump(output / "seed_annotated.json", annotated)
    authors = {}
    with (source / "poems-authors.json").open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            name = (row.get("name") or "").strip()
            if not name:
                continue
            oid = row.get("_id", {})
            author = dict(id=oid.get("$oid", "") if isinstance(oid, dict) else str(oid), name=name,
                          dynasty=(row.get("dynasty") or "").strip(),
                          lifetime="\n".join(clean_lines(row.get("lifetime"))),
                          works=int(row.get("quantity") or 0), avatar=row.get("avatar") or "",
                          describe=[dict(type=d.get("type", ""), content=clean_lines(d.get("content")))
                                    for d in row.get("describe", []) if isinstance(d, dict)])
            key = (name, author["dynasty"])
            if key not in authors or len(author["lifetime"]) > len(authors[key]["lifetime"]):
                authors[key] = author
    dump(output / "authors.json", sorted(authors.values(), key=lambda a: (-a["works"], a["name"])))
    cipai = []
    with (source / "poems-cipai.json").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cipai.append(json.loads(line)["name"])
    dump(output / "cipai.json", sorted(set(cipai)))
    report = dict(original_records=count, dropped_empty=dropped, merged_records=count-dropped-len(poems),
                  works=len(poems), lite=len(lite), authors=len(authors),
                  identity_rule="same author + source URL, or same author/dynasty + normalized body; never title alone")
    dump(output / "build-report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT.parent / "poems-db")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "raw")
    args = parser.parse_args()
    print(json.dumps(build(args.source_dir, args.output_dir), ensure_ascii=False, indent=2))
