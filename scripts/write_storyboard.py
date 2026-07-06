# -*- coding: utf-8 -*-
"""本機編劇：故事情節 → 分鏡 storyboard JSON（零 Claude token）。

單篇用法:
  python write_storyboard.py <story.txt> [--engine gemini|ollama] [--model X]
                             [--style shonen_90s] [--color] [--max-pages N] [--out slug]
連載模式由 story2manga.py 呼叫（帶 cast / 前情提要 / 固定頁數）。
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm_client
from sdxl_graph import STYLE_PRESETS

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROMPT_TEMPLATE = """你是資深日本少年漫畫（JUMP 系）的編劇兼分鏡師。把下面的故事改編成漫畫分鏡，只輸出一個 JSON 物件，不要任何其他文字。

JSON 格式（鍵名固定，照抄結構）:
{{
  "title": "英文小寫slug（字母數字底線，當資料夾名）",
  "synopsis": "這一話的前情提要，2~3句話（語言必須與故事原文相同，下一話開頭連戲用）",
  "style": "如果你被要求自動判定風格，請填入你選的風格代碼",
  "new_characters": [
    {{"name": "英文小寫id", "name_zh": "角色在故事中的名稱（語言與故事原文相同）", "tags": "外觀 danbooru tags 英文（髮型/髮色/眼睛/服裝/體型），絕不含 1boy/1girl 人數詞", "gender": "1boy 或 1girl"}}
  ],
  "pages": [
    {{
      "page": 1,
      "layout": [[1], [2, 3], [4]],
      "row_weights": [1.1, 1.0, 0.9],
      "panels": [
        {{
          "id": 1,
          "characters": ["角色id"],
          "prompt": "英文 danbooru tags：人數詞 + 動作 + 表情 + 鏡頭 + 背景 + 漫畫效果",
          "camera": "close-up 或 wide shot 等，可省略",
          "dialogues": [
            {{"speaker": "角色id", "text": "對白文字（語言必須與故事原文相同）", "pos": "top-right", "type": "speech"}}
          ]
        }}
      ]
    }}
  ]
}}

分鏡規則:
1. 每頁 3~5 格。layout 是每列的格子 id（由上到下）；同一列內第一個 id 排在「最右邊」（漫畫由右至左讀）。row_weights 是各列相對高度。
2. 重要時刻給大格（整列一格），對話戲用 2~3 格小格。每一話開頭要有定場鏡頭，結尾留一格「下回引子」的鉤子。
3. panel.prompt 只寫英文 danbooru tags：必含人數詞（solo/1boy/1girl/2boys...）開頭，再加動作、表情、鏡頭角度（from below/from above/close-up/wide shot/dutch angle）、背景、漫畫效果（speed lines/motion blur/impact/emphasis lines/dramatic shadow/debris）。不要寫品質詞、不要寫風格詞、不要重複角色外觀（外觀由 characters 欄位自動帶入）。
   ★ tags 格式鐵則：全小寫、逗號+空格分隔、每個 tag 是 1~3 個「空格分隔」的常用英文詞。
   絕對禁止：底線連接的長片語、把角色名寫進 prompt、句子式描述。
   好例: "2boys, facing each other, fighting stance, school rooftop, chain-link fence, dusk, wide shot, speed lines"
   壞例: "ryne_blocking_attack_with_arm"、"fukurou_retreating_quickly"（❌底線片語+角色名）
   ★人數詞只准用 danbooru 標準：solo / 1boy / 1girl / "1boy, 1girl" / 2boys / 2girls / 3boys / multiple boys。
   禁止自創詞（❌ 2people、3men、two persons）。
4. characters 欄位填出場角色的 id（用「現有角色」或你在 new_characters 宣告的），**依重要度排序（第一個=本格主角，只有他會鎖臉）**。關鍵特寫每格最多一人；雙人同格用 tags 分別描述兩人動作（例 "1boy, 1girl, boy shielding girl, girl hiding behind boy"）；同格 3 人以上時 characters 最多填 1 個主要角色，其餘人物直接在 prompt 用外觀 tags 描述。
5. 對白規則：語言必須與故事原文完全一致（如果故事是英文，對白就必須是英文；故事是中文就用繁體中文）、口語化、每句最多 18 個字或單字（可用 \\n 換行）。type: "speech"=一般, "shout"=吶喊大字, "narration"=旁白框, "sfx"=擬聲字(如 轟/砰/BAM/BOOM)。pos 從 top-left/top-right/bottom-left/bottom-right/top/bottom/left/right/center 選；「右邊的先讀」。每格最多 2 個氣泡 + 1 個 sfx；同格兩個氣泡的 pos 必須「對角錯開」（一個 top-right 就配 bottom-left，不可同邊）。
6. 忠實改編：劇情、事件順序、對白意圖全部照使用者的故事走，不准自行增刪劇情或加新事件；你的工作只是分鏡、運鏡與對白的專業化。
7. ★角色連戲鐵則：故事中的角色若已在「現有角色」名單（用中文名比對），characters 欄位必須用名單裡的 id，絕對禁止在 new_characters 重複建立。只有名單上沒有的全新角色才放 new_characters。
8. ★角色物種判斷：從故事內容判斷角色是否為非人類（貓、狗、獸人、精靈等）。若角色是擬人化動物或獸人，new_characters 的 tags 必須包含對應的物種特徵 danbooru tags。常用參考：
   - 擬人貓/貓人：cat ears, cat tail, animal ears, slit pupils, fangs
   - 擬人犬/犬人：dog ears, dog tail, animal ears, fangs
   - 擬人狐：fox ears, fox tail, animal ears
   - 擬人兔：rabbit ears, rabbit tail, animal ears
   - 通用獸人：furry, animal ears, tail
   同時 panel.prompt 裡也要在人數詞後面加上物種 tag（如 \"1boy, cat ears, cat tail, ...\"）以確保生圖一致。如果故事中的角色是普通人類，就不用加這些 tags。

現有角色（characters 欄位直接用這些 id）:
{existing_chars}
{prev_context}{page_limit}
故事情節:
{story}
"""


def _global_cast():
    """單篇模式：掃 characters/ 資料夾當名單。"""
    cast = {}
    cdir = ROOT / "characters"
    if cdir.exists():
        for d in sorted(cdir.iterdir()):
            if d.is_dir() and (d / "tags.txt").exists():
                zh = ""
                zf = d / "name_zh.txt"
                if zf.exists():
                    zh = zf.read_text(encoding="utf-8").strip()
                cast[d.name] = zh
    return cast


def _char_line(cid, zh):
    tags = ""
    tf = ROOT / "characters" / cid / "tags.txt"
    if tf.exists():
        tags = " ".join(tf.read_text(encoding="utf-8").split())
    label = "%s（中文名：%s）" % (cid, zh) if zh else cid
    return "- %s: %s" % (label, tags)


R15_RULE = ("★內容分級 R15（青年漫畫級，如 JUMP 系暗黑篇章）：戰鬥可以有血、重傷與沉重黑暗的劇情；"
            "成年角色可以有性感但衣著完整的場面（泳裝、緊身衣、曖昧氛圍）。"
            "全作仍維持雜誌連載尺度：不出現裸露或成人內容；"
            "未成年角色（國高中生等）一律全年齡描寫。\n")

LANG_NAME = {"zh": "繁體中文", "en": "English (英文)", "ja": "日本語（日文）"}
# 各語言的擬聲字示範，塞進強制指令避免 LLM 混用
LANG_SFX = {"zh": "轟、砰、咚、唰、喀", "en": "BOOM, BAM, CRASH, WHOOSH, THUD",
            "ja": "ドン、バン、ゴゴゴ、シュッ"}


def detect_lang(text):
    """偵測故事語言：有假名→ja；有漢字但無假名→zh；其餘→en。"""
    has_kana = any("぀" <= c <= "ゟ" or "゠" <= c <= "ヿ" for c in text)
    has_han = any("一" <= c <= "鿿" for c in text)
    if has_kana:
        return "ja"
    if has_han:
        return "zh"
    return "en"


def lang_rule(lang):
    name = LANG_NAME.get(lang, LANG_NAME["zh"])
    return ("★★對白語言（最高優先，凌駕所有其他規則與範例）：所有 dialogues 的 text、"
            "旁白(narration)、擬聲字(sfx) 一律只能用【%s】。就算本提示或範例出現其他語言，"
            "輸出時全部改寫成【%s】，絕對不可混用其他語言。擬聲字範例：%s。\n"
            % (name, name, LANG_SFX.get(lang, LANG_SFX["zh"])))


def build_prompt(story, max_pages=None, exact_pages=None, cast=None, prev_synopses=None,
                 final=False, rating="safe", lang="zh", style="shonen_90s"):
    if cast is None:
        cast = _global_cast()
    existing = "\n".join(_char_line(cid, zh) for cid, zh in cast.items()) \
        or "（目前沒有，全部走 new_characters）"

    prev = ""
    if prev_synopses:
        prev = "前情提要（前幾話的劇情，只供連戲參考，不要把它畫出來）:\n" + \
               "\n".join("- %s" % s for s in prev_synopses) + "\n"

    if exact_pages:
        limit = "頁數規定：這一話固定畫 %d 頁（不多不少）。\n" % exact_pages
    elif max_pages:
        limit = "頁數限制：這段劇情最多畫 %d 頁。\n" % max_pages
    else:
        limit = ""
    if final:
        limit += ("★這是本作的「最終話」：分鏡要有完結感——回收主線、讓角色情緒收尾，"
                  "最後一格用整列大格做收尾畫面（餘韻、遠景、微笑或背影都好），"
                  "絕對不要留下回引子或懸念鉤子。\n")
    if rating == "r15":
        limit += R15_RULE
    if style == "auto":
        style_list = ", ".join(STYLE_PRESETS.keys())
        limit += ("★風格自動判定：請從以下風格代碼中挑選一個最適合此故事的風格：[%s]，"
                  "並填入 JSON 的 `style` 欄位。\n" % style_list)
    limit += lang_rule(lang)
    return PROMPT_TEMPLATE.format(existing_chars=existing, prev_context=prev,
                                  page_limit=limit, story=story.strip())


def validate(sb):
    if not sb.get("pages"):
        raise ValueError("storyboard 沒有 pages")
    for page in sb["pages"]:
        ids_in_layout = [pid for row in page["layout"] for pid in row]
        ids_in_panels = [p["id"] for p in page["panels"]]
        if sorted(ids_in_layout) != sorted(ids_in_panels):
            raise ValueError("第 %s 頁 layout 與 panels 的 id 不一致: %s vs %s"
                             % (page.get("page"), ids_in_layout, ids_in_panels))
        rw = page.get("row_weights")
        if rw and len(rw) != len(page["layout"]):
            page["row_weights"] = None
        for p in page["panels"]:
            p.setdefault("dialogues", [])
            p.setdefault("characters", [])


def slugify(title):
    s = re.sub(r"[^a-z0-9_-]", "", str(title).lower().replace(" ", "_"))
    return s or ("story_" + time.strftime("%m%d_%H%M"))


def write_storyboard(story_text, engine="gemini", model=None, style="shonen_90s",
                     color=False, max_pages=None, out_name=None, retries=2,
                     exact_pages=None, cast=None, prev_synopses=None, final=False,
                     rating="safe", lang=None):
    if lang is None or lang == "auto":
        lang = detect_lang(story_text)
        print("[編劇] 對白語言自動判定：%s" % LANG_NAME.get(lang, lang))
    prompt = build_prompt(story_text, max_pages=max_pages, exact_pages=exact_pages,
                          cast=cast, prev_synopses=prev_synopses, final=final,
                          rating=rating, lang=lang, style=style)
    last_err = None
    for attempt in range(retries + 1):
        try:
            print("[編劇] %s 思考分鏡中...%s" % (engine, ("（第 %d 次重試）" % attempt) if attempt else ""))
            raw = llm_client.generate(prompt, engine=engine, model=model)
            sb = llm_client.extract_json(raw)
            validate(sb)
            break
        except Exception as e:
            last_err = e
            print("[編劇] 失敗: %s" % e)
            time.sleep(8 * (attempt + 1))  # Gemini 503 高峰退避
    else:
        raise RuntimeError("編劇 LLM 連續失敗: %s" % last_err)

    if style == "auto":
        style = sb.get("style", "shonen_90s")
        if style not in STYLE_PRESETS:
            print("[警告] 自動判定的風格 %s 無效，改用 shonen_90s" % style)
            style = "shonen_90s"
        else:
            print("[編劇] AI 自動判定最適合的風格：%s" % style)
    elif style not in STYLE_PRESETS:
        print("[警告] 未知風格 %s，改用 shonen_90s" % style)
        style = "shonen_90s"
    sb["style"] = style
    sb["color"] = bool(color)
    sb["rating"] = rating
    sb["lang"] = lang
    sb["title"] = out_name or slugify(sb.get("title", ""))
    if final:
        sb["final"] = True

    out = ROOT / "storyboards" / (sb["title"] + ".json")
    out.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    npanels = sum(len(p["panels"]) for p in sb["pages"])
    print("[編劇] 完成: %d 頁 %d 格, 新角色 %d 個 → %s"
          % (len(sb["pages"]), npanels, len(sb.get("new_characters", [])), out))
    return out, sb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story", help="故事 txt 檔路徑")
    ap.add_argument("--engine", default="gemini", choices=["gemini", "ollama"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--style", default="shonen_90s", help="auto 或 |".join(STYLE_PRESETS))
    ap.add_argument("--color", action="store_true")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--out", default=None, help="指定輸出 slug")
    ap.add_argument("--lang", default="auto", choices=["auto", "zh", "en", "ja"],
                    help="對白語言（預設 auto=依故事自動判定）")
    args = ap.parse_args()

    story = Path(args.story).read_text(encoding="utf-8")
    write_storyboard(story, engine=args.engine, model=args.model, style=args.style,
                     color=args.color, max_pages=args.max_pages, out_name=args.out,
                     lang=args.lang)


if __name__ == "__main__":
    main()
