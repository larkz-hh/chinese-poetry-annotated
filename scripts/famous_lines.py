"""Curated excerpts with stable IDs and exact primary-edition unit bindings."""
import copy
from urllib.parse import urlparse


FAMOUS_LINE_SCHEMA = """
CREATE TABLE famous_lines(
 id TEXT PRIMARY KEY,poem_id TEXT NOT NULL REFERENCES {poem_table}(id),
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),text TEXT NOT NULL,source_url TEXT NOT NULL,
 UNIQUE(poem_id,ordinal));
CREATE TABLE famous_line_units(
 quote_id TEXT NOT NULL REFERENCES famous_lines(id),ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 unit_id TEXT NOT NULL REFERENCES poem_units(id),PRIMARY KEY(quote_id,ordinal),
 UNIQUE(quote_id,unit_id)) WITHOUT ROWID;
"""


def validate_famous_lines(poems):
    seen = set()
    for poem in poems:
        pid = poem['id']
        quotes = poem.get('famous_lines')
        if not isinstance(quotes, list):
            raise ValueError(f'Missing or invalid famous_lines array: {pid}')
        primary = [e for e in poem['editions'] if e['is_primary']]
        if len(primary) != 1:
            raise ValueError(f'A unique primary edition is required: {pid}')
        units = primary[0]['units']
        positions = {u['id']: i for i, u in enumerate(units)}
        texts = set()
        for quote in quotes:
            if not isinstance(quote, dict) or set(quote) != {'id', 'text', 'unit_ids', 'source_url'}:
                raise ValueError(f'Invalid famous line fields: {pid}')
            qid, text, ids, source = (quote[k] for k in ('id', 'text', 'unit_ids', 'source_url'))
            if (not isinstance(qid, str) or not qid.startswith(pid + ':q') or not qid[len(pid)+2:]
                    or qid in seen or not isinstance(text, str) or not text.strip()
                    or text != text.strip() or '\ufffd' in text or text in texts):
                raise ValueError(f'Invalid or duplicate famous line: {pid}')
            if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids)
                    or len(set(ids)) != len(ids) or any(i not in positions for i in ids)):
                raise ValueError(f'Unknown or non-primary famous line units: {qid}')
            indexes = [positions[i] for i in ids]
            if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
                raise ValueError(f'Famous line units are not contiguous and ordered: {qid}')
            parts = [units[i]['text'] for i in indexes]
            joined = ''.join(parts)
            start = joined.find(text)
            if (start < 0 or joined.count(text) != 1 or start >= len(parts[0])
                    or start + len(text) <= len(joined) - len(parts[-1])):
                raise ValueError(f'Famous line text does not match its exact unit span: {qid}')
            if not isinstance(source, str):
                raise ValueError(f'Invalid famous line source: {qid}')
            url = urlparse(source)
            if url.scheme not in ('http', 'https') or not url.netloc:
                raise ValueError(f'Invalid famous line source: {qid}')
            seen.add(qid)
            texts.add(text)


def attach_famous_lines(poems, catalog):
    if not isinstance(catalog, dict) or catalog.get('schema_version') != 1 or not isinstance(catalog.get('works'), dict):
        raise ValueError('Invalid famous line curation file')
    by_id = {p['id']: p for p in poems}
    if set(catalog['works']) - set(by_id):
        raise ValueError('Famous line curation refers to missing works')
    for poem in poems:
        entry = catalog['works'].get(poem['id'])
        if entry is not None and (not isinstance(entry, dict) or entry.get('body_hash') != poem['body_hash']):
            raise ValueError(f'Stale famous line body binding: {poem["id"]}')
        poem['famous_lines'] = copy.deepcopy(entry.get('famous_lines') if entry else [])
    validate_famous_lines(poems)


def famous_line_rows(poems):
    quotes, units = [], []
    for poem in poems:
        for ordinal, quote in enumerate(poem['famous_lines']):
            quotes.append((quote['id'], poem['id'], ordinal, quote['text'], quote['source_url']))
            units.extend((quote['id'], i, unit) for i, unit in enumerate(quote['unit_ids']))
    return sorted(quotes), sorted(units)


def write_famous_lines(con, poems):
    validate_famous_lines(poems)
    quotes, units = famous_line_rows(poems)
    con.executemany('INSERT INTO famous_lines VALUES(?,?,?,?,?)', quotes)
    con.executemany('INSERT INTO famous_line_units VALUES(?,?,?)', units)


def validate_famous_line_tables(con, poems):
    validate_famous_lines(poems)
    quotes, units = famous_line_rows(poems)
    actual = con.execute('SELECT id,poem_id,ordinal,text,source_url FROM famous_lines ORDER BY id').fetchall()
    actual_units = con.execute('SELECT quote_id,ordinal,unit_id FROM famous_line_units ORDER BY quote_id,ordinal').fetchall()
    if actual != quotes or actual_units != units:
        raise ValueError('SQLite famous lines differ from JSON records')
