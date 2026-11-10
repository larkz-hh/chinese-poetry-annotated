"""Apply explicit, hash-bound work identity and catalog review decisions."""
import copy

from data_utils import body_hash, editions, unique


def apply_catalog(rows, policy):
    rows = copy.deepcopy(rows)
    by_id = {source_id: row for row in rows for source_id in unique([row["id"]] + row.get("source_ids", []))}
    decisions = policy.get("works", {})
    for pid, decision in decisions.items():
        row = by_id.get(pid)
        if row is None:
            continue
        expected = decision.get("expected_body_hash")
        if expected and body_hash(editions(row["id"], row["content"])[0]["content"]) != expected:
            raise ValueError(f"Catalog review no longer matches original text: {pid}")
    removed = set()
    for pid, decision in decisions.items():
        target_id = decision.get("merge_into")
        if not target_id or pid not in by_id:
            continue
        if target_id not in by_id or decisions.get(target_id, {}).get("merge_into"):
            raise ValueError(f"Invalid catalog merge target {pid}: {target_id}")
        member, target = by_id[pid], by_id[target_id]
        if member is target:
            continue
        if member["author"] != target["author"]:
            raise ValueError("Cross-author merge needs a separate attribution correction")
        target.setdefault("alternate_contents", []).append(dict(
            source_id=member["id"], source=member["source"], content=member["content"],
            review_status="text_compared", note=decision["reason"]))
        target["alternate_contents"].extend(member.get("alternate_contents", []))
        for key in ("tags", "collections", "source_ids", "sources"):
            target[key] = unique(target.get(key, []) + member.get(key, []))
        target["aliases"] = unique(target.get("aliases", []) + member.get("aliases", []) + [member["title"]])
        target["aliases"] = [title for title in target["aliases"] if title != target["title"]]
        removed.add(id(member))
    output = []
    for row in rows:
        if id(row) in removed:
            continue
        decision = decisions.get(row["id"], {})
        # Decisions may identify a source alias rather than the chosen raw record ID.
        if not decision:
            decision = next((decisions[i] for i in row.get("source_ids", [])
                             if i in decisions and not decisions[i].get("merge_into")), {})
        if decision:
            row["catalog_review"] = {k: v for k, v in decision.items() if k != "expected_body_hash"}
            if decision.get("author"):
                row["source_author"] = row["author"]
                row["author"] = decision["author"]
        output.append(row)
    return output
