# -*- coding: utf-8 -*-
r"""自動生成連載封面：主角特寫 key visual（彩色）+ 標題字。

用法:
  python make_cover.py --series catwarrior [--char bluestar] [--seed N] [--bw]
  python make_cover.py --all            # 所有連載，缺封面才生成
  python make_cover.py --all --redo     # 全部重生

輸出: covers\<連載名>.png（3:4），publish.py 會優先採用它當封面。
"""
import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comfy_client as cc
import sdxl_graph as sg

ROOT = Path(__file__).resolve().parents[1]
SERIES_DIR = ROOT / "series"
COVERS_DIR = ROOT / "covers"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

COVER_W, COVER_H = 900, 1200          # 3:4，跟首頁卡片一致（免裁切）
GEN_W, GEN_H = 832, 1216              # SDXL 直式 bucket

TITLE_FONTS = [r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\msjh.ttc",
               r"C:\Windows\Fonts\simhei.ttf"]


def load_font(size):
    for p in TITLE_FONTS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gender_of(meta):
    m = re.search(r"\b(1girl|1boy|1other|2girls|2boys)\b", meta.get("positive", ""))
    return m.group(1) if m else "1girl"


def cover_crop(img, w, h):
    sw, sh = img.size
    scale = max(w / float(sw), h / float(sh))
    img = img.resize((int(math.ceil(sw * scale)), int(math.ceil(sh * scale))), Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def draw_title(canvas, title):
    """底部漸層 + 標題（白字黑框，過長自動縮小/換行）。"""
    W, H = canvas.size
    # 底部漸層遮罩，讓字清楚
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    band = int(H * 0.42)
    for i in range(band):
        a = int(210 * (i / float(band)) ** 1.4)
        sd.line([(0, H - band + i), (W, H - band + i)], fill=(0, 0, 0, a))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim)
    draw = ImageDraw.Draw(canvas)

    # 字級自適應
    size = int(W / 6.2)
    font = load_font(size)
    while font.getbbox(title)[2] > W * 0.88 and size > 40:
        size -= 4
        font = load_font(size)
    # 還是太長就換兩行（取中間切）
    lines = [title]
    if font.getbbox(title)[2] > W * 0.88 and len(title) > 3:
        mid = (len(title) + 1) // 2
        lines = [title[:mid], title[mid:]]
        size = int(W / 7.0)
        font = load_font(size)

    stroke = max(4, size // 11)
    lh = int(size * 1.16)
    total_h = lh * len(lines)
    y = H - int(H * 0.05) - total_h
    # 標題上方的紫色點綴線
    accent_y = y - 22
    draw.rectangle([W // 2 - 60, accent_y, W // 2 + 60, accent_y + 6], fill=(192, 132, 252, 255))
    for ln in lines:
        draw.text((W // 2, y + lh // 2), ln, font=font, fill=(255, 255, 255, 255),
                  stroke_width=stroke, stroke_fill=(0, 0, 0, 255), anchor="mm")
        y += lh
    return canvas.convert("RGB")


def make_one(series, char_id=None, seed=None, force_bw=False):
    name = series["name"]
    title = series.get("title_zh", name)
    style = series.get("style", "shonen_90s")
    rating = series.get("rating", "safe")
    chars = series.get("characters", {})
    if not chars:
        print("[封面] %s 沒有角色，跳過" % name)
        return None

    cid = char_id or next(iter(chars))          # 預設用第一位角色（通常是主角）
    cdir = ROOT / "characters" / cid
    tags = ""
    if (cdir / "tags.txt").exists():
        tags = " ".join((cdir / "tags.txt").read_text(encoding="utf-8").split())
    meta = {}
    if (cdir / "meta.json").exists():
        meta = json.loads((cdir / "meta.json").read_text(encoding="utf-8"))
    gender = gender_of(meta)
    color = not force_bw                          # 封面預設彩色（更吸睛）

    # 封面構圖 prompt
    cover_tags = ("%s, solo, upper body, looking at viewer, dynamic pose, "
                  "cover illustration, official art, dramatic lighting, "
                  "detailed background, wind" % gender)
    prompt = (tags + ", " + cover_tags) if tags else cover_tags
    extra = "vibrant colors, high contrast" if color else ""
    positive = sg.build_positive(prompt, [], style, extra, color)
    negative = sg.NEG_DEFAULT + ", " + sg.RATING_NEG.get(rating, sg.RATING_NEG["safe"])
    if color:
        negative += ", monochrome, greyscale, sketch"

    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    cc.ensure_server()
    char_refs = []
    ref = cdir / "ref.png"
    if ref.exists():
        char_refs.append(cc.upload_image(str(ref)))

    graph = sg.build_graph(positive, negative, GEN_W, GEN_H, seed,
                           char_refs=char_refs, ref_weight=0.7, face_only=True,
                           steps=28, cfg=6.0, filename_prefix="cover_" + name)
    print("[封面] 《%s》主角=%s seed=%d" % (title, cid, seed))
    print("       %s" % positive[:150])
    outputs = cc.run_graph(graph)
    art = Image.open(__import__("io").BytesIO(cc.first_image(outputs))).convert("RGB")

    canvas = cover_crop(art, COVER_W, COVER_H)
    canvas = draw_title(canvas, title)
    COVERS_DIR.mkdir(exist_ok=True)
    out = COVERS_DIR / (name + ".png")
    canvas.save(out)
    print("[封面] 完成 → %s（不滿意換 --seed 重生）" % out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default=None)
    ap.add_argument("--char", default=None, help="指定當封面主角的角色 id")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--bw", action="store_true", help="黑白封面（預設彩色）")
    ap.add_argument("--all", action="store_true", help="所有連載")
    ap.add_argument("--redo", action="store_true", help="已存在也重生")
    args = ap.parse_args()

    targets = []
    if args.all:
        for f in sorted(SERIES_DIR.glob("*.json")):
            targets.append(json.loads(f.read_text(encoding="utf-8")))
    elif args.series:
        f = SERIES_DIR / (args.series + ".json")
        if not f.exists():
            print("[!] 找不到連載:", args.series)
            sys.exit(1)
        targets.append(json.loads(f.read_text(encoding="utf-8")))
    else:
        print("[!] 用 --series <名> 或 --all")
        sys.exit(1)

    for s in targets:
        out = COVERS_DIR / (s["name"] + ".png")
        if out.exists() and not args.redo and args.all:
            print("[封面] %s 已有封面，略過（--redo 可重生）" % s["name"])
            continue
        make_one(s, char_id=args.char, seed=args.seed, force_bw=args.bw)


if __name__ == "__main__":
    main()
