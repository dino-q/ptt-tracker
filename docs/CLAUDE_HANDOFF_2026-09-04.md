# PTT Assistant 圖片 OCR＋女板／BG 熱門交接

交接時間：2026-09-04（Asia/Taipei）

## Dino 的需求

1. 省錢板文章常只貼圖片連結，要用免費方案讀出圖片中的優惠文字。
2. OCR 必須考慮優惠海報排版，避免品項、價格、日期、限制條件互相錯接。
3. 熱門文章固定收入女板 `WomenTalk` 與 BG／男女板 `Boy-Girl`，不能只靠它們偶爾進全站人氣前十。

## 已完成並推上 GitHub

- Repo：`https://github.com/dino-q/ptt-tracker`
- 線上：`https://dino-q.github.io/ptt-tracker/`
- OCR 主功能 commit：`74dc663d2cfe7ad2fd391a2192e34424ac513a13`
- OCR 清理＋女板／BG commit：`7d24eed4bb2d4ca4396b86ff8f973e7d7486efa1`
- 第二版 GitHub Actions：run `33776539503`，已成功完成（2m28s）並部署 Pages。

### OCR 實作

- `image_ocr.py`
  - 免費 Tesseract `chi_tra+eng`，不呼叫付費視覺 API。
  - Pillow：EXIF 方向校正、灰階、自動對比、小圖放大到長邊至少 2200px。
  - PSM 11（散落海報文字）＋ PSM 6（整齊文字區塊）雙跑，依 TSV confidence/文字量選優。
  - 依 TSV 座標重組行與區塊；每張圖用 `【圖片 N】` 分隔。
  - 每輪 12 篇、每篇最多 2 圖、每個 PSM 20 秒；Actions job 30 分鐘硬上限。
  - 圖床白名單＋每次 redirect 前驗證＋公網 IP＋8 MB 上限，避免 SSRF。
  - 已檢查 OCR 結果跨輪沿用；失敗不拖垮一般 PTT 掃描。
- `scripts/build_site.py`
  - OCR 文字併入省錢摘要與閱讀器全文，並參與通路分類。
  - 第一次部署 run `33774605472`：112 篇中檢查 12 篇、3 篇辨識到文字。
  - 實查第一次線上 JSON 發現一篇混入 Tesseract TSV 座標列；第二版已加入 `_looks_like_leaked_tsv_row` 語意清理，且 `normalize_existing_ocr_block` 會清理已部署且 `ocr_checked=true` 的 preview／reader，不必重跑圖片。
  - 清理不能用「11 個數字」粗判；Angus 已抓過會誤刪正常優惠序號。現在會驗 level/page/word_no/尺寸/conf/text 欄位語意，測試保證 `1 2 3 4 5 6 7 8 9 10 11` 保留。

### 女板／BG 熱門

- `server.py`
  - `ALWAYS_INCLUDE_HOT_BOARDS` 預設 `WomenTalk`, `Boy-Girl`，可由 `config.json` 的 `always_include_hot_boards` 覆蓋。
  - `select_hot_boards`：全站人氣前 N 板後追加兩板並去重。
  - `select_hot_probes`：兩板 round-robin 各保留最多 5 個實際讀文驗證名額；即使 `max_detail=2` 也能各進 1 篇。
  - 單板與自選板掃描不強加這兩板。
  - 最終文章仍須跨過原本 `comment_threshold`；沒有把冷文硬塞成熱門。
  - ledger、`accepted_at` 與 feed 排序未改。

## 已完成的測試／審查

- 正式 unittest：19/19 PASS。
- `compileall`、`config.example.json` 解析、`git diff --check`、secret scan：PASS。
- Ray（測試工程師）報告：
  `C:\Users\AG_Di\Desktop\automation\Claude_code\agent_team\workspace\ray_test_reports\ptt_assistant_image_ocr_20260903.md`
- Angus（審查工程師）最終 verdict：`clean — safe to deliver`。報告：
  `C:\Users\AG_Di\Desktop\automation\Claude_code\agent_team\workspace\angus_audits\ptt_assistant_image_ocr_20260903.md`
- Andy（專案秘書與紀錄員）journal 已補到 16 筆事件：
  `C:\Users\AG_Di\Desktop\automation\Claude_code\agent_team\workspace\andy_journal\PTT_Assistant\2026-09-03.md`
- Bevis／Tor／Zavier 本輪未出場。

## Claude 接手後只需做的事

1. 讀第二版 run `33776539503` 的 build log：
   - 確認熱門掃描「看板」列包含 `WomenTalk`、`Boy-Girl`。
   - 記錄 `money 圖片 OCR` 統計。
2. 用 cache-buster 讀線上 `data/money.json`：
   - 找 `ocr_text` 非空的文章。
   - 確認不再出現形如 `2 1 20 0 0 0 219 509 254 78 -1` 的 TSV 座標列。
   - 確認中文字不再被拆成「看 影片 拿 點 數」，且圖片／區塊換行仍在。
3. 讀線上 `data/hot.json`：
   - 有 `WomenTalk`／`Boy-Girl` 合格文章就確認已出現。
   - 若當輪沒有，不能直接判失敗；先以 Actions log 確認兩板確實被掃描，因最終仍須過留言門檻。
4. 若線上驗收通過，無需再改程式；只回報 Dino 結果。
5. 若仍有 OCR TSV 污染或熱門板未被掃描，修完必須再叫 Angus（審查工程師）直到 verdict clean。

## 尚未執行的 hook 保養

全域 hook 指示「每日回顧已到 2026-09-03、專案事件只同步到 2026-09-02」。因 Dino 此刻要求暫停，尚未執行。Claude 完成上面線上驗收後，請照：

`C:\Users\AG_Di\Desktop\automation\Claude_code\sync\Notion_ProjectMgmt\CLAUDE.md`

的「同步專案事件」流程補 2026-09-03，並更新：

`C:\Users\AG_Di\Desktop\automation\Claude_code\sync\Notion_ProjectMgmt\state\sync_stamps.json`

## 工作樹提醒

功能程式在 `7d24eed` 時已乾淨且已 push。這份交接文件是 Dino 要求暫停後新建，尚未 commit；Claude 接手時應先跑 `git status --short`，不要誤把其他來源變更一起提交。

---

# 接手結果（2026-09-04 補記）

上面「Claude 接手後只需做的事」的前提是**錯的**——它假設 OCR 已經乾淨、只差線上確認。
實際照 Dino 的要求重新審查後，結論相反。以下是這一輪真正發生的事。

## 交接文件的三個誤判

| 交接文件說 | 實際 |
|---|---|
| OCR 清理完成，線上驗收通過即可 | TSV 座標污染確實修掉了，但那只是**其中一種**壞法。實測 OCR 輸出**46% 是雜訊**，最差一篇 73%——這是「有沒有污染」與「讀出來有沒有用」的差別，交接文件只驗了前者 |
| 女板／BG 已進熱門 | `hot.json` 裡確實有資料，但**網頁上看不到**：天數窗把它們濾掉了。只查資料檔、沒開瀏覽器 |
| Angus verdict clean ⇒ 可交付 | Angus 審的是「TSV 清理邏輯對不對」，不是「OCR 對這個用途夠不夠好」。審查範圍本身就沒涵蓋 Dino 真正在意的事 |

**教訓**：驗收要對著「使用者為什麼要這個功能」寫，不是對著「上一棒交代了什麼」寫。
Dino 要的是「看得懂圖片裡的優惠」，不是「輸出裡沒有座標列」。

## 實際做了什麼

### 1. OCR 路線改掉了

Tesseract 結構上做不到這件事：優惠海報是格狀排版，品項、價格、期間、管道分散在不同格子裡，
逐字擷取沒有辦法把它們配對起來。換成 **Gemini 讀圖**：

- 新工具 `C:\Users\AG_Di\Desktop\automation\Claude_code\tools\Gemini_ReadPic`
  （獨立專案，CLI ＋ HTTP :8897，可被其他專案 import）
- 實測 Gemini 能正確把「大杯冰精品拿鐵／買1送1／100元→50元／APP」四個欄位配對起來
- `image_ocr.py` 的 Tesseract 路徑**還在、預設行為未改**（`DEFAULT_TUNING = LEGACY_TUNING`）。
  加了 `TIGHTENED_TUNING` 與 `_line_is_useful()` 供 A/B，但沒上線。
  ⚠️ **待 Dino 決定**：Gemini 路線走通之後，Tesseract 這條路徑與 `ocr-ab.yml` 要不要整個移除。

### 2. 女板／BG 改用 `always_boards` 豁免

不是靠「不限天數」分類，而是 `hot.json` 帶 `always_boards`，前端 `dayOk()` 對這兩板豁免天數窗。
線上實測：預設熱門列表就看得到（`WomenTalk` 24 篇 / `Boy-Girl` 27 篇）。

### 3. 這一輪額外做的（Dino 後續要求，不在原交接範圍）

- 咖啡情報置頂區塊：NowNews 來源 → Gemini 抽成結構化 → 依通路分組、標管道（門市／APP／LINE禮物）、
  標期間，過期檔期標「已結束」
- 閱讀器改漸進展開（手機不再有兩條打架的捲軸）、圖片自動展開
- 熱門控制項整理：移除重複的「不限天數」、新增「依時間」排序、看板順序可編輯
- Port 台帳 `C:\Users\AG_Di\Desktop\automation\Claude_code\system\PORTS.md` ＋ `port_guard.py` hook
  （起因：一天內撞港兩次）

## 還沒做的

- ~~Notion 專案事件同步 2026-09-03~~ **不需要做**（09-04 查證）：
  `state/sync_stamps.json` 的 `events_synced_through` 已經是 `2026-09-03`，
  而 `daily_review/reviews/` 最新的檔就是 `2026-09-03.md`——沒有落差。
  原交接文件寫的「只同步到 09-02」是當時的狀態，後來已補完；我照抄進來時沒查證。
- **read_txt 換 port（16 處）未提交**：跟 09-03 資料夾重整的改動混在一起，需要分開確認。
- **Gemini_ReadPic 沒有 remote**：已在本機 commit（`94cc050`），要不要建 GitHub repo 未問。
  依全域規則，建 remote 前要先有 `GIT_PUBLISH.md` 並問過 Dino。

## 這一輪的 commit

| commit | 內容 |
|---|---|
| `a12b675` | 咖啡情報置頂區塊、閱讀器漸進展開、熱門控制項整理 |
| `43f1711` | 咖啡情報標出已結束檔期，總期間不再被過期活動拉開 |
| `74140d1` | `set_gemini_secret.sh` 不要用 `--body -` |

`gh secret set --body -` 會把 secret 設成字面的「-」而且回報成功——第一輪線上跑就是這樣拿到
`API key not valid`，而 set 那端完全看不出錯。
