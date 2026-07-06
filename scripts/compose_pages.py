# -*- coding: utf-8 -*-
"""把生好的分格圖拼成漫畫頁：黑框、白溝、直排對白氣泡、旁白框、擬聲字。

用法:
  python compose_pages.py <storyboard.json> [--page N]

輸出: output/<title>/pages/page_NN.png
分格圖缺檔時畫灰底佔位格（方便在模型下載完前先預覽版型與對白）。
"""
import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout import page_cells

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FONT_CANDIDATES = {
    "dialog":    [r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\msjh.ttc"],
    "narration": [r"C:\Windows\Fonts\kaiu.ttf", r"C:\Windows\Fonts\msjh.ttc"],
    "sfx":       [r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\msjh.ttc"],
}
_font_cache = {}

# 對白/旁白字級倍率（由 storyboard 的 text_scale 設定，1.0=預設）
TEXT_SCALE = 1.0
# 級距對照：1=小 2=中(預設) 3=大 4=特大
SCALE_LEVELS = {1: 0.85, 2: 1.0, 3: 1.2, 4: 1.4}


def get_font(kind, size):
    key = (kind, size)
    if key not in _font_cache:
        for path in FONT_CANDIDATES[kind]:
            try:
                _font_cache[key] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        else:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


# 直排時的字形替換（橫線改直線）
VERT_MAP = {"—": "｜", "－": "｜", "ー": "｜", "~": "～"}


def is_latin(text):
    """沒有任何 CJK 漢字/假名 → 當成拉丁文字（英文），改用橫排氣泡。"""
    for c in text:
        if "぀" <= c <= "ヿ" or "一" <= c <= "鿿" \
                or "＀" <= c <= "￯":
            return False
    return True


def wrap_words(text, font, max_w):
    """英文氣泡：依像素寬度做單字換行（保留 \\n 強制換行）。"""
    lines = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            continue
        cur = words[0]
        for w in words[1:]:
            if font.getbbox(cur + " " + w)[2] <= max_w:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines or [text]


def vert_columns(text, max_per_col):
    """把文字切成直排欄位（支援 \\n 強制換欄），欄位間字數均分，閱讀順序右→左。"""
    cols = []
    for seg in text.split("\n"):
        seg = "".join(VERT_MAP.get(c, c) for c in seg)
        if not seg:
            continue
        n = math.ceil(len(seg) / float(max_per_col))
        per = int(math.ceil(len(seg) / n))
        for i in range(0, len(seg), per):
            cols.append(seg[i:i + per])
    return cols


def avoid_overlap(bx, by, bw, bh, cell, placed):
    """氣泡撞到同格已放置的氣泡時，往下（不行就往上）閃。"""
    x, y, w, h = cell
    for _ in range(4):
        hit = None
        for r in placed:
            if not (bx + bw < r[0] or r[2] < bx or by + bh < r[1] or r[3] < by):
                hit = r
                break
        if hit is None:
            break
        new_by = hit[3] + 10
        if new_by + bh > y + h:
            new_by = hit[1] - bh - 10
            if new_by < y:
                break
        by = new_by
    return bx, by


def draw_vertical_text(draw, right_x, top_y, cols, font, char_h, col_w, fill="black"):
    for ci, col in enumerate(cols):
        cx = right_x - ci * col_w - col_w / 2.0
        for ri, ch in enumerate(col):
            draw.text((cx, top_y + ri * char_h + char_h / 2.0), ch,
                      font=font, fill=fill, anchor="mm")


def anchor_pos(cell, bw, bh, pos, pad=14):
    """氣泡在格子內的左上角座標。"""
    x, y, w, h = cell
    px = {"left": x + pad, "right": x + w - bw - pad,
          "center": x + (w - bw) // 2}
    py = {"top": y + pad, "bottom": y + h - bh - pad,
          "center": y + (h - bh) // 2}
    hpos, vpos = "center", "center"
    for token in pos.split("-"):
        if token in ("left", "right"):
            hpos = token
        elif token in ("top", "bottom"):
            vpos = token
    return px[hpos], py[vpos]


def draw_speech(img, draw, cell, text, pos, shout=False, placed=None):
    fs = int(round((44 if shout else 36) * TEXT_SCALE))
    font = get_font("dialog", fs)

    if is_latin(text):
        # 英文：橫排、單字換行、置中
        disp = text.upper() if shout else text
        max_w = 360 if shout else 300
        lines = wrap_words(disp, font, max_w)
        lh = int(fs * 1.22)
        tw = max(font.getbbox(ln)[2] for ln in lines)
        th = lh * len(lines)
        bw = int(tw * 1.28) + 46
        bh = int(th * 1.55) + 26
        horiz = True
    else:
        # 中日文：直排、右→左
        char_h = int(fs * 1.18)
        col_w = int(fs * 1.3)
        max_per_col = 6 if len(text) > 6 else max(2, len(text))
        cols = vert_columns(text, max_per_col)
        rows = max(len(c) for c in cols)
        tw = len(cols) * col_w
        th = rows * char_h
        bw = int(tw * 1.55) + 22
        bh = int(th * 1.30) + 22
        horiz = False

    bx, by = anchor_pos(cell, bw, bh, pos)
    if placed is not None:
        bx, by = avoid_overlap(bx, by, bw, bh, cell, placed)
        placed.append((bx, by, bx + bw, by + bh))

    # 尾巴先畫（底端會被氣泡蓋掉，看起來乾淨）
    x, y, w, h = cell
    bcx, bcy = bx + bw / 2.0, by + bh / 2.0
    pcx, pcy = x + w / 2.0, y + h / 2.0
    ang = math.atan2(pcy - bcy, pcx - bcx)
    tip = (bcx + math.cos(ang) * (bw / 2.0 + 26), bcy + math.sin(ang) * (bh / 2.0 + 26))
    base_l = (bcx + math.cos(ang + 0.45) * bw / 2.3, bcy + math.sin(ang + 0.45) * bh / 2.3)
    base_r = (bcx + math.cos(ang - 0.45) * bw / 2.3, bcy + math.sin(ang - 0.45) * bh / 2.3)
    draw.polygon([tip, base_l, base_r], fill="white", outline="black", width=3)

    outline_w = 6 if shout else 3
    draw.ellipse([bx, by, bx + bw, by + bh], fill="white", outline="black", width=outline_w)
    if shout:
        draw.ellipse([bx + 8, by + 8, bx + bw - 8, by + bh - 8], outline="black", width=2)

    if horiz:
        ty = by + (bh - th) / 2.0
        for ln in lines:
            draw.text((bx + bw / 2.0, ty + lh / 2.0), ln, font=font, fill="black", anchor="mm")
            ty += lh
    else:
        draw_vertical_text(draw, bx + bw / 2.0 + tw / 2.0, by + (bh - th) / 2.0,
                           cols, font, char_h, col_w)


def draw_narration(draw, cell, text, pos, placed=None):
    fs = int(round(29 * TEXT_SCALE))
    font = get_font("narration", fs)
    if is_latin(text):
        lines = wrap_words(text, font, 300)   # 英文：整字換行
    else:
        max_chars = 12
        lines = []
        for seg in text.split("\n"):
            for i in range(0, len(seg), max_chars):
                lines.append(seg[i:i + max_chars])
    lw = max(font.getbbox(ln)[2] for ln in lines)
    lh = int(fs * 1.35)
    bw, bh = lw + 36, lh * len(lines) + 26
    bx, by = anchor_pos(cell, bw, bh, pos, pad=0)
    if placed is not None:
        bx, by = avoid_overlap(bx, by, bw, bh, cell, placed)
        placed.append((bx, by, bx + bw, by + bh))
    draw.rectangle([bx, by, bx + bw, by + bh], fill="white", outline="black", width=3)
    for i, ln in enumerate(lines):
        draw.text((bx + 18, by + 13 + i * lh), ln, font=font, fill="black")


def draw_sfx(img, cell, text, pos):
    fs = 96 if len(text) <= 2 else 72
    font = get_font("sfx", fs)
    pad_canvas = fs  # 給筆畫外框跟旋轉留空間
    tw = int(font.getbbox(text)[2]) + pad_canvas * 2
    th = int(fs * 1.4) + pad_canvas * 2
    tmp = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    td.text((tw / 2, th / 2), text, font=font, fill="black",
            stroke_width=8, stroke_fill="white", anchor="mm")
    tmp = tmp.rotate(-8, expand=True, resample=Image.BICUBIC)
    bx, by = anchor_pos(cell, tmp.width, tmp.height, pos, pad=0)
    img.paste(tmp, (int(bx), int(by)), tmp)


def cover_crop(img, w, h):
    sw, sh = img.size
    scale = max(w / float(sw), h / float(sh))
    img = img.resize((int(math.ceil(sw * scale)), int(math.ceil(sh * scale))), Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def draw_end_mark(draw, page_w, page_h):
    """最終話最後一頁左下角的「完」章（右→左閱讀的終點）。"""
    size = 96
    x, y = 52, page_h - 52 - size
    draw.rectangle([x, y, x + size, y + size], fill="white", outline="black", width=5)
    draw.text((x + size / 2, y + size / 2), "完",
              font=get_font("dialog", 56), fill="black", anchor="mm")


def compose_page(sb, page, panels_dir, end_mark=False):
    page_w, page_h = sb.get("page_size", [1240, 1754])
    color = bool(sb.get("color", False))
    canvas = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(canvas)
    cells = page_cells(page, page_w, page_h)
    pno = page["page"]

    for panel in page["panels"]:
        pid = panel["id"]
        x, y, w, h = cells[pid]
        f = panels_dir / ("p%02d_%02d.png" % (pno, pid))
        if f.exists():
            pimg = Image.open(f).convert("RGB")
            if not color:
                pimg = pimg.convert("L").convert("RGB")
            canvas.paste(cover_crop(pimg, w, h), (x, y))
        else:
            draw.rectangle([x, y, x + w, y + h], fill=(228, 228, 228))
            draw.text((x + w / 2, y + h / 2), "(尚未生成 p%02d_%02d)" % (pno, pid),
                      font=get_font("narration", 24), fill=(120, 120, 120), anchor="mm")
        draw.rectangle([x, y, x + w, y + h], outline="black", width=4)

    # 對白第二輪畫，才能壓在圖上
    for panel in page["panels"]:
        cell = cells[panel["id"]]
        placed = []
        for d in panel.get("dialogues", []):
            kind = d.get("type", "speech")
            pos = d.get("pos", "top-right")
            if kind == "narration":
                draw_narration(draw, cell, d["text"], pos, placed=placed)
            elif kind == "sfx":
                draw_sfx(canvas, cell, d["text"], pos)
                draw = ImageDraw.Draw(canvas)  # paste 後重建 draw
            elif kind == "shout":
                draw_speech(canvas, draw, cell, d["text"], pos, shout=True, placed=placed)
            else:
                draw_speech(canvas, draw, cell, d["text"], pos, placed=placed)

    # 頁碼
    draw.text((page_w / 2, page_h - 20), str(pno),
              font=get_font("narration", 22), fill="black", anchor="mm")
    if end_mark:
        draw_end_mark(draw, page_w, page_h)
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--page", type=int, default=None)
    ap.add_argument("--text-scale", type=float, default=None,
                    help="臨時覆蓋字級倍率（不寫回檔案）；平常用 --level 存進分鏡")
    ap.add_argument("--level", type=int, choices=[1, 2, 3, 4], default=None,
                    help="設定並存回分鏡的字級：1小 2中(預設) 3大 4特大")
    args = ap.parse_args()

    global TEXT_SCALE
    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    if args.level is not None:
        sb["text_scale"] = SCALE_LEVELS[args.level]
        Path(args.storyboard).write_text(
            json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[字級] 設為等級 %d（倍率 %.2f），已存回分鏡" % (args.level, sb["text_scale"]))
    TEXT_SCALE = float(args.text_scale) if args.text_scale is not None \
        else float(sb.get("text_scale", 1.0))
    title = sb["title"]
    panels_dir = ROOT / "output" / title / "panels"
    pages_dir = ROOT / "output" / title / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    last_page = max(p["page"] for p in sb["pages"])
    for page in sb["pages"]:
        if args.page is not None and page["page"] != args.page:
            continue
        out = pages_dir / ("page_%02d.png" % page["page"])
        end_mark = bool(sb.get("final")) and page["page"] == last_page
        compose_page(sb, page, panels_dir, end_mark=end_mark).save(out)
        print("[拼頁] %s" % out)

    print("完成 → %s" % pages_dir)


if __name__ == "__main__":
    main()
