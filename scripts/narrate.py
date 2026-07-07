# -*- coding: utf-8 -*-
r"""有聲漫畫（唸整篇小說版）：乾淨畫格輪播 + 旁白唸「整篇原始小說文本」+ 燒字幕 → MP4。

- 唸的內容 = 生成時存下的 output\<slug>\script.txt（原始小說全文），不是只唸對話框。
- 所有乾淨畫格(panels/) 自動平均分配到整段旁白的時間軸上。
- 可選彩色/黑白、可選配音聲音。

配音 = Edge-TTS（免費/免 GPU/免金鑰，需連網）。聲音清單見 VOICES。

用法:
  python narrate.py storyboards\catwarrior_ep01.json
  python narrate.py <sb.json> --voice xiaoxiao --bw
  python narrate.py <sb.json> --limit 4          # 只唸前 4 句試做
  python narrate.py <sb.json> --prepare-subtitles # 只產生可編輯字幕稿
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_parser

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
    "yunxia":   "zh-CN-YunxiaNeural",      # 陸男·可愛少年
    "tw_male":  "zh-TW-YunJheNeural",     # 台灣男
    "tw_female": "zh-TW-HsiaoChenNeural",  # 台灣女·曉臻
    "tw_girl":  "zh-TW-HsiaoYuNeural",    # 台灣女·曉雨
    "hk_female": "zh-HK-HiuGaaiNeural",   # 香港女
    "hk_male":  "zh-HK-WanLungNeural",    # 香港男
    "child":    "zh-CN-XiaoshuangNeural",  # 陸·兒童
}
DEFAULT_VOICE = "xiaoxiao"
NARRATOR = "旁白"
NARRATOR_VOICE = "yunyang"          # 旁白預設沉穩男聲
# 多角色自動配音的輪替池（沒被規則命中的講者依序拿）
VOICE_POOL = ["yunjian", "yunxi", "xiaoyi", "hk_male", "tw_male", "hk_female",
              "yunxia", "tw_girl", "xiaoxiao"]


def guess_voice(spk):
    """依講者名稱猜聲音（猜不到回 None，交給輪替池）。"""
    s = spk or ""
    if s in (NARRATOR, "narration", "narrator"):
        return NARRATOR_VOICE
    rules = [
        (("兒童", "小孩", "小朋友", "童", "女孩", "小女", "孩子"), "child"),
        (("軍事", "戰鬥", "武力", "作戰"), "yunjian"),
        (("系統", "機械", "機器", "終端", "電腦"), "hk_male"),
        (("醫療", "醫護", "醫生"), "xiaoxiao"),
        (("娛樂", "音樂"), "xiaoyi"),
        (("教育", "教學"), "yunxi"),
        (("眾", "合成", "全體", "群"), "yunyang"),
        (("老師", "師父", "男", "父", "爸", "王", "帝", "將", "兄", "叔"), "yunjian"),
        (("女", "母", "姐", "娘", "妹", "后", "妃", "婆", "嬸"), "xiaoxiao"),
    ]
    for keys, v in rules:
        if any(k in s for k in keys):
            return v
    return None


def _pick_unused(prefer, used):
    for v in prefer:
        if v in VOICES and v not in used:
            return v
    for v in VOICES:
        if v not in used:
            return v
    return None   # 講者比聲音還多時才會發生


def assign_voices(speakers, title):
    """回傳 {講者: voice_key}。自動配（盡量每人不同聲）+ 寫 voices.json 供人工改。"""
    uniq = []
    for s in speakers:
        if s not in uniq:
            uniq.append(s)
    if NARRATOR not in uniq:
        uniq = [NARRATOR] + uniq
    vpath = ROOT / "output" / title / "voices.json"
    saved = {}
    if vpath.exists():
        try:
            saved = json.loads(vpath.read_text(encoding="utf-8"))
        except Exception:
            saved = {}
    vm, used = {}, set()
    # 1) 先尊重使用者在 voices.json 已指定的
    for spk in uniq:
        if spk in saved and saved[spk] in VOICES:
            vm[spk] = saved[spk]; used.add(saved[spk])
    # 2) 旁白固定沉穩聲
    if NARRATOR not in vm:
        v = NARRATOR_VOICE if NARRATOR_VOICE not in used else _pick_unused(VOICE_POOL, used)
        vm[NARRATOR] = v or NARRATOR_VOICE; used.add(vm[NARRATOR])
    # 3) 其他角色：先照規則猜，撞聲就換沒用過的
    for spk in uniq:
        if spk in vm:
            continue
        g = guess_voice(spk)
        if g is None or g in used:
            g = _pick_unused(([g] if g else []) + VOICE_POOL, used) or g or DEFAULT_VOICE
        vm[spk] = g; used.add(g)
    vpath.parent.mkdir(parents=True, exist_ok=True)
    vpath.write_text(json.dumps(vm, ensure_ascii=False, indent=2), encoding="utf-8")
    return vm, vpath

VW, VH = 1080, 1440
FPS = 30
BG = (18, 18, 18)
SUBTITLE_SCRIPT_NAME = "subtitle_script.txt"

# F5-TTS（本機克隆語音）跑在自己的 venv
F5_VENV_PY = r"D:\LocalAI\f5tts_venv\Scripts\python.exe"
F5_BATCH = str(Path(__file__).resolve().parent / "f5_tts_batch.py")
F5_DEFAULT_REF = str(ROOT / "voice" / "patrick_ref_300s.wav")

# 本機 AI 音效（AudioLDM2）跑在自己的 venv
SFX_VENV_PY = r"D:\LocalAI\sfx_venv\Scripts\python.exe"
SFX_GEN = str(Path(__file__).resolve().parent / "sfx_gen.py")
# 中文音效描述 → 英文提示（AudioLDM2 吃英文較準）；子字串比對、可多個
SFX_KEYWORDS = [
    ("雨", "gentle rain"), ("水", "water splashing"), ("風", "wind blowing"),
    ("氣閥", "pneumatic valve hiss"), ("閥", "air hiss"),
    ("門", "heavy metal door"), ("玻璃", "glass shattering"),
    ("金屬", "metallic"), ("砸", "heavy impact clang"), ("撞", "heavy collision"),
    ("碰", "impact clang"), ("鏗", "metal clang"), ("鏘", "metal clang"),
    ("馬達", "servo motors humming"), ("伺服", "servo whirring"),
    ("引擎", "engine roaring"), ("齒輪", "mechanical gears turning"),
    ("警報", "loud emergency alarm siren"), ("警", "alarm"),
    ("彈指", "sharp finger snap"), ("腳步", "footsteps"), ("走", "footsteps"),
    ("高跟", "high heel footsteps"), ("爆", "explosion blast"),
    ("轟", "powerful explosion boom"), ("電", "electric crackle"),
    ("滋", "electric buzzing crackle"), ("槍", "gunshot"), ("刀", "blade slash"),
    ("鐘", "bell ringing"), ("鈴", "bell ringing"), ("心跳", "heartbeat"),
    ("鍵盤", "keyboard typing"), ("嗶", "electronic beep"),
]


def sfx_to_english(descs):
    """把中文音效描述轉成英文 sound-effect 提示。"""
    out = []
    for d in descs:
        hits = []
        for zh, en in SFX_KEYWORDS:
            if zh in d and en not in hits:
                hits.append(en)
        if hits:
            out.append("sound effect of " + ", ".join(hits[:3]) + ", cinematic, high quality")
        else:
            out.append("dramatic cinematic impact sound effect")
    return out
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
    r"""要唸的文本：優先 output\<slug>\script.txt（原始小說全文）。"""
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
    return "".join(
        part if re.search(r"[。！？!?；;…]$", part) else (part + "。")
        for part in parts if part
    )


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
    return [c for c in chunks if c and not re.fullmatch(r"[。！？!?；;…，,、]+", c)]


def subtitle_script_path(title, custom_path=None):
    if custom_path:
        return Path(custom_path)
    return ROOT / "output" / title / SUBTITLE_SCRIPT_NAME


def build_source_beats(sb):
    """回傳 [(講者, 文字)]。劇本格式→用解析器分講者/跳音效場景；純小說→整段當旁白。"""
    text = get_script(sb)
    if script_parser.is_screenplay(text):
        raw = script_parser.spoken_lines(text)          # [{speaker,text}]
    else:
        raw = [{"speaker": None, "text": text}]
    beats = []
    for item in raw:
        spk = item.get("speaker") or NARRATOR
        for chunk in split_sentences(item["text"]):
            beats.append((spk, chunk))
    return beats


def write_subtitle_script(path, beats, overwrite=False):
    """建立可人工校對的字幕稿；格式「【講者】內容」，一行一句。既有檔案預設不覆蓋。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    header = [
        "# 可編輯字幕稿：一行 = 一句配音 + 一段字幕。格式【講者】內容。",
        "# 講者決定用哪個聲音（對照 output\\<slug>\\voices.json）；旁白就寫【旁白】。",
        "# 可改字、改講者、拆行或合併；空行與 # 註解會被忽略。存檔後重跑即生效。",
        "",
    ]
    body = ["【%s】%s" % (spk, txt) for spk, txt in beats]
    path.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    return True


def read_subtitle_script(path):
    beats = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^[【\[]\s*(.+?)\s*[】\]]\s*(.*)$", line)
        if m and m.group(2):
            beats.append((m.group(1).strip(), m.group(2).strip()))
        else:
            beats.append((NARRATOR, line))
    return beats


def load_subtitle_sentences(sb, custom_path=None, regen=False):
    title = sb["title"]
    path = subtitle_script_path(title, custom_path)
    source_beats = build_source_beats(sb)
    created = write_subtitle_script(path, source_beats, overwrite=regen)
    if created:
        print("[字幕稿] 已建立：%s" % path)
    else:
        print("[字幕稿] 使用既有檔案：%s" % path)
    beats = read_subtitle_script(path)
    if not beats:
        raise ValueError("字幕稿沒有可用內容：%s" % path)
    texts = [t for _, t in beats]
    speakers = [s for s, _ in beats]
    return texts, speakers, path


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


def draw_subtitle(canvas, text, speaker=None):
    if not text:
        return canvas
    d = ImageDraw.Draw(canvas, "RGBA")
    band_h = 250
    d.rectangle([0, VH - band_h, VW, VH], fill=(0, 0, 0, 205))
    # 台詞顯示講者名（旁白不顯示）
    show_spk = speaker and speaker != NARRATOR
    fs = 46
    f = font(fs)
    maxc = 17
    lines = [text[i:i + maxc] for i in range(0, len(text), maxc)][:3]
    top = VH - band_h + (34 if show_spk else 0)
    y = top + (band_h - (34 if show_spk else 0) - len(lines) * int(fs * 1.32)) // 2
    if show_spk:
        d.text((40, VH - band_h + 14), str(speaker) + "：", font=font(32),
               fill=(255, 214, 120), stroke_width=3, stroke_fill=(0, 0, 0))
    for ln in lines:
        d.text((VW // 2, y + int(fs * 0.66)), ln, font=f, fill="white",
               anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
        y += int(fs * 1.32)
    return canvas


async def tts(text, voice, path):
    await edge_tts.Communicate(text, voice).save(str(path))


def build_panel_segments(durs, sent_start, T, N, fracs):
    """回傳 [(t0, t1, panel_idx)]：把 N 張畫格依場景敘述長度分配到時間軸。
    每個場景顯示它自己那段的畫格（畫格是照故事順序生的，所以第 i 段=場景 i）。
    出錯或無場景時退回平均分配。"""
    M = len(durs)
    try:
        if not fracs or len(fracs) < 2 or N < len(fracs) or M < len(fracs):
            raise ValueError("fallback")
        starts = sorted(set(max(0, min(M - 1, round(f * M))) for f in fracs))
        if starts[0] != 0:
            starts = [0] + starts
        ranges = []
        for i, st in enumerate(starts):
            en = starts[i + 1] if i + 1 < len(starts) else M
            if en > st:
                ranges.append((st, en))
        K = len(ranges)
        scene_time = [sum(durs[a:b]) for a, b in ranges]
        alloc = [max(1, round(N * t / T)) for t in scene_time]
        # 調整總和 = N（多退少補到時間最長的場景）
        order = sorted(range(K), key=lambda i: -scene_time[i])
        d = N - sum(alloc)
        j = 0
        while d != 0 and order:
            i = order[j % K]
            if d > 0:
                alloc[i] += 1; d -= 1
            elif alloc[i] > 1:
                alloc[i] -= 1; d += 1
            j += 1
            if j > 10000:
                break
        segs, off = [], 0
        for (a, b), cnt in zip(ranges, alloc):
            w0 = sent_start[a]
            w1 = sent_start[b] if b < M else T
            pis = list(range(off, min(N, off + cnt))) or [min(N - 1, off)]
            off += len(pis)
            sd = (w1 - w0) / len(pis)
            for k, pi in enumerate(pis):
                segs.append((w0 + k * sd, w0 + (k + 1) * sd, pi))
        if segs:
            segs[-1] = (segs[-1][0], T, segs[-1][2])
        return segs
    except Exception:
        pd = T / N
        return [(k * pd, (k + 1) * pd, k) for k in range(N)]


def synth_f5(sentences, ref_audio, tmp):
    """用 F5-TTS（另一個 venv）批次克隆，回傳每句的 wav 路徑（失敗為 None）。"""
    job = tmp / "f5job.json"
    outdir = tmp / "f5out"
    outdir.mkdir(exist_ok=True)
    job.write_text(json.dumps({
        "ref_audio": ref_audio, "ref_text": "",
        "sentences": sentences, "out_dir": str(outdir),
    }, ensure_ascii=False), encoding="utf-8")
    print("[有聲漫畫] 用你的克隆聲音配音中（F5-TTS，第一次會載模型）...")
    subprocess.run([F5_VENV_PY, F5_BATCH, str(job)])
    res = []
    for i in range(len(sentences)):
        w = outdir / ("%04d.wav" % i)
        res.append(w if w.exists() else None)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--voice", default=DEFAULT_VOICE, help="|".join(VOICES))
    ap.add_argument("--engine", default="edge", choices=["edge", "f5"],
                    help="edge=Edge-TTS(預設) / f5=你的本機克隆聲音")
    ap.add_argument("--ref-audio", default=F5_DEFAULT_REF, help="f5 用的參考音檔")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--color", action="store_true")
    grp.add_argument("--bw", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="只唸前 N 句（試做）")
    ap.add_argument("--subtitles", default=None,
                    help="指定可編輯字幕稿；預設 output\\<slug>\\subtitle_script.txt")
    ap.add_argument("--prepare-subtitles", action="store_true",
                    help="只建立/讀取可編輯字幕稿後離開，不配音不合成")
    ap.add_argument("--regen-subtitles", action="store_true",
                    help="用 script.txt 重新產生字幕稿，會覆蓋既有 subtitle_script.txt")
    ap.add_argument("--out", default=None)
    ap.add_argument("--img-dur", type=float, default=0.0, help="每張圖片最低停留秒數")
    ap.add_argument("--sfx", dest="sfx", action="store_true", default=True,
                    help="生成並混入 [音效]（預設開，需 sfx_venv）")
    ap.add_argument("--no-sfx", dest="sfx", action="store_false",
                    help="不生成音效")
    args = ap.parse_args()

    voice = VOICES.get(args.voice, args.voice)
    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    title = sb["title"]
    color = bool(sb.get("color", False))
    if args.color:
        color = True
    if args.bw:
        color = False

    try:
        sentences, speakers, subtitle_path = load_subtitle_sentences(
            sb, custom_path=args.subtitles, regen=args.regen_subtitles)
    except ValueError as e:
        print("[!] %s" % e); sys.exit(1)

    # 多角色分聲：每個講者配一個聲音（自動配 + 寫 voices.json 供人工改）
    voices_map, vpath = assign_voices(speakers, title)
    if args.engine != "f5":
        who = "、".join("%s→%s" % (k, v) for k, v in list(voices_map.items())[:8])
        print("[配音] 角色聲音：%s%s" % (who, " …" if len(voices_map) > 8 else ""))
        print("[配音] 想改聲音就編輯：%s" % vpath)

    if args.prepare_subtitles:
        print("[字幕稿] 請編輯字幕稿與聲音後存檔，再重跑：%s" % subtitle_path)
        return
    if args.limit:
        sentences = sentences[:args.limit]; speakers = speakers[:args.limit]
    if not sentences:
        print("[!] 找不到要唸的文本"); sys.exit(1)
    panels = reading_order_panels(sb)
    if not panels:
        print("[!] 找不到乾淨畫格 panels/"); sys.exit(1)

    out_mp4 = Path(args.out) if args.out else ROOT / "output" / title / (title + "_narrated.mp4")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="narrate_"))
    vname = "你的克隆聲音" if args.engine == "f5" else args.voice
    print("[有聲漫畫] 《%s》唸小說全文：%d 句、%d 畫格，聲音=%s（%s）"
          % (title, len(sentences), len(panels), vname, "彩色" if color else "黑白"))

    # 1) 先配音：f5=一次批次克隆(單一聲)；edge=逐句、每句依講者用不同聲音
    raw_list = [None] * len(sentences)
    if args.engine == "f5":
        raw_list = synth_f5(sentences, args.ref_audio, tmp)
    else:
        for i, s in enumerate(sentences):
            raw = tmp / ("r%04d.mp3" % i)
            vkey = voices_map.get(speakers[i], DEFAULT_VOICE)
            vid = VOICES.get(vkey, VOICES[DEFAULT_VOICE])
            try:
                asyncio.run(tts(s, vid, raw))
                raw_list[i] = raw
            except Exception as e:
                print("  [警告] 配音失敗：%s" % e)
            if (i + 1) % 8 == 0:
                print("  配音 %d/%d" % (i + 1, len(sentences)))

    # 計算需要多少額外停頓來滿足 img-dur
    valid_indices = [i for i, raw in enumerate(raw_list) if raw is not None and Path(raw).exists()]
    if not valid_indices:
        print("[!] 配音全部失敗（需連網）"); sys.exit(1)
        
    M = len(valid_indices)
    N = len(panels)
    raw_durs = [audio_dur(raw_list[i]) for i in valid_indices]
    T_raw = sum(raw_durs)
    T_base = T_raw + M * 0.3
    
    target_T = N * (args.img_dur or 0.0)
    extra_pad = max(0.0, (target_T - T_base) / M) if M > 0 else 0.0
    final_pad = 0.3 + extra_pad
    
    durs, audios = [], []
    valid_sents, valid_speakers = [], []
    for i in valid_indices:
        raw = raw_list[i]
        pad = tmp / ("a%04d.m4a" % i)
        subprocess.run([FFMPEG, "-y", "-i", str(raw), "-af", f"apad=pad_dur={final_pad:.2f}",
                        "-c:a", "aac", "-b:a", "160k", str(pad)], capture_output=True)
        durs.append(audio_dur(pad)); audios.append(pad)
        valid_sents.append(sentences[i]); valid_speakers.append(speakers[i])
    sentences = valid_sents; speakers = valid_speakers

    T = sum(durs)
    N = len(panels)
    sent_start = [sum(durs[:i]) for i in range(len(durs))]

    # 畫格對齊場景：每個 [建議場景] 顯示它自己那段的畫格（比平均分配更貼合劇情）
    try:
        _scr = get_script(sb)
        fracs = script_parser.scene_fractions(_scr) if script_parser.is_screenplay(_scr) else [0.0]
    except Exception:
        fracs = [0.0]
    panel_segs = build_panel_segments(durs, sent_start, T, N, fracs)
    if len(fracs) >= 2:
        print("[畫面] 依 %d 個場景對齊畫格" % len(fracs))

    def panel_idx_at(t):
        for a, b, pi in panel_segs:
            if a - 1e-6 <= t < b + 1e-6:
                return pi
        return panel_segs[-1][2] if panel_segs else 0

    # 2) 合成整段旁白音軌
    alist = tmp / "alist.txt"
    alist.write_text("".join("file '%s'\n" % a.as_posix() for a in audios), encoding="utf-8")
    narration = tmp / "narration.m4a"
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(alist),
                    "-c", "copy", str(narration)], capture_output=True)

    # 2b) 本機 AI 生音效並混進旁白（[音效] 在它的時間點播放）
    if args.sfx:
        try:
            sfx_items = script_parser.sfx_with_fraction(get_script(sb))
        except Exception:
            sfx_items = []
        if sfx_items and Path(SFX_VENV_PY).exists():
            eng = sfx_to_english([x["text"] for x in sfx_items])
            sdir = tmp / "sfx"; sdir.mkdir(exist_ok=True)
            (tmp / "sfxjob.json").write_text(json.dumps(
                {"sfx": eng, "out_dir": str(sdir), "len": 4.0}, ensure_ascii=False),
                encoding="utf-8")
            print("[音效] 本機 AI 生成 %d 個音效中（第一次會載模型）..." % len(eng))
            subprocess.run([SFX_VENV_PY, SFX_GEN, str(tmp / "sfxjob.json")])
            wavs = []
            for i, it in enumerate(sfx_items):
                w = sdir / ("%04d.wav" % i)
                if w.exists():
                    wavs.append((w, min(T - 0.5, max(0.0, it["frac"] * T))))
            if wavs:
                inputs = ["-i", str(narration)]
                for w, _ in wavs:
                    inputs += ["-i", str(w)]
                parts, mixlabels = [], "[0]"
                for k, (_, t) in enumerate(wavs):
                    ms = int(t * 1000)
                    parts.append("[%d]adelay=%d:all=1,volume=0.55[s%d]" % (k + 1, ms, k))
                    mixlabels += "[s%d]" % k
                fc = ";".join(parts) + ";" + mixlabels + \
                    "amix=inputs=%d:duration=first:normalize=0[out]" % (len(wavs) + 1)
                mixed = tmp / "narration_sfx.m4a"
                r = subprocess.run([FFMPEG, "-y"] + inputs + ["-filter_complex", fc,
                                    "-map", "[out]", "-c:a", "aac", "-b:a", "160k",
                                    str(mixed)], capture_output=True, text=True)
                if mixed.exists():
                    narration = mixed
                    print("[音效] 已混入 %d 個音效" % len(wavs))
                else:
                    print("[音效] 混音失敗，改用純旁白：\n" + (r.stderr or "")[-400:])
        elif sfx_items:
            print("[音效] 略過（找不到 sfx_venv，還沒裝音效模型）")

    # 3) 聯合時間軸（畫格切換點 ∪ 句子切換點）→ 每段一張已燒字幕的 frame
    bounds = set([0.0, T])
    for seg in panel_segs:
        bounds.add(round(seg[1], 3))
    for st in sent_start[1:]:
        bounds.add(round(st, 3))
    times = sorted(t for t in bounds if 0 <= t <= T)

    def sent_idx_at(t):
        idx = 0
        for i, st in enumerate(sent_start):
            if t >= st - 1e-6:
                idx = i
        return idx

    concat = tmp / "vlist.txt"
    lines_out = []
    for j in range(len(times) - 1):
        t0, t1 = times[j], times[j + 1]
        if t1 - t0 < 0.05:
            continue
        pidx = panel_idx_at(t0)
        sidx = sent_idx_at(t0)
        frame = fit_panel(panels[pidx], color)
        draw_subtitle(frame, sentences[sidx], speakers[sidx])
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
