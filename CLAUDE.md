# MangaStudio — AI 連載漫畫自動化管線

**主要模式是零 token 全本機的「連載」**：使用者把故事存 `stories\*.txt`，拖到 `manga.bat`
（= scripts\story2manga.py：本機 LLM 編劇分鏡 → 自動建新角色 → 生圖 → 拼頁）。
編劇腦預設 Gemini API（key 讀 env 或 D:\原F\QuantProject\.env），`--engine ollama` 全離線（qwen3:8b 已 pull）。
編劇規則：**忠實改編使用者劇情，LLM 不自行編故事**（write_storyboard.py 規則 6）。

## 連載系統（series/）

- `series\<名>.json`：title_zh / style / color / pages_per_episode / next_ep / characters(id→中文名) / episodes(含 synopsis)。`series\default.txt` 記目前連載，讓拖拉 txt 不用帶參數就自動接下一話。
- 開新連載：`manga.bat stories\ep1.txt --series 名 --title-zh 中文 --style X --pages N`；日常出話：`manga.bat stories\epN.txt`（零參數）。
- 連戲機制：cast 連中文名餵給編劇 LLM（規則 7 禁止重建已有角色，**用中文名比對**）；story2manga.remap_characters() 再兜底——LLM 違規重建時自動併回現有 id、新角色 id 撞到別部作品時改名 `<連載>_<id>`。前情提要取最近 3 話 synopsis。
- 跨話臉孔一致 = characters\<id>\ref.png（IPAdapter）跨話共用；角色中文名在 name_zh.txt。
- `--storyboard-only` 只出分鏡不生圖（先審再畫）；`--oneshot` 單篇不掛連載。

## 一鍵檔（給使用者的，純 ASCII .bat）

**`MangaStudio.bat`＝互動工作台（scripts\studio.py），使用者的主要入口**：選單含出下一話/最終話/重抽格/改對白/審分鏡/開切連載/單篇/狀態。
`manga.bat <txt> [參數]`＝story2manga；`redo.bat <slug> 頁:格`＝重抽單格+重拼；`compose.bat <slug>`＝改完對白重拼頁。

## 內容分級（rating）

series/storyboard 的 `rating`: `safe`(預設) / `r15`。r15=血腥戰鬥+黑暗劇情+成年角色輕度性感（青年誌尺度）。
**硬線（寫死在 R15_RULE 與 RATING_NEG，不要放寬）**：全作不出現裸露/成人內容；未成年角色一律全年齡描寫。
技術面：write_storyboard.R15_RULE 進編劇 prompt；sdxl_graph.RATING_NEG 進負面詞（safe 連 blood/gore 都擋）；
Gemini 呼叫帶官方 safetySettings=BLOCK_ONLY_HIGH（否則 R15 規則文字本身會被過濾器整包拒答，症狀=回應無 candidates）。

## 對白語言（lang）

series/storyboard 的 `lang`: `auto`(預設,依故事偵測) / `zh` / `en` / `ja`。write_storyboard.detect_lang() 偵測（假名→ja、有漢字無假名→zh、其餘→en），lang_rule() 塞「最高優先」強制指令進編劇 prompt（否則 LLM 會無視埋在規則裡的語言要求）。**渲染端 compose_pages.py 會自動判斷**：is_latin() 為真→橫排氣泡(wrap_words 單字換行)，否則直排(中日文)。英文若還走直排會變字母直疊——這是當初「英文腳本卻中文對白」的兩個病根之一（另一個是編劇語言指令太弱）。

## 自動發布到 GitHub

D:\MangaStudio 是 git repo，remote origin = https://github.com/PatrickHung731/my-menga（分支 main）。GitHub Pages 服務 main /docs → 線上站 **https://patrickhung731.github.io/my-menga/**。憑證：PAT 已存進 Windows Credential Manager（GCM，加密），未來 push 免登入；**別把 token 寫進任何檔案或記憶**。
- `scripts\deploy.py`：publish.py 生站 → git add -A / commit / push origin HEAD:main（`--no-push` 只本機、`--series X` 限定、`--message`）。
- story2manga 出稿後**自動 deploy**（連載模式 + 是 git repo；`--no-deploy` 可關）。工作台選項 **[p]** 手動發布（改完對白/封面/重抽後用）。
- Pages build 需 1~2 分鐘才反映；token 失效時 deploy 會「本機已 commit、push 失敗」，補 `git push` 即可。

## 封面 / 發布

`scripts\make_cover.py`（`--series X` 或 `--all [--redo]`；`--char <id>` 選主角、`--bw` 黑白）→ 主角彩色 key visual（IPAdapter 鎖臉）+ Pillow 疊標題字 → `covers\<name>.png`（3:4, 900x1200）。story2manga 出第一話後**自動生成**（沒有才生）；工作台選項 9 可重生。`scripts\publish.py` 產靜態站到 `docs\`（PNG→WebP、index + read/<slug>.html、共用 docs\reader.js/style.css）；**封面優先用 covers\<name>.png**，沒有才退回第一話第一頁。改封面/出新話後要重跑 publish.py 才更新網站。

## 改畫風 / 改角色（做完發現不喜歡）

- **改整部畫風**：`scripts\restyle.py --series X --style NEW [--color|--bw] [--no-refs]`（=工作台 [s]）。改 series+所有分鏡的 style/color → 用**同一顆 seed** 重繪角色參考(保臉) → 重畫所有話全部分格 → 重生封面。故事/分鏡/對白不動，只換「畫」。很重（每格 20~40s）。
- **改單一角色**：`scripts\change_character.py --series X --char ID [--tags "新外觀"] [--gender] [--seed] [--bw]`（=工作台 [c]）。重繪該角色設定圖（給 tags=換外觀設計、不給=只換臉重抽 seed）→ 掃所有分鏡找出「characters 含該 id」的分格**只重畫那些**（其他格不動）→ 重拼受影響的話 →(若是封面主角)重生封面。
- 兩者做完都會問要不要順便 deploy（線上更新）。

## 最終話/完結

`story2manga --final`（=工作台選項 2）：編劇 prompt 加完結收尾規則（不留下回鉤子）、storyboard 標 `"final": true`、compose 在最後一頁左下蓋「完」章、series json 標 `completed: true` 並解除 default.txt；之後對已完結連載跑會被擋（手動改 json 可解）。

Claude Code 的角色是**精修**：使用者嫌某格不好時，直接改 storyboard JSON 的該格 prompt/對白，
用 redo.bat（或 generate_panels --only 頁:格 --redo + compose）。不要沒事重跑整個 story2manga（會重新編劇+重畫，浪費）。

## 硬體與底座（不要重裝任何東西）

- GPU: RTX 4060 8GB。生圖引擎 = 現有的 `D:\LocalAI\ComfyUI`（venv 已有 torch cu126）。
- 跑腳本一律用 **ComfyUI 的 venv python**：`D:\LocalAI\ComfyUI\venv\Scripts\python.exe`（有 requests + Pillow，本專案不建自己的 venv、不裝本機 torch）。
- ComfyUI 伺服器不用手動開，`comfy_client.ensure_server()` 會自動啟動（port 8188）。
- 8GB 注意：跑圖時不要同時跑 Applio / Deep-Live-Cam / LiveTranslator 等其他 GPU 程式。OOM 的話先關其他程式，再不行把該格 prompt 裡的解析度降級（改 storyboard `page_size` 或減少同格角色數）。

## 標準工作流程（使用者給故事之後）

1. **寫分鏡**：把故事切成頁與格，寫 `storyboards\<slug>.json`（schema 見下）。對白用繁體中文、精簡口語（每句 ≤ 20 字為佳，氣泡直排）。
2. **生圖**：`& D:\LocalAI\ComfyUI\venv\Scripts\python.exe D:\MangaStudio\scripts\generate_panels.py D:\MangaStudio\storyboards\<slug>.json`
3. **拼頁**：`... scripts\compose_pages.py 同一個json`（或一步到位 `scripts\make_manga.py`）。
4. **給使用者看** `output\<slug>\pages\page_NN.png`，逐格聽修改意見。
5. **重生單格**：`generate_panels.py <json> --only 頁:格 --redo`，然後重跑 compose。想固定某格構圖只換細節 → 把 gen_log.json 裡那格的 seed 填回 storyboard 的 `seed` 欄位再改 prompt。

新連載開角色（一次性）：
```
& D:\LocalAI\ComfyUI\venv\Scripts\python.exe D:\MangaStudio\scripts\new_character.py --name <英文名> --tags "<外觀tags>" --gender 1boy --style <風格> --bw
```
生出 `characters\<名>\ref.png`（IP-Adapter 鎖臉用）+ `tags.txt`。不滿意換 `--seed` 重跑。**黑白漫畫記得 --bw**（彩色參考圖會把灰階畫面帶彩）。

## Storyboard JSON schema

```jsonc
{
  "title": "story_slug",          // 英文，當輸出資料夾名
  "style": "dragon_ball",         // 見下方風格表
  "style_tags": "",               // 額外自由風格 tags（可省略）
  "color": false,                 // false=黑白+網點（連載漫畫預設），true=彩頁
  "page_size": [1240, 1754],      // 可省略
  "steps": 26, "cfg": 5.5,        // 可省略
  "pages": [{
    "page": 1,
    "layout": [[1],[2,3],[4]],    // 每列的格子id；⚠ 閱讀順序右→左，列內第一個id排最右
    "row_weights": [1.1,1,0.9],   // 可省略
    "panels": [{
      "id": 1,
      "characters": ["hero"],     // characters/ 下的資料夾名；tags 自動前置、ref.png 自動掛 IP-Adapter
      "prompt": "...",            // 英文 Danbooru tags：動作+表情+鏡頭+背景+效果
      "camera": "close-up",       // 可省略
      "pose": "punch.png",        // 可省略；poses/ 下的動作參考圖（照片會自動抽骨架）
      "pose_type": "photo",       // "skeleton"=已是骨架圖
      "pose_strength": 0.85,      // 可省略
      "seed": 12345,              // 可省略；固定構圖重生用
      "ref_weight": 0.75,         // IP-Adapter 權重，可省略
      "dialogues": [
        {"speaker":"hero","text":"就是現在！","pos":"top-right","type":"shout"},
        {"type":"narration","text":"三年後——","pos":"top-left"},
        {"type":"sfx","text":"轟","pos":"center"}
      ]
    }]
  }]
}
```

- dialogue `type`: `speech`(預設，直排橢圓氣泡) / `shout`(大字雙框) / `narration`(橫排方框旁白) / `sfx`(擬聲大字)。
- `pos`: `top-left` `top-right` `bottom-left` `bottom-right` `top` `bottom` `left` `right` `center`。同格多氣泡要錯開位置；右邊的氣泡先讀。
- sfx 常用字：轟、砰、咚、唰、喀、嘎、咻、磅、嘶、吼。

## Prompt 規則（給每格 prompt 欄位）

- 英文 Danbooru tags。品質詞（masterpiece 等）、風格詞、黑白詞**腳本會自動加，不要重複寫**。
- 格 prompt 只寫：人數詞(1boy/2boys/1girl...) + 動作 + 表情 + 鏡頭角度 + 背景 + 漫畫效果。
- 角色外觀 tags 住在 `characters/<名>/tags.txt`（不含人數詞），會自動前置 —— **格 prompt 不要重複角色外觀**，雙人格才不會互相污染。
- 好用的漫畫效果 tags：`speed lines, motion blur, impact, emphasis lines, dutch angle, from below, from above, close-up, wide shot, dramatic shadow, chiaroscuro, action lines, debris`。
- 多角色同格：IP-Adapter 多臉會互相污染（權重會自動降到 0.55）。原則：**關鍵特寫每格一人**；群像格靠外觀 tags 區分，必要時 `"face_only": false` 換整體風格參考。

## 風格表（style 欄位）

| key | 對應 | 內容 |
|---|---|---|
| `dragon_ball` | 七龍珠 | toriyama akira (style) + 80s |
| `one_piece` | 海賊王 | oda eiichirou (style) |
| `yuyu_hakusho` | 幽遊白書 | togashi yoshihiro (style) + 90s |
| `slam_dunk` | 灌籃高手 | inoue takehiko (style) + 90s |
| `naruto` | 火影忍者 | kishimoto masashi (style) |
| `video_girl_ai` | 電影少女 | katsura masakazu (style) + 90s |
| `kungfu_boy` | 鐵拳對鋼拳 | 80s retro + martial arts |
| `shonen_90s` | 通用九零少年漫 | 1990s (style), retro artstyle |

畫師 tag 在 Animagine XL 4.0 的辨識度不一，效果不夠像就在 `style_tags` 疊加補強（如 `sketch, ink, hatching`），或之後去 Civitai 抓對應畫風 LoRA 放 `D:\LocalAI\ComfyUI\models\loras`（graph 還沒接 LoRA 節點，需要時在 sdxl_graph.py 的 KSampler 前加 LoraLoader）。

## 模型與檔案位置

| 用途 | 檔案 | 位置 |
|---|---|---|
| 主模型 | animagine-xl-4.0.safetensors (~6.9G) | ComfyUI models\checkpoints |
| 鎖臉 | ip-adapter-plus-face_sdxl_vit-h / plus_sdxl_vit-h | models\ipadapter |
| 視覺編碼 | CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors | models\clip_vision |
| 姿勢 | controlnet-union-sdxl-promax.safetensors | models\controlnet |
| 節點 | ComfyUI_IPAdapter_plus, comfyui_controlnet_aux | custom_nodes |

下載腳本：`setup\download_models.ps1`（curl 可續傳，log 在 setup\download.log）。

## 地雷（本機慣例）

- 寫 .bat 必須純 ASCII + CRLF（cp950 地雷）；.ps1 中文要 UTF-8 BOM。本專案腳本都是 .py，用 UTF-8 沒事。
- 路徑保持純英文（cv2/模型的中文路徑地雷）；storyboard 的 title 用英文。
- 生圖類重活全在本機 ComfyUI（這是 CAPCUT「只派發 Kaggle」原則的既有例外：D:\LocalAI 堆疊）。
