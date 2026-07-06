# -*- coding: utf-8 -*-
"""ComfyUI HTTP API 極簡客戶端（沿用 D:\\LocalAI\\ComfyUI，不另裝任何東西）。"""
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

import requests

COMFY = "http://127.0.0.1:8188"
COMFY_DIR = r"D:\LocalAI\ComfyUI"
COMFY_PY = os.path.join(COMFY_DIR, "venv", "Scripts", "python.exe")


def server_up(timeout=3):
    try:
        with urllib.request.urlopen(COMFY + "/system_stats", timeout=timeout):
            return True
    except Exception:
        return False


def ensure_server(wait=240):
    """伺服器沒開就自動開（新視窗），等到 API 可用為止。"""
    if server_up():
        return
    print("[comfy] server not running, starting it ...")
    subprocess.Popen(
        [COMFY_PY, "main.py", "--port", "8188"],
        cwd=COMFY_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    t0 = time.time()
    while time.time() - t0 < wait:
        if server_up():
            print("[comfy] server ready")
            return
        time.sleep(3)
    raise RuntimeError("ComfyUI 在 %s 秒內沒起來，請檢查 D:\\LocalAI\\start_comfyui.bat" % wait)


def upload_image(path):
    """把本機圖丟進 ComfyUI 的 input 資料夾，回傳伺服器端檔名（給 LoadImage 用）。"""
    name = os.path.basename(path)
    with open(path, "rb") as f:
        r = requests.post(
            COMFY + "/upload/image",
            files={"image": (name, f, "image/png")},
            data={"overwrite": "true"},
            timeout=120,
        )
    r.raise_for_status()
    return r.json()["name"]


def run_graph(graph, timeout=900):
    """送出 API-format workflow，輪詢到完成，回傳 outputs dict。"""
    cid = uuid.uuid4().hex
    r = requests.post(COMFY + "/prompt", json={"prompt": graph, "client_id": cid}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("queue 失敗: " + r.text[:2000])
    pid = r.json()["prompt_id"]

    t0 = time.time()
    while True:
        time.sleep(1.5)
        h = requests.get(COMFY + "/history/" + pid, timeout=30).json()
        if pid in h:
            entry = h[pid]
            st = entry.get("status", {})
            if st.get("status_str") == "error":
                msgs = json.dumps(st.get("messages", []), ensure_ascii=False)
                raise RuntimeError("ComfyUI 執行錯誤: " + msgs[:3000])
            if entry.get("outputs"):
                return entry["outputs"]
        if time.time() - t0 > timeout:
            raise RuntimeError("生成逾時（%ss）" % timeout)


def fetch_image_bytes(img_info):
    params = urllib.parse.urlencode({
        "filename": img_info["filename"],
        "subfolder": img_info.get("subfolder", ""),
        "type": img_info.get("type", "output"),
    })
    r = requests.get(COMFY + "/view?" + params, timeout=120)
    r.raise_for_status()
    return r.content


def first_image(outputs):
    """從 run_graph 的 outputs 撈第一張圖的 bytes。"""
    for node_out in outputs.values():
        for img in node_out.get("images", []):
            return fetch_image_bytes(img)
    raise RuntimeError("工作流沒有輸出任何圖片")
