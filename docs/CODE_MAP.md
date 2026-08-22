# CODE_MAP — PTT_Assistant 可重用函式/元件清單

> 寫任何新程式前先查這份檔。預設「調用」既有實作，不要複製一份出來改。
> 新寫的可重用函式要當下登錄進來，並在回報/commit 標 ♻️ 沿用 或 🆕 新寫。

## ptt_tool.py（爬蟲核心＋CLI，2026-08 原始版）

| 名稱 | 用途 | 備註 |
|---|---|---|
| `PTTClient` | PTT 網頁版 HTTP client（over18 cookie、UA、重試、禮貌延遲） | 所有 PTT 抓取一律經過它，勿另開 requests session |
| `PTTClient.search(board, query, max_pages, max_posts)` | 板內搜尋（支援 `author:xxx`），回 `list[SearchItem]` | 結果新→舊 |
| `PTTClient.latest_board_posts(board, pages, max_posts)` | 掃板面最新頁 | 標題用詞不在關鍵字內時的補網 |
| `PTTClient.article(url)` | 抓單篇文章，去推文/標頭/簽名檔，回 `Article` | |
| `clean_ptt_body(text)` | 清洗 PTT 內文（發信站、簽名檔、空行正規化） | |
| `parse_board(text)` / `parse_author(text)` | 從白話文抽板名/作者（規則式） | server.py 的 `parse_request` 有更完整版 |
| `safe_filename(s)` | 檔名消毒 | |
| `title_sort_key` / `strip_ptt_category` | 標題排序（集數）/去 `[分類]` | |
| `export_author_creations(...)` | 作者 [創作] 合併匯出 TXT | |
| `this_weekend_window(now)` | 算本週五 00:00 ～ 週日 23:59 | |
| `looks_like_weekend_deal(title, body)` | 超商×飲品雙關鍵字判定 | 通用版見 server.py `match_groups` |
| `find_weekend_deals(client, out_dir, pages)` | 省錢板週末優惠整理成 TXT | 網頁版走 server.py 的 task 引擎，不再叫這支 |
| `search_and_export_index(...)` | 一般搜尋 → 索引 TXT | |
| `run_natural_language(text, out_dir)` | CLI 一句話模式入口 | |
| 常數 `BOARD_ALIASES` / `CONVENIENCE_KEYWORDS` / `DRINK_KEYWORDS` | 板名別名、超商/飲品關鍵字 | server.py 沿用並可被 config.json 覆蓋 |

## server.py（🆕 2026-08-22 通用掃描引擎＋本機網頁伺服器）

| 名稱 | 用途 | 備註 |
|---|---|---|
| `load_config()` / `load_tracks()` / `save_tracks()` | 讀 config.json（無則 fallback example）、追蹤項存取 | tracks.json 首次啟動自動建立內建追蹤項 |
| `parse_list_date(date_text, today)` | 板面列表 `M/DD` 推回完整日期（跨年往回推） | |
| `match_groups(text, groups)` | 通用多組關鍵字判定：每組至少命中一詞才算過，回命中詞 | 取代寫死的 `looks_like_weekend_deal` |
| `parse_request(text)` | 白話 → 結構化 task（板名/關鍵字/天數/超商飲品意圖） | UI 會顯示解析結果讓使用者修正後才執行 |
| `run_task(task, job)` | 通用掃描：搜尋＋最新頁 → 去重 → 日期過濾 → 關鍵字組判定（必要時讀內文）→ 結果 | 所有追蹤項共用這一支 |
| `export_results_txt(name, results)` | 掃描結果 → output/*.txt | |
| Job 機制（`JOBS` dict + thread） | 背景執行＋進度輪詢＋取消 | `/api/run` → `/api/jobs/<id>` |

## web/index.html（🆕 UI 單檔，無框架）

- 追蹤項卡片、白話輸入＋解析預覽表單、進度區、結果卡片（展開內文摘要）、匯出 TXT、存追蹤項。
- 全部 CSS/JS inline，自足單檔；無 sticky/懸浮蓋內容元件（Dino 規範）。

## HTTP API（server.py 提供，port 8877）

| Method Path | 用途 |
|---|---|
| `GET /` | 網頁 UI |
| `GET /api/meta` | 板名別名、預設關鍵字組、追蹤項清單 |
| `POST /api/parse` | `{text}` → 結構化 task 提案 |
| `POST /api/run` | `{task}` → `{job_id}`（背景執行） |
| `GET /api/jobs/<id>` | 進度＋結果輪詢 |
| `POST /api/jobs/<id>/cancel` | 取消掃描 |
| `GET /api/article?url=` | 單篇內文摘要（限 ptt.cc） |
| `POST /api/export` | 結果匯出 TXT，回檔案路徑 |
| `POST /api/tracks` | 新增/更新/刪除追蹤項 |
