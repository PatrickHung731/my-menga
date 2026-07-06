# -*- coding: utf-8 -*-
"""有聲漫畫（唸整篇小說版）：乾淨畫格輪播 + 旁白唸「整篇原始小說文本」+ 燒字幕 → MP4。

- 唸的內容 = 生成時存下的 output\<slug>\script.txt（原始小說全文），不是只唸對話框。
- 所有乾淨畫格(panels/) 自動平均分配到整段旁白的時間軸上。
- 可選彩色/黑白、可選配音聲音。

配音 = Edge-TTS（免費/免 GPU/免金鑰，需連網）。聲音清單見 VOICES。

用法:
  python narrate.py storyboards\catwarrior_ep01.json
  python narrate.py <sb.json> --voice xiaoxiao --bw
  python narrate.py <sb.json> --limit 4          # 只唸前 4 句試做
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

# ── 可選聲音（key → edge-tts voice）──
VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",   # 陸女·最自然（預設）
    "xiaoyi":   "zh-CN-XiaoyiNeural",     # 陸女·年輕活潑
    "yunxi":    "zh-CN-YunxiNeural",      # 陸男·年輕有活力
    "yunjian":  "zh-CN-YunjianNeural",    # 陸男·熱血激昂
    "yunyang":  "zh-CN-YunyangNeural",    # 陸男·沉穩旁白
    "tw_male":  "zh-TW-YunJheNeural",     # 台灣男
    "tw_female": "zh-TW-HsiaoChenNeural",  # 台灣女
}
DEFAULT_VOICE = "xiaoxiao"

VW, VH = 1080, 1440
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


FFMPEG = ffmpeg_bin()
FFPROBE = shutil.which("ffprobe")


def audio_dur(path):
    if FFPROBE:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except ValueError:
            pass
    return 2.0


def reading_order_panels(sb, max_page=None):
    """所有乾淨畫格路徑，依漫畫閱讀序（上→下、右→左）。"""
    title = sb["title"]
    pdir = ROOT / "output" / title / "panels"
    out = []
    for page in sb["pages"]:
        if max_page and page["page"] > max_page:
            continue
        pmap = {p["id"]: p for p in page["panels"]}
        for row in page["layout"]:
            for pid in row:
                if pid in pmap:
                    f = pdir / ("p%02d_%02d.png" % (page["page"], pid))
                    if f.exists():
                        out.append(f)
    return out


def get_script(sb):
    """要唸的文本：優先 output\<slug>\script.txt（原始小說全文）。"""
    title = sb["title"]
    sp = ROOT / "output" / title / "script.txt"
    if sp.exists():
        t = sp.read_text(encoding="utf-8").strip()
        if t:
            return t
    # 退回：把所有對白+旁白串起來
    parts = []
    for page in sb["pages"]:
        for p in page["panels"]:
            for d in p.get("dialogues", []):
                if d.get("type") != "sfx" and d.get("text"):
                    parts.append(d["text"].replace("\n", ""))
    return "。".join(parts)


def split_sentences(text, hard=40):
    """切成適合配音+字幕的短句（句末標點切，過長再用逗號/長度切）。"""
    text = re.sub(r"\s+", "", text)
    rough = re.split(r"(?<=[。！？!?；;…])", text)
    chunks = []
    for seg in rough:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= hard:
            chunks.append(seg); continue
        # 太長 → 用逗號切
        sub = re.split(r"(?<=[，,、])", seg)
        buf = ""
        for s in sub:
            if len(buf) + len(s) <= hard:
                buf += s
            else:
                if buf:
                    chunks.append(buf)
                buf = s
        if buf:
            chunks.append(buf)
    return [c for c in chunks if c]


def fit_panel(img_path, color):
    canvas = Image.new("RGB", (VW, VH), BG)
    if img_path and img_path.exists():
        im = Image.open(img_path).convert("RGB")
        if not color:
            im = im.convert("L").convert("RGB")
        scale = min((VW - 40) / im.width, (VH - 300) / im.height)
        nw, nh = int(im.width * scale), int(im.height * scale)
        im = im.resize((nw, nh), Image.LANCZOS)
        canvas.paste(im, ((VW - nw) // 2, (VH - 300 - nh) // 2 + 20))
    return canvas


def draw_subtitle(canvas, text):
    if not text:
        return canvas
    d = ImageDraw.Draw(canvas, "RGBA")
    band_h = 250
    d.rectangle([0, VH - band_h, VW, VH], fill=(0, 0, 0, 205))
    fs = 46
    f = font(fs)
    maxc = 17
    lines = [text[i:i + maxc] for i in range(0, len(text), maxc)][:3]
    y = VH - band_h + (band_h - len(lines) * int(fs * 1.32)) // 2
    for ln in lines:
        d.text((VW // 2, y + int(fs * 0.66)), ln, font=f, fill="white",
               anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
        y += int(fs * 1.32)
    return canvas


async def tts(text, voice, path):
    await edge_tts.Communicate(text, voice).save(str(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--voice", default=DEFAULT_VOICE, help="|".join(VOICES))
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--color", action="store_true")
    grp.add_argument("--bw", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="只唸前 N 句（試做）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    voice = VOICES.get(args.voice, args.voice)
    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    title = sb["title"]
    color = bool(sb.get("color", False))
    if args.color:
        color = True
    if args.bw:
        color = False

    sentences = split_sentences(get_script(sb))
    if args.limit:
        sentences = sentences[:args.limit]
    if not sentences:
        print("[!] 找不到要唸的文本"); sys.exit(1)
    panels = reading_order_panels(sb)
    if not panels:
        print("[!] 找不到乾淨畫格 panels/"); sys.exit(1)

    out_mp4 = Path(args.out) if args.out else ROOT / "output" / title / (title + "_narrated.mp4")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="narrate_"))
    print("[有聲漫畫] 《%s》唸小說全文：%d 句、%d 畫格，聲音=%s（%s）"
          % (title, len(sentences), len(panels), args.voice, "彩色" if color else "黑白"))

    # 1) 逐句配音（尾端加 0.3s 停頓），記錄每句時長
    durs, audios = [], []
    for i, s in enumerate(sentences):
        raw = tmp / ("r%04d.mp3" % i)
        try:
            asyncio.run(tts(s, voice, raw))
        except Exception as e:
            print("  [警告] 配音失敗：%s" % e); continue
        pad = tmp / ("a%04d.m4a" % i)
        subprocess.run([FFMPEG, "-y", "-i", str(raw), "-af", "apad=pad_dur=0.3",
                        "-c:a", "aac", "-b:a", "160k", str(pad)], capture_output=True)
        durs.append(audio_dur(pad)); audios.append(pad)
        if (i + 1) % 8 == 0:
            print("  配音 %d/%d" % (i + 1, len(sentences)))
    if not audios:
        print("[!] 配音全部失敗（需連網）"); sys.exit(1)

    T = sum(durs)
    N = len(panels)
    panel_dur = T / N
    sent_start = [sum(durs[:i]) for i in range(len(durs))]

    # 2) 合成整段旁白音軌
    alist = tmp / "alist.txt"
    alist.write_text("".join("file '%s'\n" % a.as_posix() for a in audios), encoding="utf-8")
    narration = tmp / "narration.m4a"
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(alist),
                    "-c", "copy", str(narration)], capture_output=True)

    # 3) 聯合時間軸（畫格切換點 ∪ 句子切換點）→ 每段一張已燒字幕的 frame
    bounds = set([0.0, T])
    for k in range(1, N):
        bounds.add(round(k * panel_dur, 3))
    for st in sent_start[1:]:
        bounds.add(round(st, 3))
    times = sorted(t for t in bounds if 0 <= t <= T)

    def sent_at(t):
        idx = 0
        for i, st in enumerate(sent_start):
            if t >= st - 1e-6:
                idx = i
        return sentences[idx]

    concat = tmp / "vlist.txt"
    lines_out = []
    for j in range(len(times) - 1):
        t0, t1 = times[j], times[j + 1]
        if t1 - t0 < 0.05:
            continue
        pidx = min(N - 1, int((t0 + 1e-4) / panel_dur))
        frame = fit_panel(panels[pidx], color)
        draw_subtitle(frame, sent_at(t0))
        fp = tmp / ("f%04d.png" % j)
        frame.save(fp)
        lines_out.append("file '%s'\nduration %.3f\n" % (fp.as_posix(), t1 - t0))
    if lines_out:
        lines_out.append(lines_out[-1].split("\n")[0] + "\n")  # 重複最後一張（concat 慣例）
    concat.write_text("".join(lines_out), encoding="utf-8")

    slideshow = tmp / "slide.mp4"
    r1 = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                         "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                         str(slideshow)], capture_output=True, text=True)
    if not slideshow.exists():
        print("[!] 影像串接失敗：\n" + (r1.stderr or "")[-800:])
        shutil.rmtree(tmp, ignore_errors=True); sys.exit(1)

    # 4) 影像 + 旁白 → 成品
    r = subprocess.run([FFMPEG, "-y", "-i", str(slideshow), "-i", str(narration),
                        "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "160k", "-shortest", str(out_mp4)], capture_output=True, text=True)
    ok = out_mp4.exists()
    err = r.stderr or ""
    shutil.rmtree(tmp, ignore_errors=True)
    if ok:
        print("[有聲漫畫] 完成！→ %s（約 %.0f 秒）" % (out_mp4, T))
    else:
        print("[!] 合成失敗：\n" + err[-800:]); sys.exit(1)


if __name__ == "__main__":
    main()
