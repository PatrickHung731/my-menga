# -*- coding: utf-8 -*-
r"""試做：在獨立資料夾生幾頁樣張，預覽新畫風/黑白，完全不動現有內容。

用法:
  python preview_style.py --series Aiteacher --style kungfu_boy --bw --pages 2
  python preview_style.py --series catwarrior --style dragon_ball --pages 2

輸出: output\_previews\<series>_<style>[_bw]\pages\  （看完滿意再用工作台 [s] 全部重畫）
"""
import argparse
import json
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--style", required=True, help="|".join(STYLE_PRESETS))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--color", action="store_true")
    g.add_argument("--bw", action="store_true")
    ap.add_argument("--pages", type=int, default=2, help="試做前幾頁（預設 2）")
    ap.add_argument("--ep", default=None, help="指定哪一話 slug（預設第一話）")
    args = ap.parse_args()

    if args.style not in STYLE_PRESETS:
        print("[!] 未知畫風 %s" % args.style)
        sys.exit(1)
    spath = SERIES_DIR / (args.series + ".json")
    if not spath.exists():
        print("[!] 找不到連載:", args.series)
        sys.exit(1)
    series = json.loads(spath.read_text(encoding="utf-8"))
    if not series.get("episodes"):
        print("[!] 這部還沒有任何一話可試做")
        sys.exit(1)

    slug = args.ep or series["episodes"][0]["slug"]
    sb_path = ROOT / "storyboards" / (slug + ".json")
    if not sb_path.exists():
        print("[!] 找不到分鏡檔:", sb_path)
        sys.exit(1)

    tag = args.style + ("_bw" if args.bw else ("_color" if args.color else ""))
    pdir = ROOT / "output" / "_previews" / ("%s_%s" % (args.series, tag))
    panels_dir = pdir / "panels"
    pages_dir = pdir / "pages"

    print("[試做] 《%s》%s 前 %d 頁 → %s（現有內容完全不動）"
          % (series.get("title_zh", args.series), tag, args.pages, pdir))

    # 生前 N 頁的分格（用現有角色臉，畫風走覆蓋）
    gen = [sys.executable, str(HERE / "generate_panels.py"), str(sb_path),
           "--style", args.style, "--out-dir", str(panels_dir),
           "--pages", str(args.pages), "--redo"]
    if args.color:
        gen.append("--color")
    if args.bw:
        gen.append("--bw")
    if subprocess.run(gen).returncode != 0:
        sys.exit(1)

    # 拼成頁
    comp = [sys.executable, str(HERE / "compose_pages.py"), str(sb_path),
            "--panels-dir", str(panels_dir), "--out-dir", str(pages_dir),
            "--max-page", str(args.pages)]
    if args.color:
        comp.append("--color")
    if args.bw:
        comp.append("--bw")
    subprocess.run(comp)

    print("\n[試做] 完成！樣張在：%s" % pages_dir)
    print("[試做] 滿意的話 → 工作台 [s] 選同一個畫風，全部重畫。")
    try:
        import os
        os.startfile(pages_dir)
    except Exception:
        pass


if __name__ == "__main__":
    main()
