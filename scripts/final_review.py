"""Replay individually adjudicated findings. This module makes no model calls."""
import copy
import hashlib
import re

from data_utils import FIELDS, body_hash


FINAL_ACTIONS = {
    "source_supported", "text_supported", "already_fixed", "corrected_from_text",
    "unsupported_detail_removed", "uncertainty_labeled", "editorial_rewrite",
}


def final_inputs(catalog, evidence):
    rows = catalog.get("decisions", [])
    if len(rows) != catalog.get("expected_findings"):
        raise ValueError("Final review is incomplete")
    sources = evidence.get("sources", {})
    for key, source in sources.items():
        if (not source.get("url", "").startswith("https://")
                or hashlib.sha256(source["excerpt"].encode()).hexdigest() != source["sha256"]):
            raise ValueError(f"Invalid source evidence: {key}")
    result, seen = {}, set()
    for row in rows:
        key = f"{row['id']}:{row['finding_index']}"
        if (row.get("key") != key or key in seen or row["action"] not in FINAL_ACTIONS
                or not row.get("reason") or not row.get("reviewer")):
            raise ValueError(f"Invalid final decision: {key}")
        seen.add(key)
        for ref in row.get("evidence", []):
            if ref not in sources and not re.match(r"https://[^\s]+$", ref):
                raise ValueError(f"Missing source evidence: {ref}")
        result.setdefault(row["id"], []).append(row)
    return result


def replay_final(poem, review, rows):
    """Mutate an editorial postimage using exact preconditions, not fuzzy matches."""
    decisions, edits, cautions = {}, [], []
    original_body = copy.deepcopy(poem["content"])
    context_before = {k: poem[k] for k in ("title", "author")}
    body_evidence, body_reasons = [], []
    for row in rows:
        i = row["finding_index"]
        if row["input_hash"] != review["input_hash"] or i not in range(len(review["findings"])):
            raise ValueError(f"Stale final review: {row['key']}")
        for change in row.get("changes", []):
            key = change["field"]
            if key not in (*FIELDS, "content"):
                raise ValueError(f"Unsupported final field: {key}")
            if key == "content":
                if not row.get("evidence"):
                    raise ValueError("Body correction requires source evidence")
                body_evidence.extend(row["evidence"])
                body_reasons.append(row["reason"])
            if "before" in change:
                if poem[key] != change["before"]:
                    raise ValueError(f"Stale final array: {row['key']}:{key}")
                poem[key] = copy.deepcopy(change["after"])
            else:
                index, quote, count = change["index"], change["quote"], change["occurrences"]
                if (not quote or not isinstance(count, int) or count < 1
                        or index not in range(len(poem[key])) or poem[key][index].count(quote) != count):
                    raise ValueError(f"Stale final quote: {row['key']}:{key}")
                poem[key][index] = poem[key][index].replace(quote, change["replacement"], count)
            edits.append(dict(finding_index=i, final_review=True, reason=row["reason"], **copy.deepcopy(change)))
        for key, change in row.get("context_changes", {}).items():
            if key != "title" or poem[key] != change["before"] or not change["after"]:
                raise ValueError(f"Stale final context: {row['key']}")
            poem[key] = change["after"]
        decisions[i] = {k: copy.deepcopy(row[k]) for k in ("action", "reason", "evidence", "reviewer", "reviewed_at")}
        decisions[i]["final_review"] = True
        if row.get("caution"):
            cautions.append(dict(finding_index=i, field=review["findings"][i]["field"], text=row["caution"]))
    for key in FIELDS:
        # Removing an entire unsupported paragraph may leave an empty array entry.
        poem[key] = [s for s in poem[key] if s.strip()]
        if not poem[key]:
            raise ValueError(f"Final review removed all {key}: {poem['id']}")
    body_change = None
    if original_body != poem["content"]:
        poem["body_hash"] = body_hash(poem["content"])
        body_change = dict(before=original_body, after=copy.deepcopy(poem["content"]),
            before_hash=body_hash(original_body), after_hash=poem["body_hash"],
            evidence=list(dict.fromkeys(body_evidence)), reason="；".join(dict.fromkeys(body_reasons)))
    context_after = {k: poem[k] for k in context_before if poem[k] != context_before[k]}
    return decisions, edits, cautions, body_change, context_after
