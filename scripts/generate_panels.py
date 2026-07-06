# -*- coding: utf-8 -*-
"""讀分鏡 JSON → 逐格打 ComfyUI API 生圖 → 存到 output/<title>/panels/。

用法（用 ComfyUI 的 venv python 跑）:
  python generate_panels.py <storyboard.json> [--only 頁[:格]] [--redo]

例:
  python generate_panels.py ..\\storyboards\\demo.json
  python generate_panels.py ..\\storyboards\\demo.json --only 1:2 --redo
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comfy_client as cc
import sdxl_graph as sg
from layout import page_cells

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_char(name):
    """回傳 (tags 字串, ref 圖路徑或 None)。"""
    d = ROOT / "characters" / name
    tags = ""
    tf = d / "tags.txt"
    if tf.exists():
        tags = " ".join(tf.read_text(encoding="utf-8").split())
    ref = d / "ref.png"
    return tags, (ref if ref.exists() else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--only", default=None, help="只生成某頁或某格，如 1 或 1:2")
    ap.add_argument("--redo", action="store_true", help="已存在也重生成")
    args = ap.parse_args()

    sb_path = Path(args.storyboard)
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    title = sb["title"]
    color = bool(sb.get("color", False))
    style_key = sb.get("style", "shonen_90s")
    extra_style = sb.get("style_tags", "")
    negative = sb.get("default_negative", sg.NEG_DEFAULT)
    page_w, page_h = sb.get("page_size", [1240, 1754])

    only_page = only_panel = None
    if args.only:
        parts = args.only.split(":")
        only_page = int(parts[0])
        if len(parts) > 1:
            only_panel = int(parts[1])

    out_dir = ROOT / "output" / title / "panels"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = ROOT / "output" / title / "gen_log.json"
    gen_log = {}
    if log_path.exists():
        gen_log = json.loads(log_path.read_text(encoding="utf-8"))

    cc.ensure_server()
    ref_cache = {}   # 本機路徑 -> ComfyUI input 檔名
    done, skipped = 0, 0

    for page in sb["pages"]:
        pno = page["page"]
        if only_page is not None and pno != only_page:
            continue
        cells = page_cells(page, page_w, page_h)

        for panel in page["panels"]:
            pid = panel["id"]
            if only_panel is not None and pid != only_panel:
                continue
            key = "p%02d_%02d" % (pno, pid)
            out_file = out_dir / (key + ".png")
            if out_file.exists() and not args.redo:
                skipped += 1
                continue

            x, y, w, h = cells[pid]
            gw, gh = sg.pick_size(w / float(h))

            # 角色 tags 前置 + 參考圖
            char_tags, char_refs = [], []
            for cname in panel.get("characters", []):
                tags, ref = load_char(cname)
                if tags:
                    char_tags.append(tags)
                if ref is not None:
                    rp = str(ref)
                    if rp not in ref_cache:
                        ref_cache[rp] = cc.upload_image(rp)
                    char_refs.append(ref_cache[rp])
            # 多人同格只鎖第一個角色（本格主角）的臉，兩張參考疊加會臉部融合
            if len(char_refs) > 1 and not panel.get("all_refs"):
                char_refs = char_refs[:1]

            prompt = panel["prompt"]
            if panel.get("camera"):
                prompt = prompt + ", " + panel["camera"]
            # 單人格強制 solo，壓掉「同一角色畫兩次」的毛病
            plow = prompt.lower()
            if len(panel.get("characters", [])) <= 1 and "solo" not in plow \
                    and not any(t in plow for t in ("2boys", "2girls", "multiple")):
                prompt = "solo, " + prompt
            positive = sg.build_positive(prompt, char_tags, style_key, extra_style, color)
            rating = sb.get("rating", "safe")
            neg = negative + ", multiple views, clone, duplicate, " + \
                sg.RATING_NEG.get(rating, sg.RATING_NEG["safe"])
            if len(panel.get("characters", [])) <= 1:
                neg += ", multiple boys, multiple girls, 2boys, 2girls"

            # 姿勢參考（poses/ 下的檔名）
            pose_up = None
            if panel.get("pose"):
                pp = ROOT / "poses" / panel["pose"]
                if pp.exists():
                    pps = str(pp)
                    if pps not in ref_cache:
                        ref_cache[pps] = cc.upload_image(pps)
                    pose_up = ref_cache[pps]
                else:
                    print("  [警告] 姿勢圖不存在，略過: %s" % pp)

            seed = panel.get("seed")
            if seed is None:
                seed = random.randint(0, 2**31 - 1)

            graph = sg.build_graph(
                positive, neg, gw, gh, seed,
                char_refs=char_refs,
                ref_weight=panel.get("ref_weight", 0.75),
                face_only=panel.get("face_only", True),
                pose_image=pose_up,
                pose_is_skeleton=(panel.get("pose_type", "photo") == "skeleton"),
                pose_strength=panel.get("pose_strength", 0.85),
                steps=sb.get("steps", 26), cfg=sb.get("cfg", 5.5),
                filename_prefix="manga_" + title + "_" + key,
            )
            print("[生成] %s  %dx%d  seed=%d" % (key, gw, gh, seed))
            print("       %s" % positive[:160])
            outputs = cc.run_graph(graph)
            out_file.write_bytes(cc.first_image(outputs))
            gen_log[key] = {"seed": seed, "size": [gw, gh], "positive": positive,
                            "pose": panel.get("pose"), "characters": panel.get("characters", [])}
            log_path.write_text(json.dumps(gen_log, ensure_ascii=False, indent=2), encoding="utf-8")
            done += 1

    print("完成: 生成 %d 格, 略過 %d 格(已存在) → %s" % (done, skipped, out_dir))


if __name__ == "__main__":
    main()
