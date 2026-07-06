# -*- coding: utf-8 -*-
r"""改整部連載的畫風：換 style（可同時改彩色/黑白）→ 重繪角色參考(保留同一張臉)
→ 重畫所有已出的話 → 重生封面。故事/分鏡/對白全部保留，只換「畫」。

用法:
  python restyle.py --series catwarrior --style dragon_ball
  python restyle.py --series AYU --style naruto --color
  python restyle.py --series X --style one_piece --bw --no-refs   # 不重繪角色參考
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdxl_graph import STYLE_PRESETS

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SERIES_DIR = ROOT / "series"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def run(cmd):
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("[restyle] 步驟失敗（exit %s），中止" % r.returncode)
        sys.exit(r.returncode)


def gender_of(meta):
    m = re.search(r"\b(1girl|1boy|1other)\b", meta.get("positive", ""))
    return m.group(1) if m else "1boy"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--style", required=True, help="|".join(STYLE_PRESETS))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--color", action="store_true", help="改成彩色")
    g.add_argument("--bw", action="store_true", help="改成黑白")
    ap.add_argument("--no-refs", action="store_true", help="不重繪角色參考圖（速度快，但畫風可能不夠統一）")
    args = ap.parse_args()

    if args.style not in STYLE_PRESETS:
        print("[!] 未知畫風 %s。可選：%s" % (args.style, "、".join(STYLE_PRESETS)))
        sys.exit(1)

    spath = SERIES_DIR / (args.series + ".json")
    if not spath.exists():
        print("[!] 找不到連載:", args.series)
        sys.exit(1)
    series = json.loads(spath.read_text(encoding="utf-8"))

    old_style = series.get("style")
    color = series.get("color", False)
    if args.color:
        color = True
    if args.bw:
        color = False
    print("[restyle] 《%s》畫風 %s → %s（%s）"
          % (series.get("title_zh", args.series), old_style, args.style,
             "彩色" if color else "黑白"))

    # 1) 連載設定
    series["style"] = args.style
    series["color"] = color
    spath.write_text(json.dumps(series, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) 重繪角色參考（同一顆 seed → 同一張臉，只換畫風）
    if not args.no_refs:
        for cid in series.get("characters", {}):
            cdir = ROOT / "characters" / cid
            tf = cdir / "tags.txt"
            mf = cdir / "meta.json"
            if not tf.exists():
                print("[restyle] 略過 %s（沒有 tags.txt）" % cid)
                continue
            tags = tf.read_text(encoding="utf-8").strip()
            meta = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
            cmd = [sys.executable, str(HERE / "new_character.py"),
                   "--name", cid, "--tags", tags,
                   "--gender", gender_of(meta), "--style", args.style]
            if meta.get("seed") is not None:
                cmd += ["--seed", str(meta["seed"])]
            if not color:
                cmd.append("--bw")
            print("[restyle] 重繪角色 %s" % cid)
            run(cmd)

    # 3) 每一話：改分鏡的 style/color → 重畫所有格 → 重拼頁
    for ep in series.get("episodes", []):
        sb_path = ROOT / "storyboards" / (ep["slug"] + ".json")
        if not sb_path.exists():
            print("[restyle] 略過 %s（找不到分鏡檔）" % ep["slug"])
            continue
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
        sb["style"] = args.style
        sb["color"] = color
        sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[restyle] 重畫 %s 全部分格 ..." % ep["slug"])
        run([sys.executable, str(HERE / "generate_panels.py"), str(sb_path), "--redo"])
        run([sys.executable, str(HERE / "compose_pages.py"), str(sb_path)])

    # 4) 重生封面
    print("[restyle] 重生封面 ...")
    run([sys.executable, str(HERE / "make_cover.py"), "--series", args.series, "--redo"])

    print("[restyle] 完成！全部改成【%s】畫風。記得發布（工作台 [p]）讓線上更新。" % args.style)


if __name__ == "__main__":
    main()
