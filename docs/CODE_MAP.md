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
| `PTTClient.hotboards(top)` | 即時熱門看板排行（人氣數） | 🆕 2026-08-22 |
| `PTTClient.article(url, include_comments)` | include_comments=True 會在內文後附推文留言區塊；回傳的 Article.push_summary 一律帶推/噓/→/total/users 統計 | 預設 False 不變 |
| `SearchItem.push` | 板面列表推文數欄位（爆/99/X1） | 🆕 2026-08-22，search/latest 都會帶 |
| `parse_board(text)` / `parse_author(text)` | 從白話文抽板名/作者（規則式） | server.py 的 `parse_request` 有更完整版 |
| `safe_filename(s)` | 檔名消毒 | |
| `title_sort_key` / `strip_ptt_category` | 標題排序（集數）/去 `[分類]` | 2026-08-22 修：系列名正規化，空格/無編號不再亂序 |
| `export_author_creations(..., tag, on_progress, collect)` | 作者文章合併匯出 TXT | tag 可自訂篩選（空=全部）；on_progress/collect 供網頁進度與結構化結果 |
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
| `parse_request(text)` | 白話 → 結構化 task（意圖 scan/author_export/hot＋板名/關鍵字/天數） | UI 會顯示解析結果讓使用者修正後才執行 |
| `run_task(task, job)` | scan 意圖：搜尋＋最新頁 → 去重 → 日期過濾 → 關鍵字組判定（必要時讀內文）→ 結果 | |
| `run_author_export(task, job)` | author_export 意圖：♻️ 調用 export_author_creations＋進度/取消 | 🆕 2026-08-22 |
| `run_hot(task, job)` | hot 意圖 v4：moptt 式收錄制（板級留言門檻→accepted_at→feed 依收錄時間排、舊文回鍋、收錄後凍結、保留10天）；設計依據見 docs/moptt_algorithm.md | 2026-08-23 v4 |
| `hot_cats(board)` / `HOT_BOARD_CATEGORY` | 熱門文分類＝看板主題（八卦時事/棒球…），未知板用板名；config `hot_board_categories` 可覆蓋 | 🆕 與省錢的通路標籤是兩套 |
| `select_hot_boards(...)` / `select_hot_probes(...)` / `ALWAYS_INCLUDE_HOT_BOARDS` | 全站熱門固定加入女板與 BG 板，去重後在全站驗證池各保留名額 | 預設 WomenTalk/Boy-Girl；config 可覆蓋 |
| `HOT_FEED_DAYS` / `HOT_FEED_LIMIT` / `HOT_PREVIEW_LIMIT` | 🆕 2026-09-04 feed 保留期（30 天）、顯示上限（1200 篇）、帶摘要的前 N 篇（120） | 由 10 天／400 篇放大，讓低流量板的舊文留得住。**實際涵蓋天數由先觸底的那個決定（目前是篇數）**；config 可用 `hot_feed_days`／`hot_feed_limit` 覆蓋 |
| `_parse_article_dt` / `_thread_key` | 文章時間解析／討論串聚合鍵 | 🆕 |
| `run_download(task, job)` | download 意圖：指定 urls 逐篇抓全文（可含留言）合併 TXT，job.file 給下載端點 | 🆕 2026-08-22 |
| `run_job(task, job)` | 意圖分流入口（start_job 用），完成後寫追蹤項快取 | 🆕 |
| `classify(title)` / `CATEGORY_RULES` | 標題分類標籤（四大超商/超市量販/網購電商/餐飲美食/支付回饋，可多類） | config.json `categories` 可覆蓋 |
| `push_score(push)` | 推文數欄位轉分數（爆=100、X=負） | |
| 快取層 `read_cache/write_cache_if_track/cache_summary` | 追蹤項結果快取 `data/cache/{id}.json`（原子寫入） | 開頁即看不用重掃 |
| `mark_new_results(results, old)` | 跟上一版比對標 new=True（UI 顯「新」徽章）；無舊資料不標 | 🆕 build_site 線上版同用 |
| `refresh_auto_tracks(force)` / `auto_refresh_loop()` | auto 追蹤項自動重掃（啟動補掃＋每15分檢查，快取 6 小時過期） | `--refresh-only` 給每日排程 `PTT_Assistant_DailyCache` 用 |
| ~~`export_results_txt`~~ | 已移除（2026-08-22），全文匯出走 `run_download` | |
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
| `GET /api/cache/<track_id>` | 追蹤項快取結果（開頁即看） |
| `POST /api/download` | 批次下載：urls＋include_comments → job，完成後 job.file 可下載 |
| `GET /files/<name>.txt` | 下載 output/ 內的 TXT（Content-Disposition attachment，擋路徑跳脫） |
| ~~`POST /api/export`~~ | 已移除（2026-08-22）：UI 改用 /api/download 批次下載全文 |
| `POST /api/tracks` | 新增/更新/刪除追蹤項 |

## 線上版（GitHub Pages，詳見 GIT_PUBLISH.md）

- `scripts/build_site.py`：♻️ 調用 server.py 的 run_task/run_hot 產 `site/data/*.json`（Actions 與本機都能跑）。
- `site/index.html`：唯讀靜態頁（省錢優惠＋熱門文章），部署在 https://dino-q.github.io/ptt-tracker/
  - 🆕 `triggerRefresh()`（2026-08-23）：「立即更新」鈕＝瀏覽器直呼 GitHub API workflow_dispatch → 輪詢 run 完成 → 偵測 money.json updated_at 變化 → 自動 reload；PAT 存 localStorage `ptt_gh_token`（僅該裝置），401/403 自動清除重導設定。測試：tests/verify_refresh.py（mock GitHub API 三情境）
  - 🆕 `CAT_ALL_TIME`／`allTimeOn()`（2026-09-04）：熱門的「不限天數」分類。低流量板（女板/BG）能過留言門檻的文常已 1-3 週，會被預設 3 天窗整批濾掉——資料在 hot.json，畫面上一篇都沒有。此分類跳過 `dayOk`、固定依收錄時間新→舊排，並隱藏期間／排序鈕。測試：`tests/verify_alltime_tab.py`（真瀏覽器，斷言對著行為寫）
  - ⚠️ `dayFiltered` 必須寫成 `results.filter(r => dayOk(r))`。寫 `results.filter(dayOk)` 會讓 `filter` 的第二個參數（索引）跑進 `dayOk` 的 `allTime`，索引 ≥1 全是 truthy → 天數過濾整個失效（2026-09-04 實際踩到）
- `.github/workflows/update.yml`：台灣 08–23 點每小時 cron（深夜停跑）＋push＋手動觸發，資料走 Pages artifact 不進 git 歷史。
- `.github/workflows/ocr-ab.yml`：🆕 手動觸發的 OCR 收緊 A/B 對照，只產 artifact、不部署。

## image_ocr.py（🆕 免費圖片文字辨識，2026-09-03）

| 名稱 | 用途 | 備註 |
|---|---|---|
| `extract_image_urls(text, max_images)` | 從 PTT 文章純文字擷取直接圖片網址，支援 Imgur 頁面網址正規化 | 保持順序、去重 |
| `ocr_article_images(body, max_images)` | 下載公開圖片並呼叫 Tesseract，回 checked/image_urls/text/errors | 校正方向、放大與對比增強；PSM 11/6 雙版面辨識，依 TSV 座標重組區塊；擋私有網段、8 MB 上限 |
| `append_ocr_block(text, ocr_text)` | 將 OCR 結果以明確警語併入摘要或全文 | 可重複呼叫，不會重複附加 |
| `scripts/build_site.py:fill_image_ocr(...)` | 線上省錢資料逐輪補 OCR；沿用舊結果、每輪最多檢查 12 篇 | GitHub Actions 使用 `chi_tra+eng`，不呼叫付費 API |
| `OcrTuning` / `LEGACY_TUNING` / `TIGHTENED_TUNING` / `DEFAULT_TUNING` | 🆕 2026-09-04 OCR 收緊參數（字級信心門檻、碎片過濾、擇優計分）。全部 OCR 函式都吃 `tuning=` | **調參一律傳這個物件，不要複製一份 pipeline 出去改。** `DEFAULT_TUNING` 目前＝`LEGACY_TUNING`（線上行為未變）；Dino 看過 A/B 後改成 `TIGHTENED_TUNING` 即上線 |
| `_line_is_useful(line)` | 🆕 判斷一行有無資訊（≥2 中文字／價格日期數量／≥4 字母品牌名），拿不準回 True | ⚠️ 只在新 OCR 路徑用，且要搭配 `junk_conf_ceiling` 才敢丟；`clean_ocr_text` **不吃**它（否則會回頭誤刪已部署資料） |
| `scripts/ocr_ab_compare.py` | 🆕 收緊前後並排對照報告（HTML＋JSON） | 必須在 Actions 跑（`.github/workflows/ocr-ab.yml`），本機 Windows 的 tesseract 版本不代表線上。⚠️ 報告刻意不用 `_line_is_useful` 算雜訊率——那是收緊時砍字的規則，拿它當尺必然得 0% |

## 啟動器（.bat ＋ launcher）

| 名稱 | 用途 | 備註 |
|---|---|---|
| `啟動.bat` / `安裝.bat` | 雙擊入口，純 ASCII 外殼 | 用萬用字元解析中文檔名的目標（`PTT*.bat`／`????.bat`），檔案本身不含任何中文 |
| `PTT工具.bat` | 檢查 venv → 叫 `scripts/launcher.py` | 純 ASCII |
| `scripts/launcher.py` | 🆕 2026-09-04 中文主選單＋分流（[1] server.py／[2] ptt_tool.py／[3] preview_site.py） | **所有中文 UI 放這裡，不要搬回 .bat** |
| `scripts/preview_site.py` | 🆕 預覽線上版 `site/`（缺資料自動抓線上 JSON），預設 port 8891 | 改 `site/index.html` 要用這個看；`啟動.bat` 的 [1] 是 server.py＋`web/index.html`，**兩者是不同頁面** |

⚠️ **.bat 一律純 ASCII，這是硬規則**（2026-09-04 踩到）：

- cmd.exe 解析 .bat 用系統 OEM 碼頁（台灣機器＝cp950），而專案的 .bat 存 UTF-8。UTF-8 的中文位元組被當成 cp950 雙位元組配對會錯位，**行尾換行被吃成後綴位元組**，下一行整個黏上來、指令消失。
- 實測 git 原版 `PTT工具.bat` 在 cp950 下有 13 行以上被吃掉（`'ython.exe" server.py'`、`'ho.'`…）；`啟動.bat` 因此 `call` 失敗、又沒有 `pause`，就是「雙擊後閃一下就關掉」。
- 在 .bat 裡加 `chcp 65001` **只能救一部分**，會不會壞取決於那行的位元組怎麼配對，不可靠。
- 反方向（.bat 存成 cp950）**也不行**：`server.py`／`ptt_tool.py` 含 cp950 表示不出來的字元（`♻ ⚠ ≈ é`），主控台切 cp950 會在印出時 UnicodeEncodeError。
- 結論：.bat 只做 `chcp 65001` ＋ 呼叫 Python，中文全部留在 Python。改 .bat 前先跑 `python -c "print(open('X.bat','rb').read().isascii())"` 確認是 True。
- 換行仍必須 CRLF（全域規則）。

## 排程

- `PTT_Assistant_DailyCache`：每日 08:30 `pythonw server.py --refresh-only` 更新 auto 追蹤項快取（電池模式也跑）。詳見 `路徑相依_搬移前必讀.md`。
