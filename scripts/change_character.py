# -*- coding: utf-8 -*-
r"""改單一角色：重繪這個角色的設定圖（換外觀/換臉），只重畫「有他出場」的分格。

用法:
  # 只換一張臉（外觀不變，換 seed 重抽）
  python change_character.py --series catwarrior --char rusty
  # 換外觀設計（新的英文外觀 tags）
  python change_character.py --series catwarrior --char rusty --tags "orange fur, green eyes, torn ear, muscular"
  # 連性別/黑白一起指定、或固定 seed
  python change_character.py --series X --char boss --gender 1girl --seed 12345
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

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
        print("[change] 步驟失敗（exit %s），中止" % r.returncode)
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--char", required=True, help="角色 id（characters 資料夾名）")
    ap.add_argument("--tags", default=None, help="新的外觀 tags（省略=沿用舊的，只換臉）")
    ap.add_argument("--gender", default=None, help="1boy / 1girl（省略=沿用舊的）")
    ap.add_argument("--seed", type=int, default=None, help="固定 seed（省略=隨機換一張臉）")
    ap.add_argument("--bw", action="store_true", help="強制黑白參考圖")
    args = ap.parse_args()

    spath = SERIES_DIR / (args.series + ".json")
    if not spath.exists():
        print("[!] 找不到連載:", args.series)
        sys.exit(1)
    series = json.loads(spath.read_text(encoding="utf-8"))
    if args.char not in series.get("characters", {}):
        print("[!] 連載《%s》沒有角色 id：%s（有：%s）"
              % (args.series, args.char, "、".join(series["characters"])))
        sys.exit(1)

    cdir = ROOT / "characters" / args.char
    tags = args.tags
    if tags is None:
        tf = cdir / "tags.txt"
        tags = tf.read_text(encoding="utf-8").strip() if tf.exists() else ""
    gender = args.gender
    if gender is None:
        meta = json.loads((cdir / "meta.json").read_text(encoding="utf-8")) if (cdir / "meta.json").exists() else {}
        import re
        m = re.search(r"\b(1girl|1boy|1other)\b", meta.get("positive", ""))
        gender = m.group(1) if m else "1boy"
    color = series.get("color", False) and not args.bw
    style = series.get("style", "shonen_90s")

    # 1) 重繪角色設定圖（換臉/換外觀）
    cmd = [sys.executable, str(HERE / "new_character.py"),
           "--name", args.char, "--tags", tags, "--gender", gender, "--style", style]
    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]
    if not color:
        cmd.append("--bw")
    print("[change] 重繪角色 %s（%s）" % (args.char, series["characters"][args.char]))
    run(cmd)

    # 2) 找出「有他出場」的分格，逐一重畫；記錄要重拼的話
    affected = {}
    for ep in series.get("episodes", []):
        sb_path = ROOT / "storyboards" / (ep["slug"] + ".json")
        if not sb_path.exists():
            continue
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
        panels = []
        for page in sb["pages"]:
            for p in page["panels"]:
                if args.char in p.get("characters", []):
                    panels.append("%d:%d" % (page["page"], p["id"]))
        if panels:
            affected[str(sb_path)] = panels

    if not affected:
        print("[change] 這角色目前沒有出現在任何分格（只更新了設定圖）。")
    for sb_path, panels in affected.items():
        print("[change] %s：重畫 %d 格 %s" % (Path(sb_path).stem, len(panels), panels))
        for pp in panels:
            run([sys.executable, str(HERE / "generate_panels.py"), sb_path, "--only", pp, "--redo"])
        run([sys.executable, str(HERE / "compose_pages.py"), sb_path])

    # 3) 若他是封面主角（角色清單第一位）→ 順便重生封面
    if args.char == next(iter(series["characters"])):
        print("[change] 他是封面主角，重生封面 ...")
        run([sys.executable, str(HERE / "make_cover.py"), "--series", args.series, "--redo"])

    print("[change] 完成！記得發布（工作台 [p]）讓線上更新。")


if __name__ == "__main__":
    main()
