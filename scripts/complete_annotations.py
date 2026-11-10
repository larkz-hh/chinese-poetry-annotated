"""Fill missing annotations using the configured model, with hash-bound resumable output."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import threading
import urllib.error
import urllib.request

from data_utils import ROOT, FIELDS, annotation_valid, body_hash, load

BILLING_STOP = threading.Event()


class CreditUnavailable(RuntimeError):
    """The provider requires a billing change; retries cannot resolve it."""


def configuration(env_file):
    config = {}
    if env_file and Path(env_file).is_file():
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip().strip('"').strip("'")
    config.update(os.environ)
    if not all(config.get(k) for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ID")):
        raise ValueError("Missing LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID")
    return config


def request_json(config, system, prompt, budget=8192):
    if BILLING_STOP.is_set():
        raise CreditUnavailable("Provider returned HTTP 402; requests stopped")
    base = config["LLM_BASE_URL"].rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    payload = json.dumps(dict(model=config["LLM_MODEL_ID"], messages=[dict(role="system", content=system),
                         dict(role="user", content=prompt)], temperature=.2, max_tokens=budget,
                         thinking=dict(type="disabled"), response_format=dict(type="json_object"))).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Authorization": "Bearer " + config["LLM_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 402:
            BILLING_STOP.set()
            raise CreditUnavailable("Provider returned HTTP 402; requests stopped") from exc
        raise
    choice = result["choices"][0]
    if choice.get("finish_reason") == "length":
        raise ValueError("Model output truncated")
    value = choice["message"].get("content") or ""
    return json.loads(value), result.get("usage", {})


def generate(poem, config):
    prompt = ("只为所给正文写注解，不借同题名替换正文，不猜测具体写作年月或作者经历。"
              "正文单元可能是一联、一段或合集中的部分，不把单元数称为诗句数。"
              "输出 translate、notes、appreciation 三个字符串数组。按整篇注解展示，"
              "译文须覆盖所有正文，按语义段落完整转换为简体白话，注释解释正文中确实出现的词语，不能用原文充当译文。"
              "赏析150到350字，只分析可由正文支持的意象、结构、表达与情绪，不杜撰典故。"
              "若为残句，明确资料只存残句，不补写失传内容；若为合集，分别解释单元，不把多首诗当作一首。"
              '必须严格使用这个 JSON 结构：{"translate":["单元1译文","单元2译文"],"notes":["单元1注释","单元2注释"],"appreciation":["赏析段落"]}。'
              "数组元素只能是字符串，禁止嵌套对象、字典、列表。示例中的两个单元仅为格式示意，分段不要求与来源换行一致，但不得遗漏任何内容。\n"
              + json.dumps({k: poem.get(k) for k in ("title", "author", "dynasty", "content", "text_scope")}, ensure_ascii=False))
    last_error = ""
    for attempt in range(3):
        try:
            data, usage = request_json(config, "你是审慎的古诗文注释编辑。只输出合法 JSON。任何无法从正文支持的历史细节均不补造。", prompt,
                                       budget=min(16384, max(8192, len(poem["content"]) * 240 + 2000)))
            if any(not isinstance(data.get(k), list) or not all(isinstance(s, str) for s in data[k]) for k in FIELDS):
                debug = ROOT / "backups/content-generation-debug"
                debug.mkdir(parents=True, exist_ok=True)
                (debug / (poem["id"] + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                raise ValueError("Expected string arrays: " + str({k: type(data.get(k)).__name__ for k in FIELDS}))
            if not all(annotation_valid(data[k], poem["content"]) for k in FIELDS):
                raise ValueError("Empty, corrupted or copied-original annotation")
            if not 100 <= len("".join(data["appreciation"])) <= 900:
                raise ValueError("Unexpected appreciation length")
            return dict(id=poem["id"], **{k: data[k] for k in FIELDS}, body_hash=body_hash(poem["content"]),
                        model=config["LLM_MODEL_ID"], generated_at=datetime.now(timezone.utc).isoformat(),
                        prompt_version="complete-annotations-v2", review_status="unreviewed", alignment_mode="document", usage=usage,
                        source_url=poem["source"], **{"from": "ai"})
        except Exception as exc:
            last_error = type(exc).__name__ + ": " + str(exc)[:160]
            if isinstance(exc, CreditUnavailable):
                return dict(id=poem["id"], error="billing_unavailable", fatal=True)
            if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError):
                return dict(id=poem["id"], error="network_unavailable", detail=last_error)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return dict(id=poem["id"], error=last_error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    config = configuration(args.env_file)
    path = ROOT / "raw/annotation_additions.jsonl"
    existing = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if "error" not in row:
                existing[(row["id"], row["body_hash"])] = row
    todo = [p for p in load(ROOT / "app-data/poems.json") if not p["complete"] and (p["id"], p["body_hash"]) not in existing]
    if args.limit:
        todo = todo[:args.limit]
    print(f"Pending {len(todo)}; resumed {len(existing)}", flush=True)
    failures = 0
    with path.open("a", encoding="utf-8", newline="\n") as output, concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate, poem, config): poem for poem in todo}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            if row.get("error"):
                failures += 1
            print(f"{index}/{len(todo)} {row['id']} {'error: '+row['error'] if row.get('error') else 'ok'}", flush=True)
    if failures:
        raise SystemExit(f"{failures} generation failures; rerun after resolving")


if __name__ == "__main__":
    main()
