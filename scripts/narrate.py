# -*- coding: utf-8 -*-
r"""有聲漫畫：乾淨畫格（無字幕）＋ 台灣腔配音唸劇本 ＋ 燒進字幕 → MP4 影片。

配音用 Edge-TTS（微軟台灣國語聲音，免費、免 GPU、免金鑰）：
  男 zh-TW-YunJheNeural / 女 zh-TW-HsiaoChenNeural / 旁白 zh-TW-HsiaoYuNeural
角色男女聲依 characters\<id>\meta.json 的性別自動指派。

用法:
  python narrate.py storyboards\catwarrior_ep01.json
  python narrate.py <sb.json> --pages 2          # 只做前 2 頁（試做）
  python narrate.py <sb.json> --out D:\...\x.mp4  # 指定輸出
"""
import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 台灣腔聲音 ──
VOICE_MALE = "zh-TW-YunJheNeural"
VOICE_FEMALE = "zh-TW-HsiaoChenNeural"
VOICE_NARRATOR = "zh-TW-HsiaoYuNeural"

# ── 影片參數 ──
VW, VH = 1080, 1440           # 3:4 直式畫布
FPS = 30
BG = (18, 18, 18)

FONT_BOLD = [r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\msjh.ttc"]
_fc = {}


def font(size):
    if size not in _fc:
        for p in FONT_BOLD:
            try:
                _fc[size] = ImageFont.truetype(p, size); break
            except OSError:
                continue
        else:
            _fc[size] = ImageFont.load_default()
    return _fc[size]


def ffmpeg_bin():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffprobe_bin():
    return shutil.which("ffprobe")


FFMPEG = ffmpeg_bin()
FFPROBE = ffprobe_bin()


def audio_dur(path):
    if FFPROBE:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except ValueError:
            pass
    return 2.0


def reading_order(page):
    """漫畫閱讀序：由上到下每列，列內由右到左（=layout 列表順序）。"""
    order = []
    for row in page["layout"]:
        order.extend(row)
    pmap = {p["id"]: p for p in page["panels"]}
    return [pmap[i] for i in order if i in pmap]


def load_voices(sb):
    """char_id -> (voice, 中文名)。性別讀 meta.json。"""
    vmap = {}
    cdir = ROOT / "characters"
    for panel_chars in [p.get("characters", []) for pg in sb["pages"] for p in pg["panels"]]:
        for cid in panel_chars:
            if cid in vmap:
                continue
            d = cdir / cid
            gender = "1boy"
            zh = cid
            mf = d / "meta.json"
            if mf.exists():
                m = json.loads(mf.read_text(encoding="utf-8"))
                if re.search(r"\b1girl\b", m.get("positive", "")):
                    gender = "1girl"
            zf = d / "name_zh.txt"
            if zf.exists():
                zh = zf.read_text(encoding="utf-8").strip() or cid
            vmap[cid] = (VOICE_FEMALE if gender == "1girl" else VOICE_MALE, zh)
    return vmap


def clean_text(t):
    return t.replace("\n", " ").replace("｜", "—").strip()


def build_lines(sb, max_page=None):
    """攤平成 [(panel_key, panel_img_path, speaker_zh, text, voice, is_narration)]。
    沒對白的畫格保留一筆 text=None（靜音停頓）。"""
    vmap = load_voices(sb)
    title = sb["title"]
    panels_dir = ROOT / "output" / title / "panels"
    out = []
    for page in sb["pages"]:
        if max_page and page["page"] > max_page:
            continue
        for panel in reading_order(page):
            key = "p%02d_%02d" % (page["page"], panel["id"])
            img = panels_dir / (key + ".png")
            spoken = [d for d in panel.get("dialogues", [])
                      if d.get("type") in (None, "speech", "shout", "narration")]
            if not spoken:
                out.append((key, img, None, None, None, False))
                continue
            for d in spoken:
                txt = clean_text(d.get("text", ""))
                if not txt:
                    continue
                if d.get("type") == "narration":
                    out.append((key, img, None, txt, VOICE_NARRATOR, True))
                else:
                    voice, zh = vmap.get(d.get("speaker"), (VOICE_NARRATOR, None))
                    out.append((key, img, zh, txt, voice, False))
    return out


async def tts(text, voice, path, shout=False):
    rate = "+12%" if shout else "+0%"
    c = edge_tts.Communicate(text, voice, rate=rate)
    await c.save(str(path))


def fit_panel(img_path, color):
    canvas = Image.new("RGB", (VW, VH), BG)
    if img_path.exists():
        im = Image.open(img_path).convert("RGB")
        if not color:
            im = im.convert("L").convert("RGB")
        scale = min((VW - 40) / im.width, (VH - 300) / im.height)
        nw, nh = int(im.width * scale), int(im.height * scale)
        im = im.resize((nw, nh), Image.LANCZOS)
        canvas.paste(im, ((VW - nw) // 2, (VH - 300 - nh) // 2 + 20))
    return canvas


def draw_subtitle(canvas, speaker_zh, text):
    if not text:
        return canvas
    d = ImageDraw.Draw(canvas, "RGBA")
    band_h = 250
    d.rectangle([0, VH - band_h, VW, VH], fill=(0, 0, 0, 205))
    fs = 48
    f = font(fs)
    # 換行（每行約 16 字）
    maxc = 16
    lines = []
    for i in range(0, len(text), maxc):
        lines.append(text[i:i + maxc])
    lines = lines[:3]
    y = VH - band_h + (band_h - len(lines) * int(fs * 1.3)) // 2
    if speaker_zh:
        d.text((40, VH - band_h + 16), speaker_zh + "：", font=font(34),
               fill=(255, 214, 120), stroke_width=3, stroke_fill=(0, 0, 0))
        y += 10
    for ln in lines:
        d.text((VW // 2, y + int(fs * 0.65)), ln, font=f, fill="white",
               anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
        y += int(fs * 1.3)
    return canvas


def make_segment(frame_png, audio_mp3, seg_mp4, tail=0.4, silence=1.2):
    common = ["-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
              "-r", str(FPS), "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k"]
    if audio_mp3:
        dur = audio_dur(audio_mp3) + tail
        cmd = [FFMPEG, "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(frame_png),
               "-i", str(audio_mp3), "-t", "%.2f" % dur, "-af", "apad"] + common + [str(seg_mp4)]
    else:
        cmd = [FFMPEG, "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(frame_png),
               "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
               "-t", "%.2f" % silence] + common + [str(seg_mp4)]
    subprocess.run(cmd, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--pages", type=int, default=None, help="只做前 N 頁（試做）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    title = sb["title"]
    color = bool(sb.get("color", False))
    lines = build_lines(sb, args.pages)
    if not lines:
        print("[!] 這一話沒有可配音的內容")
        sys.exit(1)

    out_mp4 = Path(args.out) if args.out else ROOT / "output" / title / (title + "_narrated.mp4")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="narrate_"))
    print("[有聲漫畫] 《%s》共 %d 段，配音+合成中 ..." % (title, len(lines)))

    seg_list = []
    for idx, (key, img, spk, text, voice, is_narr) in enumerate(lines):
        frame = fit_panel(img, color)
        draw_subtitle(frame, spk, text)
        frame_png = tmp / ("f%04d.png" % idx)
        frame.save(frame_png)

        audio_mp3 = None
        if text:
            audio_mp3 = tmp / ("a%04d.mp3" % idx)
            try:
                asyncio.run(tts(text, voice, audio_mp3))
            except Exception as e:
                print("  [警告] 配音失敗(%s)：%s" % (key, e))
                audio_mp3 = None
        seg = tmp / ("s%04d.mp4" % idx)
        make_segment(frame_png, audio_mp3, seg)
        if seg.exists():
            seg_list.append(seg)
        if (idx + 1) % 10 == 0:
            print("  ... %d/%d" % (idx + 1, len(lines)))

    # 串接
    listfile = tmp / "list.txt"
    listfile.write_text("".join("file '%s'\n" % s.as_posix() for s in seg_list), encoding="utf-8")
    r = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                        "-c", "copy", str(out_mp4)], capture_output=True, text=True)
    if r.returncode != 0 or not out_mp4.exists():
        # 退回重新編碼串接
        subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        str(out_mp4)], capture_output=True)

    shutil.rmtree(tmp, ignore_errors=True)
    if out_mp4.exists():
        dur = audio_dur(out_mp4)
        print("[有聲漫畫] 完成！→ %s（約 %.0f 秒）" % (out_mp4, dur))
    else:
        print("[!] 合成失敗，請檢查 ffmpeg。")
        sys.exit(1)


if __name__ == "__main__":
    main()
