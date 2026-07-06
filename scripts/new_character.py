# -*- coding: utf-8 -*-
"""建立角色設定：生成正面半身參考圖（給 IP-Adapter 鎖臉用）+ 存 tags。

用法:
  python new_character.py --name hero --tags "1boy 不要放這裡; 只放外觀: black spiky hair, orange gi, ..."
  python new_character.py --name hero --tags "black spiky hair, black eyes, orange martial arts uniform" --style dragon_ball --bw

注意: tags 只放「外觀」（髮型/髮色/眼睛/服裝/體型），不要放 1boy/1girl 這種數量詞，
數量詞由每格的 prompt 決定（避免雙人格變成 1boy, 1boy）。
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comfy_client as cc
import sdxl_graph as sg

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="角色資料夾名（英文）")
    ap.add_argument("--tags", required=True, help="外觀 Danbooru tags（英文逗號分隔）")
    ap.add_argument("--gender", default="1boy", help="1boy / 1girl（只用於生參考圖）")
    ap.add_argument("--style", default="shonen_90s")
    ap.add_argument("--bw", action="store_true", help="黑白參考圖（做黑白漫畫建議加）")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    d = ROOT / "characters" / args.name
    d.mkdir(parents=True, exist_ok=True)

    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    prompt = (args.gender + ", solo, upper body, front view, looking at viewer, "
              "neutral expression, standing, simple background, white background, "
              + args.tags)
    positive = sg.build_positive(prompt, [], args.style, "", color=(not args.bw))

    cc.ensure_server()
    graph = sg.build_graph(positive, sg.NEG_DEFAULT, 896, 1152, seed,
                           filename_prefix="charref_" + args.name)
    print("[角色] %s  seed=%d" % (args.name, seed))
    print("       %s" % positive[:160])
    outputs = cc.run_graph(graph)
    (d / "ref.png").write_bytes(cc.first_image(outputs))
    (d / "tags.txt").write_text(args.tags, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({
        "seed": seed, "positive": positive, "style": args.style, "bw": args.bw,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("完成 → %s（不滿意就換 --seed 重跑）" % (d / "ref.png"))


if __name__ == "__main__":
    main()
