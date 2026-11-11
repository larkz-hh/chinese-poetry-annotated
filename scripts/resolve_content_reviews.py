"""Second-pass triage of model findings, without treating initial criticism as established fact."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from complete_annotations import configuration, request_json, CreditUnavailable
from data_utils import ROOT, FIELDS, load
from review_content import review_hash
from review_application import reviewed_input


def validate_decisions(decisions, finding_count):
    if (not isinstance(decisions, list) or len(decisions) != finding_count
            or any(not isinstance(d, dict) for d in decisions)
            or {d.get("finding_index") for d in decisions} != set(range(finding_count))):
        raise ValueError("Decision indexes mismatch")
    for d in decisions:
        if (d.get("action") not in {"fix", "reject", "needs_source"}
                or not isinstance(d.get("reason"), str) or not d["reason"].strip()
                or (d["action"] == "fix" and not isinstance(d.get("replacement"), str))):
            raise ValueError("Invalid triage decision or missing replacement")


def triage(poem, review, config):
    prompt = ("复核初审意见。初审模型会误报，不能照单全收。请对每条意见给出 fix/reject/needs_source 三选一。"
              "只有能够从正文直接验证的错译、文字讹误、缺漏或公认的基础事实错误才 fix。"
              "原注解正确、只是有不同解释、名讳/旧地名与今称不同、或只是想润色时 reject。"
              "有争议的典故、地理、具体年代或无法核实的史实 needs_source，禁止猜测补写。"
              "不要修改原文；field=content 的意见只可 reject 或 needs_source。"
              "注解整体展示，数组不必与原文逐行对应；不要把正常的引用原文、夸张或比喻当成错误。"
              "对于高风险但缺证据的历史背景，可用不作实指的审慎措辞替代，但不能创造新的史实。"
              '严格输出 {"decisions":[{"finding_index":0,"action":"fix或reject或needs_source",'
              '"replacement":"替换 quote 的字符串；reject/needs_source 可为空","reason":"独立判断理由"}]}。'
              "每条 finding 必须有且仅有一个 decision。fix 的 replacement 只替换原 quote，不重写整个字段。\n"
              + json.dumps(dict(poem={k:poem.get(k) for k in ("id","title","author","content",*FIELDS)}, findings=review["findings"]), ensure_ascii=False))
    for attempt in range(3):
        try:
            data, usage = request_json(config, "你是独立的复核编辑。谨慎判断，不把初审指控当作事实。只输出 JSON。", prompt, budget=12288)
            decisions = data.get("decisions")
            validate_decisions(decisions, len(review["findings"]))
            for decision in decisions:
                if decision.get("replacement") is None and decision.get("action") != "fix":
                    decision["replacement"] = ""
            if any(d.get("action") not in {"fix","reject","needs_source"} or not isinstance(d.get("replacement", ""), str) for d in decisions):
                raise ValueError("Invalid triage action")
            return dict(id=poem["id"], input_hash=review["input_hash"], decisions=decisions,
                        reviewed_at=datetime.now(timezone.utc).isoformat(), model=config["LLM_MODEL_ID"],
                        prompt_version="review-triage-v1", review_type="ai_second_review", usage=usage)
        except Exception as exc:
            if isinstance(exc, CreditUnavailable):
                return dict(id=poem["id"], error="billing_unavailable", fatal=True)
            if attempt==2:
                return dict(id=poem["id"], error=type(exc).__name__+": "+str(exc)[:120])
            time.sleep(2*(attempt+1))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file",type=Path,default=ROOT/'.env')
    parser.add_argument("--workers",type=int,default=8)
    parser.add_argument("--limit",type=int,default=0)
    args=parser.parse_args();config=configuration(args.env_file)
    resolutions=load(ROOT/'raw/review_resolutions.json',{}).get('works',{})
    poems={p['id']:reviewed_input(p,resolutions.get(p['id'])) for p in load(ROOT/'app-data/poems.json')}
    reviews={}
    for line in (ROOT/'raw/content_reviews.jsonl').read_text(encoding='utf-8').splitlines():
        r=json.loads(line)
        if 'error' not in r and r['id'] in poems and r['input_hash']==review_hash(poems[r['id']]):reviews[r['id']]=r
    output_path=ROOT/'raw/review_triage.jsonl';done=set()
    if output_path.exists():
        for line in output_path.read_text(encoding='utf-8').splitlines():
            r=json.loads(line)
            if 'error' not in r and r['id'] in reviews:
                try:
                    validate_decisions(r.get('decisions'),len(reviews[r['id']]['findings']))
                except ValueError:
                    continue
                done.add((r['id'],r['input_hash']))
    pending=[r for r in reviews.values() if r['findings'] and (r['id'],r['input_hash']) not in done]
    if args.limit:pending=pending[:args.limit]
    print(f"Triage pending {len(pending)}; cached {len(done)}",flush=True)
    count=errors=0
    with output_path.open('a',encoding='utf-8',newline='\n') as output, concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(triage,poems[r['id']],r,config) for r in pending]
        for future in concurrent.futures.as_completed(futures):
            r=future.result();output.write(json.dumps(r,ensure_ascii=False)+'\n');output.flush();count+=1;errors+=bool(r.get('error'))
            if count%25==0 or count==len(pending):print(f"Triage {count}/{len(pending)}; errors {errors}",flush=True)
    if errors:raise SystemExit(f"{errors} triage failures")


if __name__=='__main__':main()
