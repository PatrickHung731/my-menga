# -*- coding: utf-8 -*-
"""全本機一鍵：故事 txt → 分鏡(本機LLM) → 建新角色 → 生圖 → 拼頁。零 Claude token。

連載模式（推薦）:
  python story2manga.py stories\\ep1.txt --series raiden --title-zh 雷光 --style yuyu_hakusho --pages 8
  之後直接:
  python story2manga.py stories\\ep2.txt          ← 自動接上次的連載（series\\default.txt）
  每話輸出 output\\<連載名>_epNN\\，角色/畫風/頁數/前情提要自動延續。

單篇模式:
  python story2manga.py stories\\oneshot.txt --oneshot [--style X] [--max-pages N]

其他:
  --storyboard-only   只出分鏡 JSON 不生圖（先審分鏡）
  --engine ollama     全離線編劇
  --redo              分格已存在也重生
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdxl_graph import STYLE_PRESETS
from write_storyboard import write_storyboard

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
        sys.exit(r.returncode)


def load_series(name, args):
    path = SERIES_DIR / (name + ".json")
    if path.exists():
        s = json.loads(path.read_text(encoding="utf-8"))
    else:
        s = {"name": name,
             "title_zh": args.title_zh or name,
             "style": args.style or "shonen_90s",
             "color": bool(args.color),
             "pages_per_episode": args.pages or 8,
             "rating": args.rating or "safe",
             "lang": args.lang or "auto",
             "next_ep": 1,
             "characters": {},   # id -> 中文名
             "episodes": []}
        print("[連載] 建立新連載《%s》(%s) 風格=%s 每話 %d 頁"
              % (s["title_zh"], name, s["style"], s["pages_per_episode"]))
    return path, s


def save_series(path, s):
    SERIES_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def remap_characters(sb, series):
    """LLM 違規重建已有角色時自動併回；全新角色撞到全域同名資料夾時改名。
    回傳真正需要建立的新角色 list。"""
    cast = series["characters"] if series else {}
    zh_to_id = {zh: cid for cid, zh in cast.items() if zh}
    remap, to_create = {}, []
    for nc in sb.get("new_characters", []):
        cid = nc.get("name", "").strip()
        zh = (nc.get("name_zh") or "").strip()
        if not cid:
            continue
        if zh and zh in zh_to_id and zh_to_id[zh] != cid:
            print("[連戲] LLM 想重建「%s」→ 併回現有角色 %s" % (zh, zh_to_id[zh]))
            remap[cid] = zh_to_id[zh]
            continue
        if cid in cast:      # id 已在本連載名單，不必重建
            continue
        if series and (ROOT / "characters" / cid).exists():
            newid = "%s_%s" % (series["name"], cid)   # 撞到別部作品的同名角色
            print("[連戲] 角色 id %s 已被其他作品用掉 → 改名 %s" % (cid, newid))
            remap[cid] = newid
            nc = dict(nc, name=newid)
        to_create.append(nc)
    if remap:
        for page in sb["pages"]:
            for p in page["panels"]:
                p["characters"] = [remap.get(c, c) for c in p.get("characters", [])]
                for d in p.get("dialogues", []):
                    if d.get("speaker") in remap:
                        d["speaker"] = remap[d["speaker"]]
        sb["new_characters"] = to_create
    return to_create


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story", help="故事 txt 檔路徑")
    ap.add_argument("--series", default=None, help="連載名（英文）；省略時讀 series\\default.txt")
    ap.add_argument("--oneshot", action="store_true", help="單篇模式，不掛連載")
    ap.add_argument("--title-zh", default=None, help="首次建連載時的中文標題")
    ap.add_argument("--pages", type=int, default=None, help="這一話固定頁數（連載預設吃設定檔）")
    ap.add_argument("--engine", default="gemini", choices=["gemini", "ollama"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--style", default=None, help="|".join(STYLE_PRESETS))
    ap.add_argument("--color", action="store_true")
    ap.add_argument("--max-pages", type=int, default=None, help="單篇模式的頁數上限")
    ap.add_argument("--out", default=None)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--storyboard-only", action="store_true", help="只出分鏡不生圖")
    ap.add_argument("--final", action="store_true", help="最終話：完結感分鏡+蓋「完」章+連載標記完結")
    ap.add_argument("--rating", default=None, choices=["safe", "r15"],
                    help="內容分級：safe=全年齡(預設) / r15=血腥+成年角色輕度性感（無裸露）")
    ap.add_argument("--lang", default=None, choices=["auto", "zh", "en", "ja"],
                    help="對白語言：auto=依故事自動判定(預設) / zh / en / ja")
    args = ap.parse_args()

    story = Path(args.story).read_text(encoding="utf-8")

    # ---- 連載 or 單篇 ----
    series, spath = None, None
    sname = args.series
    if not sname and not args.oneshot:
        dfile = SERIES_DIR / "default.txt"
        if dfile.exists():
            sname = dfile.read_text(encoding="utf-8").strip() or None
            if sname:
                print("[連載] 沿用預設連載: %s（要單篇請加 --oneshot）" % sname)
    if sname:
        spath, series = load_series(sname, args)
        SERIES_DIR.mkdir(exist_ok=True)
        (SERIES_DIR / "default.txt").write_text(sname, encoding="utf-8")

    if series and series.get("completed"):
        print("[連載] 《%s》已完結（第 %d 話收官）。要開新作品用 --series 新名字，"
              "或手動把 series\\%s.json 的 completed 改掉。"
              % (series["title_zh"], series["next_ep"] - 1, series["name"]))
        sys.exit(1)

    if series:
        ep = series["next_ep"]
        slug = args.out or ("%s_ep%02d" % (series["name"], ep))
        style = args.style or series["style"]
        color = args.color or series["color"]
        exact_pages = args.pages or series["pages_per_episode"]
        cast = dict(series["characters"])
        prev = [e["synopsis"] for e in series["episodes"][-3:] if e.get("synopsis")]
        print("[連載] 《%s》第 %d 話 → %s（%d 頁, %s）"
              % (series["title_zh"], ep, slug, exact_pages, style))
        if args.final:
            print("[連載] ★這是《%s》的最終話" % series["title_zh"])
        rating = args.rating or series.get("rating", "safe")
        lang = args.lang or series.get("lang", "auto")
        sb_path, sb = write_storyboard(story, engine=args.engine, model=args.model,
                                       style=style, color=color, out_name=slug,
                                       exact_pages=exact_pages, cast=cast,
                                       prev_synopses=prev, final=args.final,
                                       rating=rating, lang=lang)
        to_create = remap_characters(sb, series)
        sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        style = args.style or "shonen_90s"
        sb_path, sb = write_storyboard(story, engine=args.engine, model=args.model,
                                       style=style, color=args.color,
                                       max_pages=args.max_pages, out_name=args.out,
                                       final=args.final,
                                       rating=args.rating or "safe",
                                       lang=args.lang or "auto")
        to_create = remap_characters(sb, None)
        sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.series and not args.oneshot and not (SERIES_DIR / "default.txt").exists():
            print("[提示] 這是單篇模式。想做連載請加 --series 名字（角色/畫風/頁數會自動延續）")

    if args.storyboard_only:
        print("[分鏡] 只出分鏡模式，結束。審完跑同指令（去掉 --storyboard-only）即可生圖。")
        print("       注意：正式生圖時會重新編劇一次；若要沿用這份分鏡，直接跑 make_manga.py %s" % sb_path)
        return

    # ---- 建新角色（設定圖 + tags，之後每格自動鎖臉）----
    for nc in to_create:
        name = nc["name"]
        cdir = ROOT / "characters" / name
        if not (cdir / "ref.png").exists():
            cmd = [sys.executable, str(HERE / "new_character.py"),
                   "--name", name, "--tags", nc.get("tags", ""),
                   "--gender", nc.get("gender", "1boy"), "--style", sb["style"]]
            if not sb.get("color"):
                cmd.append("--bw")
            run(cmd)
        zh = (nc.get("name_zh") or "").strip()
        if zh:
            (cdir / "name_zh.txt").write_text(zh, encoding="utf-8")
        if series is not None:
            series["characters"][name] = zh or name

    # ---- 生圖 + 拼頁 ----
    cmd = [sys.executable, str(HERE / "generate_panels.py"), str(sb_path)]
    if args.redo:
        cmd.append("--redo")
    run(cmd)
    run([sys.executable, str(HERE / "compose_pages.py"), str(sb_path)])

    # ---- 連載進度存檔 ----
    if series is not None:
        series["episodes"].append({
            "ep": series["next_ep"], "slug": sb["title"],
            "story_file": str(Path(args.story)),
            "synopsis": sb.get("synopsis", ""),
            "final": bool(args.final)})
        series["next_ep"] += 1
        if args.final:
            series["completed"] = True
            save_series(spath, series)
            dfile = SERIES_DIR / "default.txt"
            if dfile.exists() and dfile.read_text(encoding="utf-8").strip() == series["name"]:
                dfile.unlink()
            print("[連載] ★《%s》全 %d 話完結！感謝連載～（已解除預設連載）"
                  % (series["title_zh"], len(series["episodes"])))
        else:
            save_series(spath, series)
            print("[連載] 進度已存檔：下一話是第 %d 話" % series["next_ep"])

        # ---- 第一話完成 → 自動生成封面（沒有才生） ----
        cover_png = ROOT / "covers" / (series["name"] + ".png")
        if not cover_png.exists() and series["characters"]:
            print("[封面] 首話完成，自動生成連載封面 ...")
            subprocess.run([sys.executable, str(HERE / "make_cover.py"),
                            "--series", series["name"]])

    pages_dir = ROOT / "output" / sb["title"] / "pages"
    print("\n=== 完成！成品: %s ===" % pages_dir)
    try:
        os.startfile(pages_dir)
    except Exception:
        pass


if __name__ == "__main__":
    main()
