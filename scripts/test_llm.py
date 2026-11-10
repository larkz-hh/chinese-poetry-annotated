# -*- coding: utf-8 -*-
"""读 .env 里的 LLM 配置，测一次最小调用（不打印 key）。"""
import json
import os
import urllib.request

ENV = r"D:\project\agent\.env"


def load_env(path):
    cfg = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


cfg = load_env(ENV)
key = cfg.get("LLM_API_KEY", "")
base = cfg.get("LLM_BASE_URL", "").rstrip("/")
model = cfg.get("LLM_MODEL_ID", "")
print("base:", base)
print("model:", model)
print("key:", (key[:6] + "…" + key[-4:]) if key else "(空)")

url = base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"
body = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": "只回复两个字：收到"}],
    "temperature": 0,
    "max_tokens": 10,
}).encode()
req = urllib.request.Request(url, data=body, headers={
    "Content-Type": "application/json",
    "Authorization": "Bearer " + key,
})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    print("OK:", data["choices"][0]["message"]["content"][:40])
    print("usage:", data.get("usage"))
except Exception as e:
    print("FAILED:", type(e).__name__, str(e)[:300])
    try:
        print(e.read().decode()[:300])
    except Exception:
        pass
