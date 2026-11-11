"""Safe, parameterized search against a read-only schema v3 package."""
import argparse
import json
import sqlite3
from pathlib import Path

from data_utils import ROOT, match_query
from runtime_db import APPLICATION_ID


def search(database, keyword, column=None, limit=20, offset=0):
    if not isinstance(limit, int) or not 1 <= limit <= 100 or not isinstance(offset, int) or offset < 0:
        raise ValueError("limit must be 1..100; offset must be nonnegative")
    query = match_query(keyword, column)
    if not query:
        return []
    con = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        runtime = con.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
        join = "p.rowid=poems_fts.rowid" if runtime else "p.id=poems_fts.pid"
        return [dict(row) for row in con.execute(f"""
            SELECT p.id,p.title,p.author,p.dynasty,p.genre,p.complete
            FROM poems_fts JOIN poems p ON {join}
            WHERE poems_fts MATCH ?
            ORDER BY bm25(poems_fts,0,10,5,1),p.id LIMIT ? OFFSET ?
            """, (query, limit, offset))]
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword")
    parser.add_argument("--column", choices=("title", "author", "content"))
    parser.add_argument("--db", type=Path, default=ROOT / "app-data/poems.db")
    args = parser.parse_args()
    print(json.dumps(search(args.db, args.keyword, args.column), ensure_ascii=False, indent=2))
