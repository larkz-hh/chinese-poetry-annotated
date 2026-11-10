"""Review annotation coverage and factual risks; retain model findings without auto-applying them."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from complete_annotations import configuration, request_json, CreditUnavailable
from data_utils import ROOT, FIELDS, load
from review_application import input_hash, reviewed_input


review_hash = input_hash


def check_batch(poems, config):
    payload = [{k: p.get(k) for k in ("id", "title", "author", "dynasty", "content", "text_scope", *FIELDS)} for p in poems]
    prompt = ("复核下列古诗词的译文、注释和赏析，逐首返回，ID 不得遗漏。只报告明确的错译、全文覆盖缺漏、张冠李戴，"
              "以及具体典故/人物年代/地名/制度方面的事实风险。不要因审美观点不同要求重写；不要把夸张比喻当成错误；"
              "不要把注释中的原文引用当成原文污染；注解按整篇展示，不要求数组行数与原文相等。"
              "多版本与残句已经明确标注，不能臆造遗失内容。历史背景无法确定就标需来源核对，不能猜测。",
              '严格返回 {"reviews":[{"id":"原ID","findings":[{"field":"notes","index":0,"quote":"原注解中准确的短语",'
              '"replacement":"确定可修正的文字，无法确定则为空字符串","reason":"具体问题",'
              '"confidence":"high或medium","needs_source_check":true}]}]}。无问题时 findings=[]。'
              "field 只能为 translate/notes/appreciation/content。quote 必须精确摘录该数组元素中有问题的内容。"
              "不得直接批量重写注解，不确定时只提出核对项。\n" + json.dumps(payload, ensure_ascii=False))
    prompt = "".join(prompt)
    last_error = ""
    for attempt in range(3):
        try:
            data, usage = request_json(config, "你是独立的古诗词数据复核编辑。输出合法 JSON，逐条提出有证据的问题，不为了找错而制造问题。", prompt, budget=12288)
            results = data.get("reviews")
            if not isinstance(results, list) or {r.get("id") for r in results} != {p["id"] for p in poems} or len(results) != len(poems):
                raise ValueError("Review IDs do not match input")
            by_id = {p["id"]: p for p in poems}
            output = []
            for row in results:
                poem = by_id[row["id"]]
                if not isinstance(row.get("findings"), list):
                    raise ValueError("Expected findings array")
                findings = []
                for finding in row["findings"]:
                    key, index, quote = finding.get("field"), finding.get("index"), finding.get("quote")
                    locatable = (key in ("content", *FIELDS) and isinstance(index, int) and 0 <= index < len(poem[key])
                                 and isinstance(quote, str) and bool(quote) and quote in poem[key][index])
                    finding["locatable"] = locatable
                    if not locatable:
                        finding["needs_source_check"] = True
                    findings.append(finding)
                output.append(dict(id=poem["id"], body_hash=poem["body_hash"], input_hash=review_hash(poem),
                                   findings=findings, model=config["LLM_MODEL_ID"], prompt_version="content-review-v1",
                                   reviewed_at=datetime.now(timezone.utc).isoformat(), review_type="ai_review", usage=usage))
            return output
        except Exception as exc:
            last_error = type(exc).__name__ + ": " + str(exc)[:160]
            if isinstance(exc, CreditUnavailable):
                return [dict(id=p["id"], error="billing_unavailable", fatal=True) for p in poems]
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return [dict(id=p["id"], error=last_error) for p in poems]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    config = configuration(args.env_file)
    path = ROOT / "raw/content_reviews.jsonl"
    completed = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if "error" not in value:
                completed.add((value["id"], value["input_hash"]))
    resolutions = load(ROOT / "raw/review_resolutions.json", {}).get("works", {})
    inputs = [reviewed_input(p, resolutions.get(p["id"])) for p in load(ROOT / "app-data/poems.json")]
    poems = [p for p in inputs if (p["id"], review_hash(p)) not in completed]
    if args.limit:
        poems = poems[:args.limit]
    batches, pending, size = [], [], 0
    for poem in poems:
        length = len(json.dumps(poem["content"] + poem["translate"] + poem["notes"] + poem["appreciation"], ensure_ascii=False))
        if pending and (len(pending) >= args.batch_size or size + length > 18000):
            batches.append(pending)
            pending, size = [], 0
        pending.append(poem)
        size += length
    if pending:
        batches.append(pending)
    print(f"Pending {len(poems)} poems in {len(batches)} batches; cached {len(completed)}", flush=True)
    errors = done = findings = 0
    with path.open("a", encoding="utf-8", newline="\n") as output, concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(check_batch, batch, config) for batch in batches]
        for future in concurrent.futures.as_completed(futures):
            for record in future.result():
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                errors += bool(record.get("error"))
                findings += len(record.get("findings", []))
                done += 1
            output.flush()
            print(f"Reviewed {done}/{len(poems)}; findings {findings}; errors {errors}", flush=True)
    if errors:
        raise SystemExit(f"{errors} review failures; resumable output retained")


if __name__ == "__main__":
    main()
