"""Shared, dependency-free rules for corpus identity, editions and search."""
import hashlib
import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("translate", "notes", "appreciation")
SCHEMA_VERSION = 3
BOUNDARY = "zzpoemboundaryzz"


def load(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def dump(path, value, *, newline=None):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline=newline)


def unique(values):
    return list(dict.fromkeys(v for v in values if v))


def clean_lines(values):
    if isinstance(values, str):
        values = [values]
    result = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        value = re.sub(r"<(?:br\s*/?|/?p|/?div)\b[^>]*>", "\n", value, flags=re.I)
        value = html.unescape(re.sub(r"</?[a-zA-Z][^>]*>", "", value))
        result.extend(line.strip() for line in value.splitlines() if line.strip())
    return result


def compact(value):
    value = "".join(value) if isinstance(value, list) else value
    return "".join(c for c in unicodedata.normalize("NFC", value or "")
                   if unicodedata.category(c)[0] in "LN")


def source_key(url):
    match = re.search(r"shiwenv_([a-zA-Z0-9]+)", url or "")
    return match[1].lower() if match else (url or "").strip().rstrip("/")


VARIANT = re.compile(r"[（(]([^()（）]*(?:一作|又作|通[:：]|同[:：]|版本)[^()（）]*)[）)]")
VERSION = re.compile(r"[（(](版本[一二三四五六七八九十\d]+[^()（）]*)[）)]")


def identity_body(lines):
    return compact(VARIANT.sub("", "".join(lines)))


def body_hash(lines):
    return hashlib.sha256(json.dumps(lines, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def work_body(lines):
    """Compare the full primary edition, excluding explicit alternate editions."""
    primary = []
    for line in lines:
        primary.append(line)
        if VERSION.search(line):
            break
    return identity_body(primary)


def annotation_valid(value, content):
    return (isinstance(value, list) and any(isinstance(s, str) and s.strip() for s in value)
            and all(isinstance(s, str) and "\ufffd" not in s for s in value)
            and compact(value) != compact(content))


def editions(poem_id, content):
    """Split only explicit version endings; retain every original segment separately."""
    blocks, pending = [], []
    for line in content:
        pending.append(line)
        marker = VERSION.search(line)
        if marker:
            blocks.append((marker[1], pending))
            pending = []
    if pending:
        blocks.append(("原始文本" if blocks else "来源版本", pending))
    output = []
    for index, (name, lines) in enumerate(blocks):
        normalized, variants = [], []
        for line in lines:
            for marker in VARIANT.finditer(line):
                variants.append(dict(unit_ordinal=len(normalized), text=marker[1]))
            value = VARIANT.sub("", line).strip()
            if value:
                normalized.append(value)
        output.append(dict(id=f"{poem_id}:v{index + 1}", label=name, content=normalized,
                           original_content=lines, variants=variants, is_primary=index == 0))
    return output


def fts_text(value):
    """Character tokens with a boundary token, so phrases cannot cross punctuation."""
    tokens = []
    for char in unicodedata.normalize("NFC", value or "").casefold():
        if unicodedata.category(char)[0] in "LN":
            tokens.append(char)
        elif tokens and tokens[-1] != BOUNDARY:
            tokens.append(BOUNDARY)
    return " ".join(tokens).strip()


def match_query(keyword, column=None):
    if column not in (None, "title", "author", "content"):
        raise ValueError("Unsupported search column")
    tokens = fts_text(keyword).split()
    while tokens and tokens[-1] == BOUNDARY:
        tokens.pop()
    if not tokens:
        return None
    phrase = '"' + " ".join(tokens).replace('"', '""') + '"'
    return (column + ":" if column else "") + phrase
