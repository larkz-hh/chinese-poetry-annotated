"""Compile explicit editorial decisions and review findings into reproducible resolutions.

This command is offline. Model suggestions never become edits unless explicitly
listed in approved_review_edits.json. Reruns reconstruct the reviewed input from
the previous resolution, so published corrections do not invalidate the log.
"""
import argparse
import copy
import json
from pathlib import Path

from data_utils import ROOT, FIELDS, dump, load
from review_application import input_hash, fragmented_array, reviewed_input
from final_review import final_inputs, replay_final


def successful_records(path):
    result = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if "error" not in record:
                    result[record["id"]] = record
    return result


def prepare(poems, reviews, triages, approvals, catalog, previous, final=None):
    output = {}
    for current in poems:
        pid = current["id"]
        poem = reviewed_input(current, previous.get(pid))
        review = reviews.get(pid)
        if not review or review["input_hash"] != input_hash(poem):
            raise ValueError(f"Missing or stale initial review: {pid}")
        after = copy.deepcopy(poem)
        decisions = {}
        edits = []
        for key in FIELDS:
            if fragmented_array(after[key]):
                after[key] = ["".join(after[key])]
                edits.append(dict(field=key, action="join_character_array", reason="无损合并单字数组，文字及顺序不变。"))
                for i, finding in enumerate(review["findings"]):
                    if finding.get("field") == key and any(word in finding.get("reason", "") for word in ("单字", "逐字", "字符")):
                        decisions[i] = dict(action="format_repaired", reason="逐字数组已无损合并，未使用模型替代赏析。")
        triage = triages.get(pid, {})
        if triage and triage["input_hash"] != review["input_hash"]:
            raise ValueError(f"Stale second review: {pid}")
        for d in triage.get("decisions", []):
            if d["action"] == "reject" and d["finding_index"] not in decisions:
                decisions[d["finding_index"]] = dict(action="ai_rejected", reason=d["reason"], model=triage["model"])
        for rejection in approvals.get("rejections", []):
            if rejection["id"] == pid:
                if rejection["input_hash"] != review["input_hash"]:
                    raise ValueError(f"Stale rejection: {pid}")
                decisions[rejection["finding_index"]] = dict(action="source_rejected", reason=rejection["reason"], evidence=rejection["evidence"])
        for decision in approvals.get("decisions", []):
            if decision["id"] != pid:
                continue
            if (decision["input_hash"] != review["input_hash"]
                    or decision["finding_index"] not in range(len(review["findings"]))
                    or decision["action"] not in {"source_rejected", "local_rejected", "already_fixed", "interpretation_supported"}):
                raise ValueError(f"Invalid explicit review decision: {pid}")
            decisions[decision["finding_index"]] = {k: decision[k] for k in ("action", "reason", "evidence")}
        for edit in approvals.get("edits", []):
            if edit["id"] != pid:
                continue
            if edit["input_hash"] != review["input_hash"]:
                raise ValueError(f"Stale edit: {pid}")
            key, index, quote = edit["field"], edit["index"], edit["quote"]
            occurrences = edit.get("occurrences", 1)
            if (key not in FIELDS or not quote or not isinstance(occurrences, int) or occurrences < 1
                    or after[key][index].count(quote) != occurrences):
                raise ValueError(f"Edit is not uniquely located: {pid}:{key}:{index}")
            after[key][index] = after[key][index].replace(quote, edit["replacement"], occurrences)
            edits.append(edit)
            if "finding_index" in edit:
                decisions[edit["finding_index"]] = dict(action="fixed", reason=edit["reason"], evidence=edit["evidence"])
        # Local catalog corrections can close a title-related finding explicitly.
        cat = catalog.get("works", {}).get(pid, {})
        if cat.get("title"):
            after["title"] = cat["title"]
        final_rows = (final or {}).get(pid, [])
        final_decisions, final_edits, cautions, body_change, context_after = replay_final(after, review, final_rows) if final_rows else ({}, [], [], None, {})
        decisions.update(final_decisions)
        edits.extend(final_edits)
        pending = []
        for i, finding in enumerate(review["findings"]):
            if i in decisions:
                continue
            # Extra approved edits may address a finding beyond the second pass.
            covered = any(e.get("quote") and e.get("field") == finding.get("field")
                          and finding.get("quote") and finding["quote"] in e["quote"] for e in edits)
            if covered:
                decisions[i] = dict(action="fixed", reason="显式批准的局部修订已覆盖该疑点。")
                continue
            if cat.get("title") and finding.get("field") == "content" and "柏舟" in finding.get("reason", ""):
                decisions[i] = dict(action="catalog_fixed", reason=cat["reason"])
                continue
            pending.append(dict(finding_index=i, **finding, status="needs_source_check",
                                second_review=next((d for d in triage.get("decisions", []) if d["finding_index"] == i), None)))
        fields = {}
        for key in FIELDS:
            if poem[key] != after[key]:
                fields[key] = dict(before=poem[key], after=after[key], format_only="".join(poem[key]) == "".join(after[key]))
                old_change = previous.get(pid, {}).get("fields", {}).get(key, {})
                prior = old_change.get("accepted_previous", []) + ([old_change["after"]] if old_change else [])
                accepted = []
                for value in prior:
                    if value not in (poem[key], after[key]) and value not in accepted:
                        accepted.append(value)
                if accepted:
                    fields[key]["accepted_previous"] = accepted
        output[pid] = dict(body_hash=poem["body_hash"], input_hash=input_hash(poem), output_hash=input_hash(after),
            context_before=dict(title=poem["title"], author=poem["author"]), fields=fields,
            reviewed_at=approvals["reviewed_at"], model=review["model"],
            initial_findings=len(review["findings"]), second_reviewed=bool(triage), edits=edits,
            pending_findings=pending, decisions=[dict(finding_index=i, **d) for i, d in sorted(decisions.items())])
        if final_rows:
            output[pid]["final_review"] = dict(status="completed", scope="flagged_passages_after_second_review",
                reviewer="codex", reviewed_at="2026-11-11", findings=len(final_rows), cautions=cautions)
        if body_change:
            output[pid]["body_change"] = body_change
        if context_after:
            output[pid]["context_after"] = context_after
    if final and set(final) - set(output):
        raise ValueError("Final decisions refer to missing works")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-poems", type=Path, default=ROOT / "app-data/poems.json")
    args = parser.parse_args()
    path = ROOT / "raw/review_resolutions.json"
    works = prepare(load(args.input_poems), successful_records(ROOT / "raw/content_reviews.jsonl"),
        successful_records(ROOT / "raw/review_triage.jsonl"), load(ROOT / "raw/approved_review_edits.json"),
        load(ROOT / "raw/content_review.json", {}), load(path, {}).get("works", {}),
        final_inputs(load(ROOT / "raw/final_content_decisions.json"), load(ROOT / "raw/source_evidence.json"))
        if (ROOT / "raw/final_content_decisions.json").exists() else None)
    dump(path, dict(review_type="ai_assisted_review", academic_review_complete=False, works=works), newline="\n")
    print(json.dumps(dict(reviewed=len(works), changed=sum(bool(r["fields"]) for r in works.values()),
        pending_poems=sum(bool(r["pending_findings"]) for r in works.values()),
        pending_findings=sum(len(r["pending_findings"]) for r in works.values())), ensure_ascii=False))


if __name__ == "__main__":
    main()
