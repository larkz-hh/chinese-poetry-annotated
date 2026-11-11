"""Apply explicit review resolutions with before/after guards; never rewrite poem originals."""
import copy
import hashlib
import json

from data_utils import FIELDS, annotation_valid, body_hash, unique


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
    correction = resolution.get("body_change")
    accepted_hashes = [resolution["body_hash"]] + ([correction["after_hash"]] if correction else [])
    if before["body_hash"] not in accepted_hashes:
        raise ValueError(f"Reviewed body changed: {poem['id']}")
    if correction:
        if (body_hash(before["content"]) != before["body_hash"]
                or body_hash(correction["before"]) != resolution["body_hash"]
                or body_hash(correction["after"]) != correction["after_hash"]):
            raise ValueError(f"Invalid corrected body: {poem['id']}")
        before["content"] = copy.deepcopy(correction["before"])
        before["body_hash"] = resolution["body_hash"]
    for key, change in resolution.get("fields", {}).items():
        if key not in FIELDS or before[key] not in allowed_values(change):
            raise ValueError(f"Annotation changed since review: {poem['id']}:{key}")
        before[key] = change["before"]
    before.update(resolution["context_before"])
    if input_hash(before) != resolution["input_hash"]:
        raise ValueError(f"Reviewed input changed: {poem['id']}")
    return before


def apply_resolution(poem, resolution):
    if not resolution:
        return
    reviewed_input(poem, resolution)
    correction = resolution.get("body_change")
    if correction:
        apply_body_correction(poem, correction)
    for key, value in resolution.get("context_after", {}).items():
        if key != "title" or not value:
            raise ValueError("Unsupported review context change")
        poem["aliases"] = unique(poem.get("aliases", []) + [resolution["context_before"][key]])
        poem[key] = value
    for key, change in resolution.get("fields", {}).items():
        if not annotation_valid(change["after"], poem["content"]):
            raise ValueError("Review would introduce invalid annotations")
        poem[key] = change["after"]
        previous = poem["field_sources"][key]
        if (not change.get("format_only") and not change.get('format_normalized_only')
                and previous.get("revision") != "content-review-v1"):
            poem["field_sources"][key] = dict(type="ai_editorial", model="codex",
                original_source=previous.copy(), revision="content-review-v1", body_hash=poem["body_hash"],
                alignment_verified=False, source_url=previous.get("source_url"),
                reason="复核后修正明确的文字、引用或译注错误；原值保存在 review_resolutions.json")
        elif change.get("format_only") and not change.get('format_normalized_only'):
            poem["field_sources"][key]["format_repaired"] = "single-character-array-joined"
    if input_hash(poem) != resolution["output_hash"]:
        raise ValueError(f"Unexpected review output: {poem['id']}")
    pending = resolution.get("pending_findings", [])
    status = "needs_source_check" if pending else "editorially_reviewed" if resolution.get("final_review") else "ai_reviewed"
    poem["content_review"] = dict(type="ai_assisted_editorial_review" if resolution.get("final_review") else "ai_review", review_status=status,
        input_hash=resolution["input_hash"], output_hash=resolution["output_hash"],
        reviewed_at=resolution["reviewed_at"], model=resolution["model"],
        initial_findings=resolution.get("initial_findings", 0), second_reviewed=resolution.get("second_reviewed", False),
        academic_review_complete=False,
        pending_findings=pending, decisions=resolution.get("decisions", []))
    if resolution.get("final_review"):
        poem["content_review"]["final_review"] = copy.deepcopy(resolution["final_review"])
    if resolution.get('notes_normalization'):
        normalization = resolution['notes_normalization']
        poem['content_review']['notes_normalization'] = copy.deepcopy(normalization)
        poem['field_sources']['notes']['display_format'] = normalization['version']
    if correction:
        poem["content_review"]["body_correction"] = dict(before_hash=correction["before_hash"],
            after_hash=correction["after_hash"], evidence=correction["evidence"], reason=correction["reason"])
    poem["review_status"] = poem["content_review"]["review_status"]
    for key in FIELDS:
        poem["field_sources"][key]["review_status"] = "needs_source_check" if any(f.get("field") == key for f in pending) else status
        if correction:
            meta = poem["field_sources"][key]
            if meta["body_hash"] != poem["body_hash"]:
                meta["previous_body_hash"] = meta["body_hash"]
                meta["body_hash"] = poem["body_hash"]
                meta["body_binding_review"] = "source-correction-20261111"
        poem["alignment"][key]["equal_length"] = key != "appreciation" and len(poem[key]) == len(poem["content"])
    poem["quality_issues"] = [i for i in poem["quality_issues"] if i != "content_source_verification"]
    if pending:
        poem["quality_issues"].append("content_source_verification")


def apply_body_correction(poem, change):
    """Select a source-corrected edition while retaining every source edition."""
    if (not change.get("evidence") or body_hash(change["before"]) != change["before_hash"]
            or body_hash(change["after"]) != change["after_hash"]):
        raise ValueError("Unbound body correction")
    versions = poem.get("editions", [])
    if not any(v["content"] == change["before"] for v in versions):
        raise ValueError("Body correction would lose the original edition")
    eid = poem["id"] + ":source-checked-v1"
    existing = next((v for v in versions if v["id"] == eid), None)
    if existing and existing["content"] != change["after"]:
        raise ValueError("Corrected edition changed without a new version")
    for version in versions:
        version["is_primary"] = False
    if not existing:
        existing = dict(id=eid, label="据古籍校订本", content=copy.deepcopy(change["after"]),
            original_content=copy.deepcopy(change["after"]), variants=[],
            source_evidence=change["evidence"], revision="source-correction-20261111",
            reason=change["reason"], units=[dict(id=f"{eid}:u{i + 1}", ordinal=i, kind="passage", text=s)
                for i, s in enumerate(change["after"])])
        versions.append(existing)
    existing["is_primary"] = True
    poem["content"] = copy.deepcopy(change["after"])
    poem["body_hash"] = change["after_hash"]
    poem["text_scope"] = "source_corrected"
