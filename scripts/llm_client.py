# -*- coding: utf-8 -*-
"""本機編劇 LLM 客戶端。

engine="gemini"（預設）: 走 Gemini API 免費額度，零 VRAM、不吃 Claude token，需網路。
engine="ollama": 全離線，需先裝 Ollama 並 `ollama pull qwen3:8b`。
"""
import json
import os
import re
from pathlib import Path

import requests

QUANT_ENV = Path(r"D:\原F\QuantProject\.env")


def gemini_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k
    if QUANT_ENV.exists():
        for line in QUANT_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("找不到 GEMINI_API_KEY（環境變數或 D:\\原F\\QuantProject\\.env）")


def gemini_generate(prompt, model="gemini-2.5-flash", temperature=0.9):
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           + model + ":generateContent?key=" + gemini_key())
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
        # 官方 safetySettings：創作用途放寬到只擋高風險（露骨內容 Google 仍硬性阻擋）
        "safetySettings": [
            {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
            for c in ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                      "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")
        ],
    }
    r = requests.post(url, json=body, timeout=300)
    if r.status_code != 200:
        raise RuntimeError("Gemini API 失敗 %s: %s" % (r.status_code, r.text[:800]))
    data = r.json()
    if not data.get("candidates"):
        raise RuntimeError("Gemini 拒答（安全過濾）: %s"
                           % json.dumps(data.get("promptFeedback", data),
                                        ensure_ascii=False)[:400])
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def _ensure_ollama(wait=60):
    import subprocess
    import time
    try:
        requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        return
    except requests.RequestException:
        pass
    print("[ollama] server not running, starting it ...")
    subprocess.Popen(["ollama", "serve"],
                     creationflags=subprocess.CREATE_NO_WINDOW)
    t0 = time.time()
    while time.time() - t0 < wait:
        try:
            requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            return
        except requests.RequestException:
            time.sleep(2)
    raise RuntimeError("Ollama 伺服器 %s 秒內沒起來" % wait)


def ollama_generate(prompt, model="qwen3:8b", temperature=0.9):
    _ensure_ollama()
    r = requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False,
              "format": "json",
              "options": {"temperature": temperature, "num_ctx": 8192}},
        timeout=1800,
    )
    if r.status_code != 200:
        raise RuntimeError("Ollama 失敗（沒 pull 模型？）: " + r.text[:500])
    return r.json()["response"]


def generate(prompt, engine="gemini", model=None, temperature=0.9):
    if engine == "ollama":
        return ollama_generate(prompt, model or "qwen3:8b", temperature)
    return gemini_generate(prompt, model or "gemini-2.5-flash", temperature)


def extract_json(text):
    """容錯解析：剝 code fence、抓最外層大括號。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("LLM 回應中找不到 JSON: " + text[:300])
    return json.loads(text[i:j + 1])
