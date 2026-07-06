# -*- coding: utf-8 -*-
"""一鍵：生成所有分格 + 拼成漫畫頁。

用法:
  python make_manga.py <storyboard.json> [--redo]
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--redo", action="store_true")
    args = ap.parse_args()

    cmd1 = [sys.executable, str(HERE / "generate_panels.py"), args.storyboard]
    if args.redo:
        cmd1.append("--redo")
    r = subprocess.run(cmd1)
    if r.returncode != 0:
        sys.exit(r.returncode)
    r = subprocess.run([sys.executable, str(HERE / "compose_pages.py"), args.storyboard])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
