#!/usr/bin/env python3
"""MangaStudio — 靜態漫畫閱讀器網站生成器

掃描 series/*.json + output/ 產出完整靜態網站到 docs/。
圖片自動 PNG→WebP 壓縮。

用法:
    python publish.py                      # 發布所有連載
    python publish.py --series raiden      # 只發布「雷光」
    python publish.py --series raiden --series AYU
    python publish.py --quality 80         # 調整 WebP 品質 (預設 82)
"""

import argparse
import json
import shutil
import sys
from html import escape
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("[ERROR] 需要 Pillow。請用 ComfyUI venv 的 python 執行。")
    sys.exit(1)

# ── 路徑常數 ──
ROOT      = Path(__file__).resolve().parent.parent
SERIES_DIR = ROOT / "series"
OUTPUT_DIR = ROOT / "output"
DOCS_DIR   = ROOT / "docs"
STORYBOARD_DIR = ROOT / "storyboards"

# ── HTML 模板片段 ──

BOOK_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M21 4H3a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1zM4 18V6h7v12H4zm9 0V6h7v12h-7z"/></svg>'
UP_ARROW = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><polyline points="18 15 12 9 6 15"></polyline></svg>'


def html_head(title: str, css_path: str = "style.css", js_path: str = "reader.js") -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<meta name="description" content="{escape(title)} — MangaStudio 漫畫閱讀">
<link rel="stylesheet" href="{css_path}">
</head>
<body>
<div class="progress-bar"></div>
"""


def html_tail(js_path: str = "reader.js") -> str:
    return f"""
<footer class="footer">MangaStudio 漫畫閱讀器</footer>
<button class="fab-top" title="回到頂部" aria-label="回到頂部">{UP_ARROW}</button>
<script src="{js_path}"></script>
</body>
</html>"""


# ══════════════════════════════════════════════════
#  資料收集
# ══════════════════════════════════════════════════

def load_series(filter_names: list[str] | None = None) -> list[dict]:
    """載入 series/*.json 並過濾。"""
    all_series = []
    for f in sorted(SERIES_DIR.glob("*.json")):
        data = json.loads(f.read_text("utf-8"))
        if filter_names and data.get("name") not in filter_names:
            continue
        all_series.append(data)
    return all_series


def get_cover_image(slug: str) -> Path | None:
    """取得某話第一頁作為封面。"""
    pages_dir = OUTPUT_DIR / slug / "pages"
    if not pages_dir.exists():
        return None
    pages = sorted(pages_dir.glob("page_*.png"))
    return pages[0] if pages else None


def get_episode_pages(slug: str) -> list[Path]:
    """取得某話所有頁面圖片。"""
    pages_dir = OUTPUT_DIR / slug / "pages"
    if not pages_dir.exists():
        return []
    return sorted(pages_dir.glob("page_*.png"))


# ══════════════════════════════════════════════════
#  圖片處理
# ══════════════════════════════════════════════════

def convert_to_webp(src: Path, dst: Path, quality: int = 82) -> None:
    """PNG → WebP 壓縮（只在 dst 不存在或 src 較新時轉換）。"""
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return  # 已是最新
    dst.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src)
    img.save(dst, "WEBP", quality=quality, method=4)


def publish_images(series_list: list[dict], quality: int = 82) -> dict[str, list[str]]:
    """把所有需要的圖片轉 WebP 到 docs/images/，回傳 {slug: [相對路徑...]}。"""
    result = {}
    for s in series_list:
        for ep in s.get("episodes", []):
            slug = ep["slug"]
            pages = get_episode_pages(slug)
            if not pages:
                print(f"  [SKIP] {slug}: 找不到 output 頁面")
                continue
            rel_paths = []
            for p in pages:
                webp_name = p.stem + ".webp"
                dst = DOCS_DIR / "images" / slug / webp_name
                convert_to_webp(p, dst, quality)
                rel_paths.append(f"images/{slug}/{webp_name}")
            result[slug] = rel_paths
            print(f"  [OK] {slug}: {len(rel_paths)} 頁")

        # 封面：優先用 make_cover.py 生成的正式封面，否則退回第 1 話第 1 頁
        if s.get("episodes"):
            custom_cover = ROOT / "covers" / f"{s['name']}.png"
            if custom_cover.exists():
                cover_src = custom_cover
            else:
                cover_src = get_cover_image(s["episodes"][0]["slug"])
            if cover_src:
                cover_dst = DOCS_DIR / "images" / "covers" / f"{s['name']}.webp"
                convert_to_webp(cover_src, cover_dst, quality=88)

    return result


# ══════════════════════════════════════════════════
#  HTML 生成 — 首頁
# ══════════════════════════════════════════════════

STYLE_NAMES = {
    "dragon_ball": "七龍珠風",
    "one_piece": "海賊王風",
    "yuyu_hakusho": "幽遊白書風",
    "slam_dunk": "灌籃高手風",
    "naruto": "火影忍者風",
    "video_girl_ai": "電影少女風",
    "kungfu_boy": "鐵拳對鋼拳風",
    "shonen_90s": "90年代少年漫",
    "jojo": "JOJO 風",
    "clamp": "CLAMP 風",
    "rumiko": "高橋留美子風",
    "bleach": "死神風",
    "aot": "進擊的巨人風",
    "chainsaw": "鏈鋸人風",
    "shoujo": "少女漫畫風",
    "modern_anime": "現代動畫風",
    "shinkai": "新海誠風",
    "ghibli": "吉卜力風",
    "marvel": "美漫風",
    "webtoon": "韓漫風",
    "disney_3d": "迪士尼3D風",
}


def generate_index(series_list: list[dict], slug_images: dict[str, list[str]]) -> str:
    """生成首頁 HTML。"""
    html = html_head("MangaStudio 漫畫閱讀")
    html += f"""
<nav class="nav">
  <div class="nav__brand">{BOOK_ICON}<span>小楠漫畫</span></div>
  <div class="nav__links"></div>
</nav>

<section class="hero">
  <h1 class="hero__title">創作漫畫</h1>
</section>

<section class="series-grid">
"""

    # 可讀的連載排前面，還沒生成的（敬請期待）排後面
    def _has_playable(s):
        return any(ep["slug"] in slug_images for ep in s.get("episodes", []))
    series_list = sorted(series_list, key=lambda s: 0 if _has_playable(s) else 1)

    for s in series_list:
        name = s["name"]
        title_zh = s.get("title_zh", name)
        completed = s.get("completed", False)
        style_key = s.get("style", "")
        style_label = STYLE_NAMES.get(style_key, style_key)
        episodes = s.get("episodes", [])
        ep_count = len(episodes)

        # 封面：有生成才用圖，否則用佔位板（避免破圖）
        cover_file = DOCS_DIR / "images" / "covers" / f"{name}.webp"
        if cover_file.exists():
            cover_html = (f'<img class="card__cover" src="images/covers/{name}.webp"'
                          f' alt="{escape(title_zh)} 封面" loading="lazy">')
        else:
            cover_html = (f'<div class="card__cover card__cover--placeholder">'
                          f'<span>{escape(title_zh)}</span></div>')

        # 狀態 badge
        if completed:
            status_badge = '<span class="badge badge--completed">✓ 已完結</span>'
        else:
            status_badge = '<span class="badge badge--ongoing">● 連載中</span>'

        # 話數列表
        ep_items = ""
        for ep in episodes:
            slug = ep["slug"]
            ep_num = ep.get("ep", "?")
            synopsis = escape(ep.get("synopsis", ""))
            has_pages = slug in slug_images
            if has_pages:
                ep_items += f"""
      <a href="read/{slug}.html" class="ep-item">
        <span class="ep-item__num">第 {ep_num} 話</span>
        <span class="ep-item__synopsis">{synopsis}</span>
      </a>"""
            else:
                ep_items += f"""
      <div class="ep-item disabled" style="opacity:0.4">
        <span class="ep-item__num">第 {ep_num} 話</span>
        <span class="ep-item__synopsis">（尚未生成）</span>
      </div>"""

        # 可閱讀的話（有生成頁面的）
        playable = [ep for ep in episodes if ep["slug"] in slug_images]

        inner = f"""
    {cover_html}
    <div class="card__body">
      <h2 class="card__title">{escape(title_zh)}</h2>
      <div class="card__meta">
        {status_badge}
        <span>{ep_count} 話</span>
      </div>"""

        if len(playable) == 1:
            # 只有一話 → 整張卡直接連進去看（點哪都行）
            only_slug = playable[0]["slug"]
            html += f"""
  <a href="read/{only_slug}.html" class="card card--link">{inner}
    </div>
  </a>
"""
        elif len(playable) >= 2:
            # 多話 → 整張卡點一下展開各話清單（點哪都行）
            html += f"""
  <article class="card" data-expandable>{inner}
      <div class="card__hint">點一下選擇話數 ▾</div>
    </div>
    <div class="episodes">
      <div class="ep-list">{ep_items}
      </div>
    </div>
  </article>
"""
        else:
            # 沒有可讀的話
            html += f"""
  <article class="card card--disabled">{inner}
    </div>
  </article>
"""

    html += "</section>\n"
    html += html_tail()
    return html


# ══════════════════════════════════════════════════
#  HTML 生成 — 閱讀頁
# ══════════════════════════════════════════════════

def generate_reader(series_data: dict, ep_data: dict,
                    image_paths: list[str],
                    prev_slug: str | None, next_slug: str | None) -> str:
    """生成單話閱讀頁 HTML。"""
    title_zh = series_data.get("title_zh", series_data["name"])
    ep_num = ep_data.get("ep", "?")
    page_title = f"{title_zh} — 第 {ep_num} 話"

    html = html_head(page_title, css_path="../style.css", js_path="../reader.js")

    # Nav
    html += f"""
<nav class="nav">
  <div class="nav__brand">
    <a href="../index.html" style="display:flex;align-items:center;gap:8px;color:inherit">
      {BOOK_ICON}<span>{escape(title_zh)}</span>
    </a>
    <span style="color:var(--text-muted);font-size:0.85rem">第 {ep_num} 話</span>
  </div>
  <div class="nav__links">
    <a href="../index.html" class="nav__link">目錄</a>
  </div>
</nav>
"""

    # Reader container
    html += '<main class="reader"><div class="reader__pages">\n'
    for i, img_path in enumerate(image_paths):
        rel_path = f"../{img_path}"
        html += f'  <div class="reader__page" data-src="{rel_path}" data-alt="第 {ep_num} 話 第 {i+1} 頁"><div class="skeleton"></div></div>\n'
    html += '</div></main>\n'

    # Bottom nav
    html += '<nav class="reader-nav">\n'
    if prev_slug:
        html += f'  <a href="{prev_slug}.html" class="reader-nav__btn" data-rel="prev">← 上一話</a>\n'
    else:
        html += '  <span class="reader-nav__btn disabled">← 上一話</span>\n'

    html += '  <a href="../index.html" class="reader-nav__btn">目錄</a>\n'

    if next_slug:
        html += f'  <a href="{next_slug}.html" class="reader-nav__btn reader-nav__btn--primary" data-rel="next">下一話 →</a>\n'
    else:
        html += '  <span class="reader-nav__btn disabled">下一話 →</span>\n'
    html += '</nav>\n'

    html += html_tail(js_path="../reader.js")
    return html


# ══════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MangaStudio 靜態漫畫網站生成器")
    parser.add_argument("--series", action="append", default=None,
                        help="指定要發布的連載名稱（可多次指定）")
    parser.add_argument("--quality", type=int, default=82,
                        help="WebP 壓縮品質 (1-100, 預設 82)")
    args = parser.parse_args()

    print("═══ MangaStudio Publish ═══")

    # 1. 載入連載資料
    series_list = load_series(args.series)
    if not series_list:
        print("[ERROR] 找不到任何連載。")
        print(f"  series 目錄: {SERIES_DIR}")
        if args.series:
            print(f"  指定篩選: {args.series}")
        sys.exit(1)

    names = [s.get("title_zh", s["name"]) for s in series_list]
    print(f"連載: {', '.join(names)}")

    # 2. 確保 docs 子目錄存在
    (DOCS_DIR / "read").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "images" / "covers").mkdir(parents=True, exist_ok=True)
    # .nojekyll：純靜態站，叫 GitHub Pages 跳過 Jekyll（更快更穩，避免 deploy 失敗）
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # 3. 圖片處理
    print("\n── 圖片處理 ──")
    slug_images = publish_images(series_list, args.quality)

    # 4. 生成閱讀頁
    print("\n── 生成閱讀頁 ──")
    for s in series_list:
        episodes = s.get("episodes", [])
        for idx, ep in enumerate(episodes):
            slug = ep["slug"]
            if slug not in slug_images:
                continue
            prev_slug = episodes[idx - 1]["slug"] if idx > 0 else None
            next_slug = episodes[idx + 1]["slug"] if idx < len(episodes) - 1 else None
            # 確認 prev/next 也有圖才連結
            if prev_slug and prev_slug not in slug_images:
                prev_slug = None
            if next_slug and next_slug not in slug_images:
                next_slug = None

            reader_html = generate_reader(s, ep, slug_images[slug], prev_slug, next_slug)
            out_path = DOCS_DIR / "read" / f"{slug}.html"
            out_path.write_text(reader_html, encoding="utf-8")
            print(f"  [OK] read/{slug}.html")

    # 5. 生成首頁
    print("\n── 生成首頁 ──")
    index_html = generate_index(series_list, slug_images)
    (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print("  [OK] index.html")

    # 6. 複製 CSS / JS（已存在就跳過修改時間比較）
    # style.css 和 reader.js 已經直接在 docs/ 裡，不需要複製

    total_pages = sum(len(v) for v in slug_images.values())
    total_eps = len(slug_images)
    print(f"\n═══ 完成：{total_eps} 話、{total_pages} 頁 ═══")
    print(f"輸出目錄: {DOCS_DIR}")
    print(f"\n預覽: python -m http.server 8080 -d \"{DOCS_DIR}\"")
    print(f"然後開啟: http://localhost:8080")


if __name__ == "__main__":
    main()