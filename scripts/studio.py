# -*- coding: utf-8 -*-
"""MangaStudio 互動工作台 —— 雙擊 MangaStudio.bat 進來，選數字操作。

所有功能都在選單裡：出下一話 / 最終話 / 重抽某格 / 改對白 / 審分鏡 / 開新連載 / 單篇。
txt 路徑可以直接把檔案「拖進這個視窗」再按 Enter。
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdxl_graph import STYLE_PRESETS

ROOT = Path(__file__).resolve().parents[1]
SERIES_DIR = ROOT / "series"
PY = sys.executable
SCRIPTS = ROOT / "scripts"
F5_REFS = {
    "f5_60": ROOT / "voice" / "patrick_ref_60s.wav",
    "f5_300": ROOT / "voice" / "patrick_ref_300s.wav",
    "f5_600": ROOT / "voice" / "patrick_ref_600s.wav",
}

if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

STYLE_MENU = [
    ("auto", "⭐ AI 自動判斷最適合的風格"),
    # ── 經典少年漫畫 ──
    ("dragon_ball", "七龍珠風（鳥山明）"),
    ("one_piece", "海賊王風（尾田）"),
    ("yuyu_hakusho", "幽遊白書風（富堅）"),
    ("slam_dunk", "灌籃高手風（井上）"),
    ("naruto", "火影忍者風（岸本）"),
    ("video_girl_ai", "電影少女風（桂正和）"),
    ("kungfu_boy", "鐵拳對鋼拳風（80年代格鬥）"),
    ("shonen_90s", "通用九零少年漫"),
    # ── 經典作家風 ──
    ("jojo", "JOJO 風（荒木飛呂彥）"),
    ("clamp", "CLAMP 風（魔法騎士/庫洛牌）"),
    ("rumiko", "高橋留美子風（乱馬/犬夜叉）"),
    ("bleach", "死神風（久保帶人）"),
    ("aot", "進擊的巨人風（諫山創）"),
    ("chainsaw", "鏈鋸人風（藤本樹）"),
    # ── 少女漫畫 ──
    ("shoujo", "少女漫畫風（花朵/閃亮）"),
    # ── 現代動畫/電影風 ──
    ("modern_anime", "現代動畫風"),
    ("shinkai", "新海誠風（你的名字）"),
    ("ghibli", "吉卜力風（宮崎駿）"),
    # ── 海外風格 ──
    ("marvel", "美漫風（Marvel/DC）"),
    ("webtoon", "韓漫 Webtoon 風"),
    ("disney_3d", "迪士尼/皮克斯 3D 風"),
]


def ask(msg, default=""):
    try:
        s = input(msg)
    except EOFError:
        raise SystemExit(0)
    # 清 BOM/亂碼前綴（管線測試才會出現，鍵盤輸入不受影響）
    s = s.replace("﻿", "").replace("\udcbb", "").replace("\udcbf", "").replace("嚜", "")
    return s.strip().strip('"').strip("'") or default


def run(script, *args):
    print("-" * 56)
    r = subprocess.run([PY, str(SCRIPTS / script)] + [str(a) for a in args])
    print("-" * 56)
    if r.returncode != 0:
        print("[!] 執行失敗（exit %s），錯誤訊息看上面。" % r.returncode)
    return r.returncode == 0


def current_series():
    f = SERIES_DIR / "default.txt"
    if f.exists():
        name = f.read_text(encoding="utf-8").strip()
        p = SERIES_DIR / (name + ".json")
        if name and p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def save_series(s):
    SERIES_DIR.mkdir(exist_ok=True)
    (SERIES_DIR / (s["name"] + ".json")).write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def set_default(name):
    SERIES_DIR.mkdir(exist_ok=True)
    (SERIES_DIR / "default.txt").write_text(name, encoding="utf-8")


def resolve_txt_path(p):
    path = Path(p)
    if not path.exists():
        alt = ROOT / "stories" / p
        if alt.exists():
            return alt
        print("[!] 找不到檔案:", p)
        return None
    return path


def ask_txt():
    p = ask("故事 txt 路徑（把檔案拖進這視窗再按 Enter）> ")
    if not p:
        return None
    return resolve_txt_path(p)


def open_pages(slug):
    d = ROOT / "output" / slug / "pages"
    if d.exists():
        try:
            os.startfile(d)
        except Exception:
            pass


def pick_episode(s, msg="哪一話？"):
    latest = s["next_ep"] - 1
    if latest < 1:
        print("[!] 這部連載還沒有任何一話。")
        return None
    n = ask("%s(數字 1~%d, Enter=第 %d 話) > " % (msg, latest, latest), str(latest))
    try:
        n = int(n)
    except ValueError:
        print("[!] 請輸入數字")
        return None
    if not (1 <= n <= latest):
        print("[!] 沒有第 %d 話" % n)
        return None
    return "%s_ep%02d" % (s["name"], n)


def storyboard_slug(path):
    try:
        sb = json.loads(path.read_text(encoding="utf-8"))
        return sb.get("title") or path.stem
    except Exception:
        return path.stem


def slugify_name(text, fallback="audio_novel"):
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(text)).strip("_").lower()
    s = re.sub(r"_+", "_", s)
    return s or fallback


def unique_story_slug(txt):
    base = slugify_name(Path(txt).stem)
    slug = base
    if (ROOT / "storyboards" / (slug + ".json")).exists() or (ROOT / "output" / slug).exists():
        slug = "%s_%s" % (base, time.strftime("%m%d_%H%M%S"))
    return slug


def pick_storyboard_file():
    files = sorted((ROOT / "storyboards").glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("[!] 找不到任何分鏡檔。先用 [7] 做單篇，或用 [1] 出一話。")
        return None, None
    print("目前沒有進行中的連載。請選一個已生成的分鏡來做有聲影片：")
    entries = files[:30]
    for i, f in enumerate(entries, 1):
        label = f.stem
        extra = ""
        try:
            sb = json.loads(f.read_text(encoding="utf-8"))
            label = sb.get("title") or label
            extra = "，%d 頁" % len(sb.get("pages", []))
        except Exception:
            extra = "，分鏡檔讀取有問題"
        print("  [%d] %s（%s%s）" % (i, label, f.name, extra))
    c = ask("選分鏡（Enter=最新）> ", "1")
    try:
        f = entries[int(c) - 1]
    except Exception:
        print("[!] 選擇無效")
        return None, None
    return storyboard_slug(f), f


def do_episode(final=False):
    s = current_series()
    if s is None:
        print("[!] 還沒有進行中的連載，先用 [6] 開一部。")
        return
    if s.get("completed"):
        print("[!] 《%s》已完結。想出番外請用 [6] 開新連載或 [7] 單篇。" % s["title_zh"])
        return
    txt = ask_txt()
    if txt is None:
        return

    # 這一話幾頁？每次都能改，預設=連載當初設的數字（直接 Enter 沿用）
    default_pages = s.get("pages_per_episode", 8)
    pg = ask("這一話畫幾頁？(Enter=%d 頁) > " % default_pages, str(default_pages))
    try:
        pages = str(int(pg))
    except ValueError:
        print("[!] 不是數字，用預設 %d 頁" % default_pages)
        pages = str(default_pages)

    if final:
        ok = ask("★最終話跑完會把《%s》標記完結，之後不能再加話。確定？(y/N) > " % s["title_zh"])
        if ok.lower() != "y":
            print("已取消。")
            return
        if run("story2manga.py", txt, "--pages", pages, "--final"):
            print("★ 完結撒花！最後一頁已蓋「完」章。")
    else:
        run("story2manga.py", txt, "--pages", pages)


def do_redo():
    s = current_series()
    if s is None:
        print("[!] 沒有進行中的連載（單篇的話直接告訴 Claude 或用 redo.bat <slug> 頁:格）。")
        return
    slug = pick_episode(s, "要修哪一話？")
    if slug is None:
        return
    sb_json = ROOT / "storyboards" / (slug + ".json")
    if not sb_json.exists():
        print("[!] 找不到分鏡檔:", sb_json)
        return
    pp = ask("重抽哪一格？頁:格（如 2:3）> ")
    if ":" not in pp:
        print("[!] 格式要像 2:3")
        return
    e = ask("要先改這格的畫面 prompt 嗎？(y=開啟分鏡檔編輯 / Enter=直接重抽換運氣) > ")
    if e.lower() == "y":
        os.startfile(sb_json)
        ask("改好「存檔」後回來按 Enter 繼續 > ")
    if run("generate_panels.py", sb_json, "--only", pp, "--redo"):
        run("compose_pages.py", sb_json)
        open_pages(slug)
        print("改好了。要讓線上網站也更新 → 按 [p] 發布。")


def do_dialog():
    s = current_series()
    if s is None:
        print("[!] 沒有進行中的連載。")
        return
    slug = pick_episode(s, "要改哪一話的對白？")
    if slug is None:
        return
    sb_json = ROOT / "storyboards" / (slug + ".json")
    if not sb_json.exists():
        print("[!] 找不到分鏡檔:", sb_json)
        return
    print("開啟分鏡檔了，在 dialogues 裡改這兩個欄位，存檔後回來：")
    print("  text : 對白文字（\\n 可換行）")
    print("  pos  : 氣泡位置——氣泡遮到臉就改這個，搬到沒人的角落")
    print("         可填：top-left / top-right / bottom-left / bottom-right")
    print("               / top / bottom / left / right / center")
    print("  （同一格有兩句對白時，兩個 pos 要放對角，例如一個 top-right、一個 bottom-left）")
    os.startfile(sb_json)
    ask("改好「存檔」後按 Enter 重拼頁 > ")
    if run("compose_pages.py", sb_json):
        open_pages(slug)
        print("改好了。要讓線上網站也更新 → 按 [p] 發布。")


def do_preview():
    txt = ask_txt()
    if txt is None:
        return
    run("story2manga.py", txt, "--storyboard-only")


def choose_style(allow_auto=True):
    print("選畫風：")
    valid_menu = STYLE_MENU if allow_auto else [m for m in STYLE_MENU if m[0] != "auto"]
    for i, (k, zh) in enumerate(valid_menu, 1):
        print("  [%d] %s (%s)" % (i, zh, k))
    c = ask("> ", "9" if allow_auto else "8")
    try:
        return valid_menu[int(c) - 1][0]
    except Exception:
        return "shonen_90s"


def do_series_menu():
    files = sorted(SERIES_DIR.glob("*.json")) if SERIES_DIR.exists() else []
    print("連載清單：")
    entries = []
    for i, f in enumerate(files, 1):
        s = json.loads(f.read_text(encoding="utf-8"))
        state = "已完結" if s.get("completed") else ("進行中，下一話第 %d 話" % s["next_ep"])
        print("  [%d] 《%s》(%s) — %s" % (i, s["title_zh"], s["name"], state))
        entries.append(s)
    print("  [n] 開一部新連載")
    c = ask("> ")
    if c.lower() == "n":
        name = ask("英文代號（當資料夾名，如 raiden）> ")
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            print("[!] 代號要英文數字")
            return
        if (SERIES_DIR / (name + ".json")).exists():
            print("[!] 這個代號已存在，直接切換過去。")
            set_default(name)
            return
        title = ask("作品中文名 > ", name)
        style = choose_style()
        pages = ask("預設每話幾頁？(Enter=8；每次出稿時還能個別調整) > ", "8")
        color = ask("彩色？(y=彩色 / Enter=黑白漫畫) > ").lower() == "y"
        r = ask("內容分級？(Enter=全年齡 / 2=R15 血腥+成年角色輕度性感,無裸露) > ")
        rating = "r15" if r.strip() == "2" else "safe"
        lg = ask("對白語言？(Enter=跟著故事自動判定 / z=中文 / e=英文 / j=日文) > ").lower()
        lang = {"z": "zh", "e": "en", "j": "ja"}.get(lg, "auto")
        s = {"name": name, "title_zh": title, "style": style, "color": color,
             "pages_per_episode": int(pages), "rating": rating, "lang": lang,
             "next_ep": 1, "characters": {}, "episodes": []}
        save_series(s)
        set_default(name)
        print("《%s》建好了！回主選單用 [1] 出第一話。" % title)
    elif c.isdigit() and 1 <= int(c) <= len(entries):
        s = entries[int(c) - 1]
        set_default(s["name"])
        print("已切換到《%s》。" % s["title_zh"])


def do_oneshot():
    txt = ask_txt()
    if txt is None:
        return
    style = choose_style()
    pages = ask("最多幾頁？(Enter=4) > ", "4")
    run("story2manga.py", txt, "--oneshot", "--style", style, "--max-pages", pages)


def do_deploy():
    if not (ROOT / ".git").exists():
        print("[!] 這裡還不是 git repo，無法推 GitHub。請先請 Claude 幫你接好一次。")
        return
    print("發布網站 + 推上 GitHub（改完對白/封面後用這個把線上更新）...")
    if run("deploy.py"):
        print("線上網址：https://patrickhung731.github.io/my-menga/")


def _offer_deploy():
    if (ROOT / ".git").exists():
        if ask("要順便發布到線上網站嗎？(Enter=是 / n=先不要) > ").lower() != "n":
            run("deploy.py")


def do_restyle():
    s = current_series()
    if s is None:
        print("[!] 沒有進行中的連載。")
        return
    print("目前畫風：%s。要改成哪一種？" % s["style"])
    new_style = choose_style(allow_auto=False)
    col = ask("彩色還黑白？(Enter=不變 / c=彩色 / b=黑白) > ").lower()
    col_flag = "--color" if col == "c" else ("--bw" if col == "b" else None)

    # 先試做幾頁預覽（非破壞，完全不動現有內容）
    n = ask("先試做幾頁看看？(Enter=2 頁 / 0=不試、直接全部重畫) > ", "2")
    try:
        npv = int(n)
    except ValueError:
        npv = 2
    if npv > 0:
        pcmd = ["preview_style.py", "--series", s["name"], "--style", new_style, "--pages", str(npv)]
        if col_flag:
            pcmd.append(col_flag)
        if not run(*pcmd):
            return
        print("↑ 樣張資料夾已開啟，看看喜不喜歡（現有內容一格都沒動）。")
        if ask("要用這個畫風把整部重畫嗎？(y=全部重畫 / 其他=先不要) > ").lower() != "y":
            print("好，先不動。想換別的畫風再選一次 [s]；試做樣張留在 output\\_previews\\。")
            return
    else:
        print("⚠ 這會【重畫整部連載所有頁】＋重繪角色，會跑好一陣子（每格約20~40秒）。")
        if ask("確定改整部畫風？(y/N) > ").lower() != "y":
            print("已取消。")
            return

    cmd = ["restyle.py", "--series", s["name"], "--style", new_style]
    if col_flag:
        cmd.append(col_flag)
    if run(*cmd):
        _offer_deploy()


def pick_existing_narrate_storyboard():
    s = current_series()
    if s is not None:
        mode = ask("選現有來源：Enter=目前連載選一話 / a=全部分鏡清單 > ").lower()
        if mode == "a":
            return pick_storyboard_file()
        slug = pick_episode(s, "要把哪一話做成有聲漫畫影片？")
        if slug is None:
            return None, None
        sb_json = ROOT / "storyboards" / (slug + ".json")
        if not sb_json.exists():
            print("[!] 找不到分鏡檔:", sb_json)
            return None, None
        return storyboard_slug(sb_json), sb_json
    return pick_storyboard_file()


def build_audio_novel_storyboard(txt):
    slug = unique_story_slug(txt)
    print("有聲小說模式：先依 TXT 自動分鏡/分頁/生圖，再用乾淨畫格配音加字幕。")
    print("影片會使用 output\\%s\\panels\\ 的無對白畫格，不用 pages\\ 的對白頁。" % slug)
    style = choose_style()

    pages = ask("最多生成幾頁？(Enter=8；編劇會在上限內自動分頁 / 0=不限制) > ", "8")
    try:
        max_pages = int(pages)
    except ValueError:
        print("[!] 不是數字，用預設 8 頁上限。")
        max_pages = 8

    color = ask("彩色？(y=彩色 / Enter=黑白漫畫) > ").lower() == "y"
    r = ask("內容分級？(Enter=全年齡 / 2=R15 血腥+成年角色輕度性感,無裸露) > ")
    rating = "r15" if r.strip() == "2" else "safe"
    lg = ask("字幕/對白語言？(Enter=跟著故事自動判定 / z=中文 / e=英文 / j=日文) > ").lower()
    lang = {"z": "zh", "e": "en", "j": "ja"}.get(lg, "auto")

    cmd = ["story2manga.py", txt, "--oneshot", "--narrated", "--style", style,
           "--out", slug, "--rating", rating, "--lang", lang]
    if max_pages > 0:
        cmd += ["--max-pages", str(max_pages)]
    if color:
        cmd.append("--color")

    print("輸出代號：%s" % slug)
    if not run(*cmd):
        return None, None

    sb_json = ROOT / "storyboards" / (slug + ".json")
    if not sb_json.exists():
        print("[!] 已跑完生圖，但找不到分鏡檔：", sb_json)
        return None, None
    return storyboard_slug(sb_json), sb_json


def run_narrate_for_storyboard(slug, sb_json):
    print("唸的是整篇小說原文（生成時存的 script.txt），乾淨畫格自動平均分配。")
    print("選配音（先去 output\\_voice_samples\\ 試聽）：")
    voice_menu = [
        ("f5_300", "★ 你的克隆聲音 F5（300秒參考，平衡）"),
        ("f5_60", "你的克隆聲音 F5（60秒參考，較乾淨）"),
        ("f5_600", "你的克隆聲音 F5（600秒參考，音色資訊最多）"),
        ("xiaoxiao", "曉曉 陸女·最自然"),
        ("xiaoyi", "曉伊 陸女·年輕活潑"),
        ("yunxi", "雲希 陸男·年輕有活力"),
        ("yunjian", "雲健 陸男·熱血激昂"),
        ("yunyang", "雲揚 陸男·沉穩旁白"),
        ("yunxia", "雲夏 陸男·可愛少年"),
        ("tw_male", "雲哲 台灣男"),
        ("tw_female", "曉臻 台灣女"),
        ("tw_girl", "曉雨 台灣女"),
        ("hk_female", "曉佳 香港女"),
        ("hk_male", "雲龍 香港男"),
    ]
    for i, (k, zh) in enumerate(voice_menu, 1):
        print("  [%d] %s (%s)" % (i, zh, k))
    vc = ask("> ", "1")
    try:
        voice = voice_menu[int(vc) - 1][0]
    except Exception:
        voice = "f5_300"
    col = ask("彩色還黑白？(Enter=依這話設定 / c=彩色 / b=黑白) > ").lower()
    lim = ask("先試做前幾句？(Enter=整篇 / 輸入數字=只唸前 N 句) > ")
    edit = ask("要先校對字幕稿嗎？(Enter=開啟字幕稿 / n=直接生成 / r=重建字幕稿再開) > ").lower()
    if edit != "n":
        prep = ["narrate.py", str(sb_json), "--prepare-subtitles"]
        if edit == "r":
            prep.append("--regen-subtitles")
        if not run(*prep):
            return
        subtitle_file = ROOT / "output" / slug / "subtitle_script.txt"
        try:
            os.startfile(str(subtitle_file))
        except Exception:
            print("字幕稿位置：", subtitle_file)
        ask("改好字幕稿並存檔後，回來按 Enter 開始配音/合成 > ")
    cmd = ["narrate.py", str(sb_json)]
    if voice.startswith("f5_"):
        ref = F5_REFS.get(voice)
        if ref and not ref.exists():
            print("[!] 找不到 F5 參考音檔：%s" % ref)
            return
        cmd += ["--engine", "f5"]
        if ref:
            cmd += ["--ref-audio", str(ref)]
    else:
        cmd += ["--voice", voice]
    if col == "c":
        cmd.append("--color")
    elif col == "b":
        cmd.append("--bw")
    if lim.isdigit():
        cmd += ["--limit", lim]
        
    dur = ask("每張圖片最少停留幾秒？(Enter=隨配音長短自動決定 / 數字=最低秒數，例: 5) > ")
    try:
        if dur and float(dur) > 0:
            cmd += ["--img-dur", dur]
    except ValueError:
        pass
        
    if run(*cmd):
        vid = ROOT / "output" / slug / (slug + "_narrated.mp4")
        print("有聲漫畫影片好了：%s" % vid)
        
        # ── YouTube 上傳 ──
        s = current_series()
        yt_title = (s.get("title_zh") if s else None) or slug
        if "_ep" in slug:
            yt_title += " 第%s話" % slug.split("_ep")[-1]
        if (ROOT / "client_secrets.json").exists():
            if ask("\n要自動上傳到 YouTube 嗎？(Enter=是 / n=先不要) > ").lower() != "n":
                pv = ask("隱私？(Enter=unlisted有連結才看 / p=私人 / o=公開) > ").lower()
                privacy = {"p": "private", "o": "public"}.get(pv, "unlisted")
                print("上傳中（第一次會開瀏覽器要你登入/授權 Google）...")
                # 邊上傳邊顯示，同時把輸出收下來抓 YouTube_ID
                res = subprocess.run(
                    [PY, str(SCRIPTS / "upload_youtube.py"), "--file", str(vid),
                     "--title", yt_title, "--desc", "AI 生成有聲小說漫畫。",
                     "--privacy", privacy],
                    text=True, encoding="utf-8", errors="replace",
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                print(res.stdout)
                m = re.search(r"YouTube_ID=([0-9A-Za-z_-]{11})", res.stdout or "")
                if m:
                    yt_id = m.group(1)
                    print("✅ 上傳成功：https://youtu.be/%s" % yt_id)
                    if s:
                        for ep in s.get("episodes", []):
                            if ep.get("slug") == slug:
                                ep["youtube_id"] = yt_id; save_series(s); break
                else:
                    print("[!] 沒抓到影片 ID，可能上傳失敗或需重新授權（看上面訊息）。")
        else:
            print("（找不到 client_secrets.json，略過自動上傳）")
        try:
            os.startfile(str(vid))
        except Exception:
            open_pages(slug)


def do_narrate():
    p = ask("小說 txt 路徑（拖入 TXT 開始有聲小說；輸入 e=選現有話/分鏡重做影片）> ")
    if not p:
        return
    if p.lower() in ("e", "old", "existing"):
        slug, sb_json = pick_existing_narrate_storyboard()
    else:
        txt = resolve_txt_path(p)
        if txt is None:
            return
        slug, sb_json = build_audio_novel_storyboard(txt)
    if sb_json is None:
        return
    run_narrate_for_storyboard(slug, sb_json)


def do_textsize():
    s = current_series()
    if s is None:
        print("[!] 沒有進行中的連載。")
        return
    slug = pick_episode(s, "要調哪一話的字級？")
    if slug is None:
        return
    sb_json = ROOT / "storyboards" / (slug + ".json")
    if not sb_json.exists():
        print("[!] 找不到分鏡檔:", sb_json)
        return
    print("對白/旁白字級（氣泡會跟著變大，太大會擋到角色，可多試幾次）：")
    print("  [1] 小    [2] 中(預設)    [3] 大    [4] 特大")
    lv = ask("選等級 > ", "3")
    if lv not in ("1", "2", "3", "4"):
        print("[!] 請輸入 1~4")
        return
    if run("compose_pages.py", sb_json, "--level", lv):
        open_pages(slug)
        print("字級已套用（只重拼頁，沒重畫圖）。想換大小就再選一次 [t]。")
        print("氣泡擋到角色的話，用 [4] 改那句的 pos 把氣泡搬走。")
        _offer_deploy()


def do_change_char():
    s = current_series()
    if s is None:
        print("[!] 沒有進行中的連載。")
        return
    if not s["characters"]:
        print("[!] 這部還沒有角色。")
        return
    ids = list(s["characters"].keys())
    print("要改哪個角色？")
    for i, cid in enumerate(ids, 1):
        print("  [%d] %s（%s）" % (i, s["characters"][cid], cid))
    c = ask("> ")
    try:
        char_id = ids[int(c) - 1]
    except Exception:
        print("[!] 選擇無效")
        return
    print("怎麼改？")
    print("  直接 Enter = 外觀不變，只換一張臉（換 seed 重抽）")
    print("  或輸入新的英文外觀 tags（例：orange fur, green eyes, torn ear, scar）")
    tags = ask("新外觀 tags > ")
    cmd = ["change_character.py", "--series", s["name"], "--char", char_id]
    if tags:
        cmd += ["--tags", tags]
    g = ask("性別要改嗎？(Enter=不變 / b=改男 1boy / g=改女 1girl) > ").lower()
    if g == "b":
        cmd += ["--gender", "1boy"]
    elif g == "g":
        cmd += ["--gender", "1girl"]
    print("⚠ 會重繪這角色，並重畫所有他出場的分格。")
    if ask("確定？(y/N) > ").lower() != "y":
        print("已取消。")
        return
    if run(*cmd):
        _offer_deploy()


def do_cover():
    s = current_series()
    if s is None:
        print("[!] 沒有進行中的連載。")
        return
    if not s["characters"]:
        print("[!] 這部還沒有角色，先出第一話。")
        return
    print("目前角色：")
    ids = list(s["characters"].keys())
    for i, cid in enumerate(ids, 1):
        print("  [%d] %s（%s）" % (i, s["characters"][cid], cid))
    c = ask("封面主角選誰？(數字, Enter=第1位) > ", "1")
    try:
        char_id = ids[int(c) - 1]
    except Exception:
        char_id = ids[0]
    bw = ask("黑白封面？(Enter=彩色 / b=黑白) > ").lower() == "b"
    cmd = ["make_cover.py", "--series", s["name"], "--char", char_id, "--redo"]
    if bw:
        cmd.append("--bw")
    if run(*cmd):
        print("封面已更新。不滿意就再選一次 [9]，會換一張。")
        print("要讓線上網站也換成新封面 → 按 [p] 發布。")


def do_status():
    s = current_series()
    if s is None:
        print("目前沒有進行中的連載。")
        return
    print("《%s》(%s)  風格=%s  每話 %d 頁  分級=%s  角色 %d 位：%s"
          % (s["title_zh"], s["name"], s["style"], s["pages_per_episode"],
             s.get("rating", "safe"), len(s["characters"]),
             "、".join(s["characters"].values()) or "（無）"))
    for e in s["episodes"]:
        tag = "【完】" if e.get("final") else ""
        print("  第 %d 話%s %s" % (e["ep"], tag, e.get("synopsis", "")[:46]))
    if not s["episodes"]:
        print("  （還沒出過任何一話）")


def do_delete():
    import shutil
    files = sorted(SERIES_DIR.glob("*.json")) if SERIES_DIR.exists() else []
    if not files:
        print("[!] 找不到任何連載資料。")
        return
    print("要刪除哪一部作品？(這會清除分鏡、圖片與設定)")
    for i, f in enumerate(files, 1):
        s = json.loads(f.read_text(encoding="utf-8"))
        print("  [%d] 《%s》(%s)" % (i, s.get("title_zh", ""), s.get("name", "")))
    c = ask("> ")
    try:
        f = files[int(c) - 1]
    except Exception:
        print("[!] 選擇無效")
        return
    s = json.loads(f.read_text(encoding="utf-8"))
    name = s["name"]
    print(f"⚠ 警告：即將永久刪除《{s.get('title_zh', name)}》的所有資料！")
    if ask("確定刪除？(輸入 y 確定) > ").lower() != "y":
        print("已取消。")
        return
    f.unlink(missing_ok=True)
    dfile = SERIES_DIR / "default.txt"
    if dfile.exists() and dfile.read_text(encoding="utf-8").strip() == name:
        dfile.unlink(missing_ok=True)
    for sb in (ROOT / "storyboards").glob(f"{name}*.json"):
        sb.unlink(missing_ok=True)
    for out in (ROOT / "output").glob(f"{name}*"):
        if out.is_dir():
            shutil.rmtree(out, ignore_errors=True)
    (ROOT / "covers" / f"{name}.png").unlink(missing_ok=True)
    (ROOT / "covers" / f"{name}.webp").unlink(missing_ok=True)
    
    # 6. 清除 docs 裡面已發布的殘留網頁與圖片
    for html in (ROOT / "docs" / "read").glob(f"{name}*.html"):
        html.unlink(missing_ok=True)
    for img_dir in (ROOT / "docs" / "images").glob(f"{name}*"):
        if img_dir.is_dir():
            shutil.rmtree(img_dir, ignore_errors=True)
    (ROOT / "docs" / "images" / "covers" / f"{name}.png").unlink(missing_ok=True)
    (ROOT / "docs" / "images" / "covers" / f"{name}.webp").unlink(missing_ok=True)
    
    print(f"已清除 {s.get('title_zh', name)}。如果已經發布過，記得再按 [p] 發布一次來更新網站！")

def main():
    print("=" * 56)
    print("   MangaStudio 漫畫工作台（Ctrl+C 或 [0] 離開）")
    print("=" * 56)
    while True:
        print()
        s = current_series()
        if s:
            state = "已完結" if s.get("completed") else ("下一話：第 %d 話" % s["next_ep"])
            print("目前連載：《%s》 %s  [%s, 每話 %d 頁]"
                  % (s["title_zh"], state, s["style"], s["pages_per_episode"]))
        else:
            print("目前沒有進行中的連載 → 用 [6] 開一部")
        print("""
 [1] 出下一話（拖入故事txt）      [5] 先審分鏡（不生圖）
 [2] 出最終話・完結本作           [6] 開新連載 / 切換連載
 [3] 重抽某一格（可先改prompt）   [7] 單篇短篇
 [4] 改對白/搬氣泡 → 重拼頁      [8] 連載狀態/各話提要
 [9] 重新生成封面                 [p] 發布網站 / 推上 GitHub
 [s] 改整部畫風（全部重畫）       [c] 改某個角色（重繪他的分格）
 [t] 調對白/旁白字級大小          [v] 生成有聲漫畫/小說影片（可校字幕）
 [d] 刪除作品（清空生成資料）     [0] 離開""")
        c = ask("選功能 > ")
        try:
            if c == "1":
                do_episode()
            elif c == "2":
                do_episode(final=True)
            elif c == "3":
                do_redo()
            elif c == "4":
                do_dialog()
            elif c == "5":
                do_preview()
            elif c == "6":
                do_series_menu()
            elif c == "7":
                do_oneshot()
            elif c == "8":
                do_status()
            elif c == "9":
                do_cover()
            elif c in ("p", "P"):
                do_deploy()
            elif c in ("s", "S"):
                do_restyle()
            elif c in ("c", "C"):
                do_change_char()
            elif c in ("t", "T"):
                do_textsize()
            elif c in ("v", "V"):
                do_narrate()
            elif c in ("d", "D"):
                do_delete()
            elif c == "0":
                break
        except KeyboardInterrupt:
            print("\n（已中斷，回主選單）")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
