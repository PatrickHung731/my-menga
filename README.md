# MangaStudio — 你講故事，AI 畫連載漫畫

日系少年漫風格，RTX 4060 本機生圖（ComfyUI），編劇用 Gemini 免費額度或本機 Ollama，
**全程零 Claude token**。連載模式會自動延續：角色長相、畫風、每話頁數、前情提要。

---

## ★ 日常操作：雙擊 `MangaStudio.bat`

所有事情都在這個選單裡，選數字、把 txt 拖進視窗就好：

```
 [1] 出下一話（拖入故事txt）      [5] 先審分鏡（不生圖）
 [2] 出最終話・完結本作           [6] 開新連載 / 切換連載
 [3] 重抽某一格（可先改prompt）   [7] 單篇短篇
 [4] 改對白/搬氣泡 → 重拼頁      [8] 連載狀態/各話提要
 [9] 重新生成封面
```

封面會在**出第一話後自動生成**（主角彩色 key visual + 標題字）。不滿意就按 `9` 換一張（可選主角、可選黑白）。

- **第一次**：按 `6` → `n` 開新連載（會問代號/中文名/畫風/預設頁數/內容分級）
  - 「預設每話幾頁」只是**預設值**；每次出稿時還會再問一次，可以每話不一樣
  - 分級 `全年齡`＝乾淨少年漫；`R15`＝血腥戰鬥/黑暗劇情/成年角色輕度性感（青年誌尺度，**無裸露、未成年角色一律全年齡**）
  - 對白語言：預設「跟著故事自動判定」（英文腳本→英文對白+橫排氣泡；中文→中文+直排氣泡；日文→日文）。也可指定 z中 / e英 / j日
- **平常**：寫好故事 txt → 按 `1` → 拖入 txt → **輸入這一話幾頁**（直接 Enter 用預設）→ 等它畫完自動開資料夾
  - 出稿完會**自動發布到線上網站**：https://patrickhung731.github.io/my-menga/ （約 1~2 分鐘後更新）
  - 改完對白/封面/重抽某格後，按 `[p]` 手動發布，線上才會跟著更新
- **完結**：最後一話按 `2` —— 編劇會做完結收尾（回收主線、不留鉤子），最後一頁自動蓋「完」章，連載標記完結防止誤加話
- 修圖/改對白：按 `3` / `4`，它會自己開分鏡檔給你改、改完自動重跑

角色連戲的唯一要求：**故事裡的角色中文名每話寫法固定**（第一話叫雷恩，以後都寫雷恩）。

## 進階：命令列（跟選單等價，給想自動化的你）

```
manga.bat stories\ep1.txt --series raiden --title-zh 雷光 --style yuyu_hakusho --pages 8   ← 開連載+第一話
manga.bat stories\ep2.txt                    ← 下一話（自動接）
manga.bat stories\ep9.txt --final            ← 最終話
manga.bat stories\en.txt --oneshot --lang en ← 指定英文對白（不加=依故事自動判定）
redo.bat raiden_ep02 2:3                     ← 重抽第2頁第3格
compose.bat raiden_ep02                      ← 改完對白重拼頁
```

## 三、修改流程（改哪裡跑哪個）

| 想改什麼 | 怎麼做 | 花費時間 |
|---|---|---|
| **對白/旁白文字** | 開 `storyboards\raiden_ep01.json` 改 `text`，存檔後跑 `compose.bat raiden_ep01` | 幾秒 |
| **某一格的畫面** | 同上檔案改該格 `prompt`（英文tags），跑 `redo.bat raiden_ep01 1:3`（=第1頁第3格） | ~30秒 |
| **同格重抽**（prompt 不變換運氣） | 直接 `redo.bat raiden_ep01 1:3` | ~30秒 |
| **整話重新分鏡重畫** | `manga.bat stories\ep1.txt --out raiden_ep01 --redo` | 幾分鐘 |
| **先看分鏡再決定要不要畫** | `manga.bat stories\ep3.txt --storyboard-only`，審完 JSON 再正式跑 | 幾秒 |

JSON 裡一格長這樣（要改就改這幾個欄位）：
```jsonc
{ "id": 3,
  "characters": ["ryne"],
  "prompt": "solo, 1boy, punching, close-up, speed lines",   // ← 畫面
  "seed": 12345,                                             // ← 加這行可鎖住構圖微調
  "dialogues": [ {"text": "就是現在！", "pos": "top-right", "type": "shout"} ] }  // ← 對白
```

## 四、角色管理

- 角色住在 `characters\<id>\`：`ref.png`（鎖臉參考）、`tags.txt`（外觀）、`name_zh.txt`（中文名）
- **嫌某角色長相不行**：`manga.bat` 之前先跑
  `scripts\new_character.py --name ryne --tags "..." --bw --seed 換數字`（重生 ref.png，之後每話都用新臉）
- 連載名單在 `series\<連載名>.json`（角色表、頁數、下一話編號、前情提要都在裡面，可手動編輯）

## 五、其他

- **單篇短篇**：`manga.bat stories\x.txt --oneshot --max-pages 4`（不掛連載）
- **全離線編劇**：加 `--engine ollama`（qwen3:8b，品質較弱，斷網備用）
- **彩頁**：開連載時加 `--color`（整部固定）
- **換連載**：`--series 另一部`（之後拖拉預設就跟著換）

## 畫風表（--style，一部作品選一次）

`dragon_ball` 七龍珠 | `one_piece` 海賊王 | `yuyu_hakusho` 幽遊白書 | `slam_dunk` 灌籃高手 | `naruto` 火影 | `video_girl_ai` 電影少女 | `kungfu_boy` 鐵拳對鋼拳 | `shonen_90s` 通用九零少年漫

## 疑難排解

- **Gemini 503**：尖峰擁擠，腳本會自動重試 3 次；還是失敗就等幾分鐘再跑，或加 `--engine ollama`
- **OOM / 很慢**：關掉其他吃 GPU 的程式（Applio、Deep-Live-Cam、遊戲）
- **雙人同格臉互染**：結構性限制。特寫盡量一格一人；壞格用 `redo.bat` 重抽最快
- 第一次跑會自己開 ComfyUI（黑窗），跑完留著沒關係，下次更快
