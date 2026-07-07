# -*- coding: utf-8 -*-
r"""劇本解析器：把「[旁白]/[音效]/[建議場景]/[角色]」這種分鏡劇本格式拆開。

規則（純文字，不吃 GPU）：
- 第X章 / [建議場景 X] / 【…】場景標題 → 分場，不唸出來（拿來驅動畫面）
- [音效] xxx           → 音效提示，不唸出來（可另接音效）
- [旁白]               → 旁白，用旁白聲唸
- [角色名]（語氣…）    → 該角色台詞；（括號語氣）不唸；「」引號去掉
- 沒標記的行           → 接續上一個講者/旁白

回傳 beats 與便利清單。若偵測不到任何標記，視為純小說（整段當旁白）。
"""
import re

# 行首標記： [xxx] 或 【xxx】
TAG_RE = re.compile(r"^[\[【]\s*([^\]】]+?)\s*[\]】]\s*(.*)$")
CHAPTER_RE = re.compile(r"^第.{1,8}[章話回幕]\b|^第.{1,8}[章話回幕][:：]")
SCENE_KW = ("建議場景", "場景", "分鏡", "scene")
SFX_KW = ("音效", "sfx", "sound")
NARR_KW = ("旁白", "narration", "旁", "narrator")

# 語氣括號（不唸）：全形/半形括號整段
PAREN_RE = re.compile(r"[（(][^（）()]*[）)]")
QUOTE_CHARS = "「」『』“”\""


def _clean(text):
    """去掉語氣括號、引號、多餘空白。"""
    text = PAREN_RE.sub("", text)
    text = "".join(c for c in text if c not in QUOTE_CHARS)
    return text.strip()


def _is_scene(tag):
    t = tag.lower()
    return any(k in t for k in [k.lower() for k in SCENE_KW])


def _is_sfx(tag):
    t = tag.lower()
    return any(k in t for k in [k.lower() for k in SFX_KW])


def _is_narr(tag):
    t = tag.strip().lower()
    return t in [k.lower() for k in NARR_KW] or t == "旁白"


def is_screenplay(text):
    """有沒有這種標記格式（有就走解析器，沒有就當純小說）。"""
    hits = 0
    for kw in ("[旁白]", "【旁白】", "[音效]", "【音效】", "[建議場景", "【建議場景",
               "[老師]", "[場景"):
        if kw in text:
            hits += 1
    # 或行首出現 2 個以上 [xxx] 標記
    tagged = sum(1 for ln in text.splitlines() if TAG_RE.match(ln.strip()))
    return hits >= 1 or tagged >= 3


def parse(text):
    beats = []            # {kind, speaker, text}
    cur = ("narration", None)   # (kind, speaker) 接續狀態
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if CHAPTER_RE.match(line):
            beats.append({"kind": "chapter", "speaker": None, "text": line})
            cur = ("narration", None)
            continue
        m = TAG_RE.match(line)
        if m:
            tag, rest = m.group(1).strip(), m.group(2).strip()
            if _is_scene(tag):
                beats.append({"kind": "scene", "speaker": None,
                              "text": (tag + " " + rest).strip()})
                cur = ("narration", None)
                continue
            if _is_sfx(tag):
                beats.append({"kind": "sfx", "speaker": None, "text": rest or tag})
                cur = ("narration", None)
                continue
            if _is_narr(tag):
                cur = ("narration", None)
                c = _clean(rest)
                if c:
                    beats.append({"kind": "narration", "speaker": None, "text": c})
                continue
            # 其餘一律當「講者」（老師 / 軍事AI / 女孩 / 系統機械音 / 眾AI合成音…）
            cur = ("dialogue", tag)
            c = _clean(rest)
            if c:
                beats.append({"kind": "dialogue", "speaker": tag, "text": c})
            continue
        # 無標記行：接續目前講者/旁白
        c = _clean(line)
        if not c:
            continue
        beats.append({"kind": cur[0], "speaker": cur[1], "text": c})
    return beats


def spoken_lines(text):
    """回傳要唸出來的行（旁白+台詞，已清乾淨），跳過音效/場景/章節/語氣。"""
    out = []
    for b in parse(text):
        if b["kind"] in ("narration", "dialogue") and b["text"]:
            out.append({"speaker": b["speaker"], "text": b["text"]})
    return out


def scenes(text):
    """回傳分場清單（[建議場景]/場景標題），拿來驅動畫面生成。"""
    return [b["text"] for b in parse(text) if b["kind"] == "scene"]


def sfx_list(text):
    return [b["text"] for b in parse(text) if b["kind"] == "sfx"]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raw = open(sys.argv[1], encoding="utf-8").read()
    print("是劇本格式：", is_screenplay(raw))
    print("\n=== 要唸的（旁白+台詞）===")
    for s in spoken_lines(raw):
        who = ("[%s] " % s["speaker"]) if s["speaker"] else "(旁白) "
        print(" ", who + s["text"][:50])
    print("\n=== 跳過的音效 ===")
    for x in sfx_list(raw):
        print("  🔊", x[:40])
    print("\n=== 分場（驅動畫面）===")
    for x in scenes(raw):
        print("  🎬", x[:40])
