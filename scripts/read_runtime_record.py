"""Read a complete original record from the App database, including its audit."""
import argparse
import json
from pathlib import Path

from data_utils import ROOT
from runtime_db import APPLICATION_ID, connect_readonly, read_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("poem", "author", "package"))
    parser.add_argument("id")
    parser.add_argument("--db", type=Path, default=ROOT / "app-runtime/poems.db")
    args = parser.parse_args()
    con = connect_readonly(args.db)
    try:
        if con.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise ValueError("Expected an App runtime database")
        rid = args.id
        if args.kind == "poem":
            alias = con.execute("SELECT poem_id FROM id_aliases WHERE old_id=?", (rid,)).fetchone()
            if alias:
                rid = alias[0]
        record = read_archive(con, args.kind, rid)
        print(json.dumps(record, ensure_ascii=False, indent=2))
    finally:
        con.close()


if __name__ == "__main__":
    main()
