"""Apply explicit review resolutions with before/after guards; never rewrite poem originals."""
import copy
import hashlib
import json

from data_utils import FIELDS, annotation_valid


def input_hash(poem):
    value = {k: poem[k] for k in ("id", "title", "author", "body_hash", *FIELDS)}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fragmented_array(value):
    return isinstance(value, list) and len(value) >= 20 and sum(isinstance(s, str) and len(s) <= 2 for s in value) / len(value) > .85


def allowed_values(change):
    return [change["before"], change["after"], *change.get("accepted_previous", [])]


def reviewed_input(poem, resolution):
    """Restore a review's preimage for resuming the same review after publication."""
    before = copy.deepcopy(poem)
    if not resolution:
        return before
    if before["body_hash"] != resolution["body_hash"]:
        raise ValueError(f"Reviewed body changed: {poem['id']}")
    for key, change in resolution.get("fields", {}).items():
        if before[key] not in allowed_values(change):
            raise ValueError(f"Annotation changed since review: {poem['id']}:{key}")
        before[key] = change["before"]
    before.update(resolution["context_before"])
    if input_hash(before) != resolution["input_hash"]:
        raise ValueError(f"Reviewed input changed: {poem['id']}")
    return before


def apply_resolution(poem, resolution):
    if not resolution:
        return
    if resolution["body_hash"] != poem["body_hash"]:
        raise ValueError(f"Stale content review body: {poem['id']}")
    before = copy.deepcopy(poem)
    for key, change in resolution.get("fields", {}).items():
        if key not in FIELDS or poem[key] not in allowed_values(change):
            raise ValueError(f"Stale reviewed annotation: {poem['id']}:{key}")
        before[key] = change["before"]
    before["title"] = resolution["context_before"]["title"]
    before["author"] = resolution["context_before"]["author"]
    if input_hash(before) != resolution["input_hash"]:
        raise ValueError(f"Content changed since review: {poem['id']}")
    for key, change in resolution.get("fields", {}).items():
        if not annotation_valid(change["after"], poem["content"]):
            raise ValueError("Review would introduce invalid annotations")
        poem[key] = change["after"]
        previous = poem["field_sources"][key]
        if not change.get("format_only") and previous.get("revision") != "content-review-v1":
            poem["field_sources"][key] = dict(type="ai_editorial", model="codex",
                original_source=previous.copy(), revision="content-review-v1", body_hash=poem["body_hash"],
                alignment_verified=False, source_url=previous.get("source_url"),
                reason="复核后修正明确的文字、引用或译注错误；原值保存在 review_resolutions.json")
        elif change.get("format_only"):
            poem["field_sources"][key]["format_repaired"] = "single-character-array-joined"
    if input_hash(poem) != resolution["output_hash"]:
        raise ValueError(f"Unexpected review output: {poem['id']}")
    pending = resolution.get("pending_findings", [])
    poem["content_review"] = dict(type="ai_review", review_status="needs_source_check" if pending else "ai_reviewed",
        input_hash=resolution["input_hash"], output_hash=resolution["output_hash"],
        reviewed_at=resolution["reviewed_at"], model=resolution["model"],
        initial_findings=resolution.get("initial_findings", 0), second_reviewed=resolution.get("second_reviewed", False),
        academic_review_complete=False,
        pending_findings=pending, decisions=resolution.get("decisions", []))
    poem["review_status"] = poem["content_review"]["review_status"]
    for key in FIELDS:
        poem["field_sources"][key]["review_status"] = "needs_source_check" if any(f.get("field") == key for f in pending) else "ai_reviewed"
        poem["alignment"][key]["equal_length"] = key != "appreciation" and len(poem[key]) == len(poem["content"])
    poem["quality_issues"] = [i for i in poem["quality_issues"] if i != "content_source_verification"]
    if pending:
        poem["quality_issues"].append("content_source_verification")
