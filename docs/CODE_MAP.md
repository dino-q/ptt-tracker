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
| `always_boards`（hot.json 欄位）／前端 `alwaysBoard()` | 🆕 2026-09-04 固定收錄板（女板/BG）**豁免前端的天數窗**，預設熱門清單就看得到 | 這些板的文要過留言門檻常已 1-3 週，但討論度是現在才累積的；用發文時間擋等於永遠看不到（Dino：「不然熱門文章很無聊」）。板名由後端帶下來，不在前端寫死 |
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
  - ❌ ~~`CAT_ALL_TIME`「不限天數」分類~~（2026-09-04 加、同日移除）：它跟篩選面板的
    「含回鍋（不分期間）」（`HOTMODE="all"`）做**完全同一件事**，兩個入口只會讓人搞混
    （Dino：「含回鍋就是不限天數對吧」）。**不要再加回來**——要看全部舊文用含回鍋。
    低流量板的可見性改由 `always_boards` 豁免處理。
  - 🆕 `SORT="posted"`「依時間」（2026-09-04）：依**發文時間**（`hotPostTs`）排。
    跟「最新熱門」（`SORT="time"`＝`accepted_at` 收錄時間）是兩件事——三週前的文
    今天才過門檻被收錄，在「最新熱門」排很前面、在「依時間」會落到後面。
  - 🆕 `BOARD_ORDER` / `orderBoards()` / `moveBoard()`（2026-09-04）：看板順序可自訂，
    存 `localStorage.ptt_board_order`。展開看板篩選 →「調整順序」→ 每個板出現 ◀ ▶。
    **沒排過的板依篇數接在後面**，所以新板不會被吃掉、也不必每次重排。
    用左右鈕不用拖曳：手機上拖曳難精準，且要多帶一套指標事件處理。
    測試：`tests/verify_hot_controls.py`（斷言順序真的改變＋重載後仍記得）
  - 🆕 `setupClip()` / `.art-clip` / `.art-more`（2026-09-04）：閱讀器改成**漸進展開**。
    舊做法 `.preview { max-height:72vh; overflow-y:auto }` 在手機上讓內容 4075px 擠進 608px 視窗，
    頁面與卡片兩個捲軸互搶、滑動卡住。現在不裁成內捲框，先顯示 520px，按一次多放 900px。
    ⚠️ **setupClip 必須在卡片 `.open` 之後才呼叫**——`display:none` 時 `scrollHeight` 是 0，
    會誤判成「不夠長不用裁」（2026-09-04 實際踩到，用 `container._clip` ＋ rAF 延後）。
    測試：`tests/verify_reader_expand.py`（真瀏覽器，斷言「內捲軸不存在」而非「按鈕存在」）
  - 🆕 `scripts/preview_site.py` 的**代理**：本機沒有的檔案自動抓線上版。
    少了它，`data/articles/*.json` 在本機是空的，前端會走「抓不到全文」的退路，
    `fillArticle` 根本不會執行——驗收會在驗一個沒被觸發的程式路徑。
  - ⚠️ `dayFiltered` 必須寫成 `results.filter(r => dayOk(r))`。寫 `results.filter(dayOk)` 會讓 `filter` 的第二個參數（索引）跑進 `dayOk` 的 `allTime`，索引 ≥1 全是 truthy → 天數過濾整個失效（2026-09-04 實際踩到）
- `.github/workflows/update.yml`：台灣 08–23 點每小時 cron（深夜停跑）＋push＋手動觸發，資料走 Pages artifact 不進 git 歷史。

## image_ocr.py（圖片辨識，2026-09-04 換成 Gemini）

**為什麼換掉 Tesseract**：實測輸出 46% 是雜訊（最差一篇 73%）。這不是調參問題——
優惠海報是格狀排版，品項、價格、期間、取得管道分散在不同格子裡，逐字擷取的 OCR
結構上就配不起來。Gemini 讀同一張圖回的是「大杯拿鐵／買1送1／100→50元／APP」。
⛔ **不要提議「調 PSM／加前處理再試一次」**，那條路 09-03～09-04 走過了。

| 名稱 | 用途 | 備註 |
|---|---|---|
| `extract_image_urls(text, max_images)` | 從 PTT 文章純文字擷取直接圖片網址，支援 Imgur 頁面網址正規化 | ♻️ 換引擎時原樣保留：這層跟用哪個引擎無關 |
| `_is_public_url` / `_download_image` | 白名單圖床＋每次 redirect 前重驗＋公網 IP＋8 MB 上限 | ♻️ 同上保留。⚠️ 驗證必須在**跟 redirect 之前**，等 requests 跟完 SSRF 已經發生 |
| `_REQUEST_HEADERS` | 下載圖片用的 header | ⛔ **絕對不要加 `Referer`**。2026-09-04 實測：帶 `Referer: https://www.ptt.cc/` 時 i.imgur.com 一律回 403（防盜連），11 張圖 0 成功；拿掉後 11/11，i.mopix.cc 未受影響。imgur 是 PTT 最常用的圖床，這條踩下去等於整個功能失效。`tests/test_image_ocr.py::test_no_referer_header_imgur_blocks_hotlinking` 守著 |
| `_sniff_mime(data)` | 🆕 靠 magic bytes 判圖片型別 | 副檔名是 PTT 文章作者寫的，不能信 |
| `read_image_url(url)` | 🆕 下載單張圖交給 Gemini 讀，回純文字 | 模型回「無相關資訊」時轉成空字串，不要把這四個字塞進使用者的優惠摘要 |
| `ocr_article_images(body, max_images)` | 讀文章內圖片，回 checked/image_urls/text/errors/**engine** | 沒圖片就不打 API；單張壞圖不中止整篇；**有任何錯就不標 checked**，下一輪重讀 |
| `OCR_ENGINE`（目前 `"gemini-1"`） | 🆕 引擎版本標記 | **換引擎時改這個字串**，`build_site` 就會把舊引擎讀過的全部重讀一次 |
| `strip_ocr_block(text)` | 🆕 移除任何版本的辨識區塊（含舊版 `自動 OCR` 標題） | 換引擎重讀前一定要先做，否則上一代亂碼留在使用者眼前 |
| `append_ocr_block(text, ocr_text)` | 將結果以明確警語併入摘要或全文 | 可重複呼叫，不會重複附加；傳空字串＝移除既有區塊 |
| `scripts/build_site.py:fill_image_ocr(...)` | 線上省錢資料逐輪補圖片文字；每輪上限 12 篇 | ⚠️ **沿用要比對 `ocr_engine`**。只看 `ocr_checked` 的話，Tesseract 時代那批雜訊會被永遠沿用下去——這是換引擎最容易漏掉的一步，`tests/test_build_site_ocr.py` 有測試守住 |

## gemini_client.py（🆕 2026-09-04，Gemini 呼叫層）

| 名稱 | 用途 | 備註 |
|---|---|---|
| `available()` | 有金鑰且裝得起 SDK 才回 True | 呼叫端拿它決定要不要進入整段流程 |
| `parts()` | 回 `google.genai.types` | 讓呼叫端組 Part 而不必各自處理 ImportError |
| `generate(contents, config, label, quiet)` | 打一次 Gemini，內建重試＋備援模型；失敗回 `None` 不丟例外 | **要調重試或換模型一律改這裡。** 咖啡情報與圖片辨識都吃這支；複製出去兩邊遲早分岔。`quiet=True` 給「一輪打很多次」的場景，避免同一個錯誤刷滿 log |
| `REQUEST_TIMEOUT_MS`（120 秒） | 單次呼叫硬上限 | SDK 預設**不設 timeout**，一個卡住的請求會拖到整個 Actions job 撞 30 分鐘上限。實測單張圖 ~90 秒，所以給 120 秒 |
| `MIN_INTERVAL_SECONDS`（4 秒） | 兩次呼叫最小間隔 | 免費層額度很小，爆量打只會失敗＋重試把情況弄更糟 |
| `MODEL` / `FALLBACK_MODEL` | `gemini-3.8-flash` → `gemini-2.5-flash` | 環境變數 `GEMINI_MODEL` / `GEMINI_MODEL_FALLBACK` 可覆寫。3.8-flash 常回 503「high demand」，2026-09-04 線上第一輪就是靠備援跑成功的 |

### ⛔ Gemini 免費層額度：**每個模型每天 20 次**（2026-09-04 實測）

錯誤原文：`429 RESOURCE_EXHAUSTED … quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 20`

這個數字決定了整個功能能做到什麼程度，**改任何跟 Gemini 有關的用量之前先看這條**：

- 一天 16 輪排程。咖啡情報只有「發現新文章」才呼叫（平常沿用，不花額度）。
- 圖片辨識一篇最多 2 張圖＝2 次呼叫。`IMAGE_BUDGET` 預設壓到 **2 篇/輪**。
- **咖啡情報排在圖片辨識前面**（`build_site.main`）：置頂區塊是使用者一進站就看到的，
  優先權高於逐輪補圖。順序反過來的話，圖片會把額度吃光、置頂區直接開天窗。
- **`is_daily_quota_error()`**：把「每日額度用完」跟「尖峰塞車」分開。兩者都是
  429/RESOURCE_EXHAUSTED，但處理相反——尖峰要重試、每日額度同一輪內**不可能**恢復。
  額度是每個模型各自算，所以仍會換下一個模型試，但同一個模型不再重試。
  撞到就整輪停手（`build_site` 設 `stopped`）。實測代價：不擋的話 2 篇文章 4 張圖打 16 次全 429。
- ⚠️ **print 的字串不要放 emoji**：`⚠️` 讓 `build_site.py` 在 cp950 主控台直接
  `UnicodeEncodeError` 崩潰（Actions 是 UTF-8 看不出來，本機跑就炸）。用「【注意】」這種純文字。
  ⚠️ 但 `coffee_news.PROMPT` 裡的 `📍`／`🟡` **要留著**——那是在告訴 Gemini
  「NowNews 文章用這種符號標管道」，不是輸出。
- 保險三道：`IMAGE_PHASE_SECONDS`（480 秒上限）、`MAX_CONSECUTIVE_FAILURES`（連 4 篇失敗就停手）、
  `IMAGE_ATTEMPTS`（單張只重試 2 次）。撞到額度時 log 會明講。
- **開通付費後**：把 `PTT_IMAGE_BUDGET` 環境變數調大（12 以上）才有辦法在幾小時內把
  存量文章補完；否則 119 篇要補好幾天。

## 咖啡情報（🆕 2026-09-04）

| 名稱 | 用途 | 備註 |
|---|---|---|
| `scripts/coffee_news.py` | 抓 NOWnews「本周咖啡優惠」週更專欄 → 結構化成 `site/data/coffee.json` | 🆕 新寫（不沿用 `run_task` 的原因：那是 PTT 掃描引擎，來源、解析、輸出格式全都不同） |
| `coffee_news.find_latest()` | 兩個來源合併挑最新一篇 | ⚠️ **不要改回用 nownews 站內搜尋**：`/search?q=` 對程式化存取是壞的，2026-09-04 實測連只搜「咖啡」都回「查無符合資料」 |
| `coffee_news.extract()` | 丟 Gemini 做結構化（通路／品項／原價／優惠價／期間） | ♻️ 沿用 `gemini_client.generate`（金鑰／重試／備援模型）。原本這裡自帶一份同樣的重試迴圈，2026-09-04 圖片辨識也要用時抽出去共用 |
| `site/index.html:renderCoffee()` | 置頂區塊：通路捷徑 chips ＋ 依通路分組的優惠列 ＋ 可收合（狀態存 localStorage） | 只在省錢頁顯示；沒有 coffee.json 就整塊不出現，不留空殼 |

**來源策略**（兩個都是純 HTTP，不需要瀏覽器）：

- `https://feed.nownews.com/rss/7d948070-...`：官方 RSS，真實網址與時間，但只有最新 20 筆（全站混合）
- `https://www.nownews.com/cat/life/`：生活分類頁，伺服器端渲染，補 RSS 被洗掉的漏
- ❌ Google News RSS 找得到文章，但 `<link>` 是 JS 轉址頁、解不出真實網址，所以沒用

**收錄範圍**（2026-09-04 Dino 兩次調整後的現況）：**只收 NOWnews**，標題同時含「咖啡」
與優惠字樣（`COFFEE_RE` ＋ `DEAL_RE`）。⚠️ 一度改成只認精確片語「本周咖啡優惠」，
實測**抓到 0 筆**——這系列標題不固定（五六日咖啡優惠／週末咖啡買一送一／開學開工咖啡優惠…），
而當天真正有效的那篇反而被擋掉。別再改回精確片語。

**「管道」欄位（門市／APP／LINE禮物／會員）**：文章用 `📍門市｜9月2日至9月6日`
`📍APP｜9月2日至9月11日` `🟡LINE禮物（7-11電子票券）` 標示。
**同一家超商不同管道的價格常常不一樣，不可以合併**——7-ELEVEN 一篇裡就有 5 種
（LINE禮物／門市×2／APP×2）。schema 與 prompt 都明確要求分開填，前端也依管道分塊顯示。

**沒有總期間時**：前端 `summarizeCoffeePeriod()` 會從各通路期間撈出所有「M月D日」，
取最早與最晚合成範圍（例如 8/10～9/29）。否則收合態完全看不到日期，
而「優惠到什麼時候」正是最該先看到的資訊。

**（歷史）** 只認「本周咖啡優惠」的舊設定已作廢。


**部署**：`update.yml` 需要 repo secret `GEMINI_API_KEY`；沒設也不會壞（會安靜跳過咖啡那段）。

**Tor（設計主管）2026-09-04 審查後的必要修正**（改這塊前先看，別退回去）：

- **預設收合**：`coffeeCollapsed()` 無記錄時回 `true`。54 筆優惠不該擋在文章清單前面；
  收合態仍保留標題／來源／期間／通路捷徑當預覽。
- **收合時點捷徑要先自動展開**，否則會捲到一個 `display:none` 的區段。
- **捷徑鈕尺寸對齊 `.tab`**（padding 7px/`--space-4`、字級 .85rem）。原本 5px/.82rem
  換算只有 30px 高，是全頁最小的可點擊目標，9 顆並排最容易點錯。現為 38px。
- **`.coffee-jump-wrap::after` 右側漸層**＝「還能往右滑」的提示；沒有它使用者不知道右邊還有。
- **`.coffee-deal .d-price s` 不可以加 `opacity`**。Tor 用 OKLab→sRGB 換算實測，
  `opacity:.7` 讓對比度掉到 **3.33:1**（未達 WCAG AA 4.5:1）。刪除線本身已足夠表達語意。
- **`aria-controls`**：收合鈕指向 `#coffee-collapsible`；`.art-more` 指向 clip 的 id
  （原本掛 `aria-expanded` 但恆為 false，形同虛設）。
- **`setupClip.finish()` 要轉移焦點**：按鈕被 remove 時鍵盤焦點會掉回 `<body>`。
- **展開步長隨長度放大**（`max(900, full*0.25)`）：固定 900px 對兩萬 px 的長文要點 22 次。
- **按鈕文案要講明「含留言」**：clip 同時包內文與留言，百分比是合計，不講會誤導。

完整報告：`agent_team\workspace	or_design\PTT_Assistant6-09-04-coffee-section-and-progressive-reader.md`
（還有幾項「可選」未做：內文與留言拆成兩個 clip、body 也做前 3 通路的漸進揭露、桌機不橫捲）

## 啟動器（.bat ＋ launcher）

| 名稱 | 用途 | 備註 |
|---|---|---|
| `啟動.bat` / `安裝.bat` | 雙擊入口，純 ASCII 外殼 | 用萬用字元解析中文檔名的目標（`PTT*.bat`／`????.bat`），檔案本身不含任何中文 |
| `PTT工具.bat` | 檢查 venv → 叫 `scripts/launcher.py` | 純 ASCII |
| `scripts/launcher.py` | 🆕 2026-09-04 中文主選單＋分流（[1] server.py／[2] ptt_tool.py／[3] preview_site.py） | **所有中文 UI 放這裡，不要搬回 .bat** |
| `scripts/preview_site.py` | 🆕 預覽線上版 `site/`（缺資料自動抓線上 JSON），預設 port 8879 | 改 `site/index.html` 要用這個看；`啟動.bat` 的 [1] 是 server.py＋`web/index.html`，**兩者是不同頁面** |

⚠️ **.bat 一律純 ASCII，這是硬規則**（2026-09-04 踩到）：

- cmd.exe 解析 .bat 用系統 OEM 碼頁（台灣機器＝cp950），而專案的 .bat 存 UTF-8。UTF-8 的中文位元組被當成 cp950 雙位元組配對會錯位，**行尾換行被吃成後綴位元組**，下一行整個黏上來、指令消失。
- 實測 git 原版 `PTT工具.bat` 在 cp950 下有 13 行以上被吃掉（`'ython.exe" server.py'`、`'ho.'`…）；`啟動.bat` 因此 `call` 失敗、又沒有 `pause`，就是「雙擊後閃一下就關掉」。
- 在 .bat 裡加 `chcp 65001` **只能救一部分**，會不會壞取決於那行的位元組怎麼配對，不可靠。
- 反方向（.bat 存成 cp950）**也不行**：`server.py`／`ptt_tool.py` 含 cp950 表示不出來的字元（`♻ ⚠ ≈ é`），主控台切 cp950 會在印出時 UnicodeEncodeError。
- 結論：.bat 只做 `chcp 65001` ＋ 呼叫 Python，中文全部留在 Python。改 .bat 前先跑 `python -c "print(open('X.bat','rb').read().isascii())"` 確認是 True。
- 換行仍必須 CRLF（全域規則）。

## 排程

- `PTT_Assistant_DailyCache`：每日 08:30 `pythonw server.py --refresh-only` 更新 auto 追蹤項快取（電池模式也跑）。詳見 `路徑相依_搬移前必讀.md`。
