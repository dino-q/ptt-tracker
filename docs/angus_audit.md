# Angus 交付前審查 — PTT_Assistant 網頁版（2026-08-22）

審查對象：`server.py`（新）、`web/index.html`（新）、`PTT工具.bat`、`docs/CODE_MAP.md`、`tests/verify_ui.py`
方法：read-only 靜態審查 ＋ 離線函式實測（parse_request/parse_list_date/safe_filename/urljoin）＋ 本機 HTTP 錯誤路徑黑箱實測（另起 port 8971，測完已清掉自己起的 process）。

## Pre-flight

- ⚠️ **本專案不是 git repo**（`git status` → fatal: not a git repository）。無法用 diff 界定改動範圍，本次以「主 agent 提供的檔案清單 ＋ 全檔通讀」替代；也代表這次交付**沒有任何版本可回滾**。建議交付前 `git init` ＋ 首次 commit（照 GIT_PUBLISH.md 規則決定要不要上遠端）。

---

## 1. 同 pattern 的兄弟 bug

- ✅ **背景 job 鎖使用無巢狀** — `job_log()` 本身取 `_jobs_lock`（server.py:291-293），全部呼叫點（316/325/331/336/351/414/420/424）都在鎖外，`with _jobs_lock` 區塊（360/415/421/425/443/550/585）內沒有再呼叫 `job_log` → 無 deadlock。
- ✅ **job 清理不會踢掉 running job** — server.py:446-449 有 `if JOBS[old_id]["status"] != "running"` 保護，且新 job 先 `JOBS[job_id]=job` 再淘汰、`list(JOBS)[:-20]` 保留最新 20 個，順序正確。
- ⚠️ **例外靜默吞沒是全檔重複 pattern（3 處同形）** — server.py:374-375 / 385-386 / 394-395 三段 `except Exception: continue|pass`（讀內文失敗）＋ index.html:417 `catch (e) { /* 下一輪再試 */ }`。內文讀取那三處吞掉是合理設計（單篇失敗不該中斷整批），但**完全沒有計數**：30 篇內文全部讀失敗（PTT 擋 IP、網路斷）時，log 只會顯示「完成：N 篇符合（讀取內文 30 篇）」，使用者無法分辨「內文空是因為沒抓到」還是「本文真的短」。建議吞的時候 `body_fail += 1`，收尾在 job log 補一行「內文讀取失敗 X 篇」。
- ✅ `ptt_tool.py` 未改動，`_get()`（ptt_tool.py:86-101）失敗會 raise RuntimeError 不吞，沿用面沒有引入新的吞沒點。

## 2. Silent failure paths

- ❌ **pollJob 對所有失敗靜默吞掉 → 永久轉圈、按鈕卡死** — **web/index.html:397-418**。`catch (e) {}` 空實作，沒有連續失敗計數、沒有 404 判斷。三種都會發生的情境會讓 UI 永遠停在「掃描中」、`#btn-run` 永久 disabled、且不給任何訊息：
  1. server 視窗被關掉（bat 就是這樣結束的）；
  2. job 被 20 個上限淘汰（server.py:446）後回 404（實測 `GET /api/jobs/deadbeef` → 404）；
  3. 輪詢打到另一個 server process（見 3 的 B2）。
  修法：`fail++`，`fail >= 5` 或 HTTP 404 就 `clearInterval` ＋ 在 `#form-error` 寫「與伺服器失去連線，請重開視窗」，並恢復按鈕。
- ⚠️ **取消後已抓到的結果全丟、UI 停在「掃描中」** — server.py:419-422 只在 `done` 才寫 `job["results"]`（415-418），cancelled 分支不寫；index.html:405-416 只處理 `done`/`error`，`cancelled` 兩者都不是 → `showResults()` 不會被呼叫 → `#progress` 區塊（含 h2「掃描中」）繼續顯示、結果區維持隱藏。使用者只能從 log 最後一行「已取消」猜。建議取消時把已完成的 `results` 一併存回並顯示「已取消，先給你目前抓到的 N 篇」。
- ⚠️ **tracks.json 讀取失敗靜默回 default，且會被 default 覆寫** — server.py:133-136 `except: return default_tracks()`。搭配 139-143 的**非原子寫入**（直接 `write_text` 覆蓋），寫入中途中斷 → 0-byte / 半截 JSON → 下次開啟使用者自訂的追蹤項**無聲消失**，接著任何一次「存成追蹤項」會 `save_tracks()` 把 default + 新項寫回去，舊資料永久蒸發。修法：`tmp + os.replace` 原子寫；parse 失敗改名成 `tracks.json.bad` 並在 `/api/meta` 回一個 warning 欄位讓 UI 顯示。
- ⚠️ **`/api/tracks` 的 read-modify-write 跨兩次鎖** — server.py:599-615：`load_tracks()`（取鎖→放鎖）→ 改 list →`save_tracks()`（再取鎖）。ThreadingHTTPServer 並行兩個請求會 lost update（同時刪＋存 → 刪掉的復活）。單人使用機率低，但把整段包進一個鎖（或加 `_tracks_lock` 的 RLock 版 helper）成本極低。

## 3. 修法本身

- ❌ **B1：重複開始掃描 → 洩漏輪詢 timer ＋ 產生無法取消的孤兒 job** — **web/index.html:380-395（runTask）、318（追蹤項按鈕）、420-421**。
  `$("btn-run").disabled = true` 是在 `await post("/api/run")` **之後**才設；而追蹤項的「掃描」按鈕（318）**從頭到尾沒有 disable**，`runTask` 也沒有 `if (JOB) return` 也沒有先 `clearInterval(POLL)`。
  確定性重現（不需要搶時序）：按「開始掃描」→ 掃描中直接按任一追蹤項的「掃描」→
  - `POLL` 被覆寫，第一個 `setInterval` 永久洩漏（之後每 900ms 空跑一次 `if (!JOB) return`）；
  - `JOB` 被覆寫，第一個 job **再也取消不到**（取消鈕只送新 JOB），它會繼續打 PTT 直到跑完，等於同時兩條爬蟲、PTT 請求速率翻倍（`delay` 0.4s 的禮貌設計被抵銷）；
  - 第一個 job 的結果靜默丟棄。
  修法：`runTask` 開頭同步 `if (JOB) { $("form-error").textContent = "已有掃描進行中"; return; }`、`if (POLL) clearInterval(POLL)`，並把追蹤項 run 按鈕一起 disable（或整段用一個 `setBusy(bool)` 統一控制）。
- ❌ **B2：port 重複綁定，伺服器可以「靜默共用/被別的程式冒名回答」** — **server.py:629**。`ThreadingHTTPServer` 繼承 `allow_reuse_address = 1`，在 **Windows 上 SO_REUSEADDR 允許多個 process 同時綁同一個 port**（不像 Linux 會 EADDRINUSE）。實測：
  - 同一支 server.py 連開 3 次 → `netstat -ano | grep 8971` 出現 **3 個 LISTENING**（PID 27608/47412/22048），沒有任何錯誤訊息；
  - 我第一次黑箱測試誤用 8899（read_txt 閱讀器「我的書房」正在用）→ server.py **綁定成功、毫無警告**，但我打過去的每一個 `/api/*` 都由另一支程式回答 `{"error":"未登入"} 401`。
  對使用者的具體後果：重複雙擊 `PTT工具.bat`（很常見，因為視窗看起來沒反應）→ 兩個 server 搶 8877 → 瀏覽器的 `/api/run` 落在 A、`/api/jobs/<id>` 輪詢落在 B → 404 → 接上 2 的靜默吞沒 → **永遠轉圈**。
  修法：自訂 `class Server(ThreadingHTTPServer): allow_reuse_address = False`（Windows 上更嚴謹是 `SO_EXCLUSIVEADDRUSE`），bind 失敗時印中文訊息「8877 已被占用，可能已經開過一個視窗；或用 --port 換 port」並 `sys.exit(1)`；`main()` 目前對 `OSError` 完全沒處理，只會噴 traceback。
- ❌ **B3（同一條鏈的另一端）：bat 網頁模式失敗會「視窗一閃就關」** — **PTT工具.bat:32-34**。`".venv\Scripts\python.exe" server.py` 後直接 `exit /b %errorlevel%`，**沒有 pause**（CLI 分支 42-52 有）。server 啟動失敗（port 被占、套件缺、traceback）時使用者只看到黑窗一閃，拿不到任何訊息，無法自救也無法回報。修法：`if not "%ERR%"=="0" ( echo [ERROR] ... & pause )`。
- ⚠️ **HTTP handler 沒有總 try/except，未預期例外＝完全不回應** — server.py:524/567 兩個 route dispatch 都是裸的。實測 `POST /api/export` 帶 `{"results":["abc"]}` → `export_results_txt` 的 `r.get(...)` AttributeError → **連線直接斷、沒有任何 HTTP response**（curl 回 `[000]`），server console 噴 traceback。同類洞還有 `export_results_txt` 的 `write_text`（磁碟滿/檔名含 `\x00`/output 被鎖）。修法：dispatch 外層包 try/except 回 `500 {"error": str(exc)}`，UI 才有東西顯示。
- ⚠️ **`/api/run` 邊界零驗證，型別錯會變成「猛打 PTT」** — server.py:577-582 只檢查 board 非空。實測 `{"task":{"board":"Stock","days":"abc"}}` → 回 200 + job_id，錯誤延到 worker 才炸，UI 顯示生的 Python 訊息 `invalid literal for int() with base 10: 'abc'`。更糟的是 `queries` 傳字串："coffee" 會被 `[q for q in "coffee"]`（server.py:300）**逐字元**當成 6 個關鍵字，各自跑一次板內搜尋（每次最多 3 頁）。另外 `scan_latest_pages`/`search_pages`/`days` 沒有上限（UI 有 max=15 但 server 不管）、`delay` 可傳 0 或負數 → 無延遲連打 PTT。修法：在 `/api/run` 就驗證型別＋clamp（pages ≤ 15、days ≤ 365、delay ≥ 0.2），錯誤回 400 中文訊息。
- ⚠️ **`days=0` 語意反轉（0 不是「只看今天」而是「不限」）** — server.py:347 `if days and dt and (today - dt).days > days`：`days=0` 為 falsy → **完全不做日期過濾**。而 UI 的欄位是 `min="0"`（index.html:227）、`readForm()` 又 `Math.max(0, ...)`（index.html:353），使用者填 0 期待「今天」，實際拿到整批歷史文（也代表更多內文讀取與 PTT 請求）。修法：`min="1"`，或把標籤改成「0＝不限天數」。
- ⚠️ **`fillForm`/`readForm` 不能無損來回，內建追蹤項的週末提示會消失** — index.html:339-363。`weekend` 是從 `#ask-input` 的文字重算（361），但 `fillForm` 不會回填 ask-input；開頁時 init 自動載入內建週末追蹤項（532）→ 使用者直接按「開始掃描」→ `weekend=false` → server.py:410-412 的週末視窗提示（note）**靜默消失**。同理 `search_pages: 3` / `max_body_reads: 30` 是寫死的（354-360），追蹤項存回去時原本的值遺失（例如內建的 `max_body_reads: 30`、未來想調 `search_pages: 5`）。修法：`fillForm` 把整個 task 存到一個 `CURRENT_TASK`，`readForm` 以它為底只覆寫表單有的欄位。
- ⚠️ **取消未知 job 回報假成功** — server.py:583-589：job 不存在時仍 `{"ok": true}`（實測 `POST /api/jobs/deadbeef/cancel` → 200）。應回 404，否則 UI 無法察覺「你以為取消了，其實那個 job 在別的 server process 上」（正好是 B2 的情境）。
- ⚠️ **改動點附近沒有 server 端測試** — `tests/` 只有 `verify_ui.py`（Playwright，需要真的連 PTT，且 3 分鐘級）。`parse_request` / `parse_list_date` / `match_groups` / `_word_hit` 全是純函式、零 IO，卻沒有一個 unit test 守著（這次「OK 誤判」就是這類 bug）。建議補一支 `tests/test_parse.py`（pytest 或純 assert 皆可，秒級），至少釘住：OK 不命中內文的 "ok"、`最近7天` → days=7、跨年 12/31、閏日回 None、`must_groups` 空＝不過濾。
- ✅ **新引入的 state 都有對應路徑** — `tracks.json`（首次自動建、server.py:125-136）、`output/*.txt`（export 時 mkdir，server.py:458）都不需要 cleanup（使用者資料，故意留）；job 只在記憶體、有 20 個上限。沒有 temp 檔殘留。
- ✅ **回傳 shape 沒有偷改** — 沿用 `ptt_tool.PTTClient` 的 `SearchItem`/`Article` 欄位，server.py 只讀 `.url/.title/.date_text/.author/.body`（author 還用 `getattr` 保底，403）；ptt_tool.py 未動，CLI 路徑（`ptt_tool.py:478-513`）不受影響。

## 4. UI / response 表面

- ✅ **空結果不會變空白畫面** — index.html:439-441 有 `else` 分支輸出「沒有符合條件的文章。可以放寬…」；`showResults()` 也處理 `NOTE` 空字串（427）。實測 server 端 `cands=0` 時仍回 `status:done, results:[]` → UI 顯示 0 篇提示，非空 HTML。
- ✅ **無 path traversal** — `_file()`（server.py:512-521）只被兩個固定字面路徑呼叫（`WEB_DIR/"index.html"`），沒有任何使用者輸入拼進路徑；其餘路由是白名單 if/elif，落底 404。實測 `GET /../server.py`（--path-as-is）→ 404、`GET /web/index.html` → 404。
- ✅ **`/api/article` 白名單擋得住** — server.py:540 的 `startswith("https://www.ptt.cc/bbs/")` 前綴已包含 authority，之後不可能再注入 host（`@`、`//` 都只能落在 path）。實測 `https://www.ptt.cc.evil.com/...` → 400、`http://127.0.0.1:8971/api/meta` → 400、`https://www.ptt.cc/bbs/@evil.com/x` → 502（真的去打 ptt.cc 拿到 404，沒外連）。
- ✅ **無 XSS** — 所有 PTT 來源字串都走 `textContent`（index.html:317/320/449/453/460/467），`innerHTML` 只塞靜態字面字串（309/440）。
- ⚠️ **`item.url` 沒有白名單就直接 fetch／塞進 href** — server.py:372/381/390 `client.article(it.url)`、index.html:448 `a.href = r.url`。url 來自 `urljoin(BASE, href)`（ptt_tool.py:117/159），實測 `urljoin(BASE, "//evil.com/x")` → `https://evil.com/x`、`urljoin(BASE, "javascript:alert(1)")` → `javascript:alert(1)`。前提是 ptt.cc 頁面出現惡意 href（實務極低，PTT 的連結是系統產生），但 `/api/article` 都做了白名單，內部路徑漏掉不一致；建議在 `SearchItem` 收錄時就 `if not full_url.startswith("https://www.ptt.cc/bbs/"): continue`。
- ⚠️ **`board` 未做字元約束就串進 URL；擋頁被誤報成「板名錯誤」** — ptt_tool.py:104/147 `f"{BASE}/bbs/{board}/search?q=..."`。host 無法被劫（authority 在前），但打錯板名時 `_get` 每個關鍵字都重試 3 次（sleep 1.5/3/4.5s ≈ 9s），7 個關鍵字要等一分鐘才吐 server.py:339 的「抓不到任何文章，請確認板名是否正確」。且 over18 擋頁（`.r-ent` 選不到）也會走進同一句話 → 誤導。建議 `board` 限 `[A-Za-z0-9_-]{1,30}`（不合就 400），並在 `latest_board_posts` 空結果時檢查頁面是否含 over18 表單，分開報錯。

## 5. 並發 / 持久化

- ✅ **cancel 路徑本身正確** — `job["cancel"]` 只被單一 bool 寫入/讀取，run_task 在三個階段有 checkpoint（314/329/357），InterruptedError 統一收在 419-422。
- ⚠️ **`GET /api/jobs/<id>` 在持有全域鎖的情況下做 json.dumps ＋ socket write** — server.py:550-563，`self._json(...)` 整段在 `with _jobs_lock` 內。結果集大時（150 篇 × 1500 字 preview ≈ 幾百 KB）遇上慢/半斷線的 client，TCP backpressure 會讓寫入卡住，**同時擋住所有 worker thread 的 `job_log()` 與 progress 更新**（291/360）。修法：鎖內只組出 dict 快照，出鎖再 `self._json(snapshot)`。
- ⚠️ **tracks.json 非原子寫入 / 不容忍 0-byte** — 見第 2 項（server.py:129-143）。
- ⚠️ **cancel 只在 checkpoint 生效，UI 無「取消中」回饋** — 取消若落在 `client.search()` 內（最多 3 頁 × 每頁 sleep 0.4s ＋ 網路），要等當前關鍵字跑完才停；index.html:421 送出後按鈕維持原狀、無 disable、無文字變化，使用者會連按。建議送出後把按鈕改成「取消中…」＋disable。
- ⚠️ **`log_message` 覆寫用 `args[1]` 沒檢查長度** — server.py:490-492。stdlib 有單一參數的呼叫點（`http/server.py`: `log_error("Request timed out: %r", e)`）→ 會在錯誤處理中再拋 IndexError。預設 `timeout=None` 下不會觸發（已確認 `BaseHTTPRequestHandler.timeout is None`），但只要哪天加了 timeout 就會炸。改 `if len(args) > 1 and str(args[1]) not in ("200", "204")`。
- ✅ 每個 job 各自 `PTTClient`（server.py:298），`requests.Session` 沒有跨 thread 共用；`/api/article` 也是每次 new（544）。

## 6. Supabase 專案加查

- ✅ **不適用** — 本專案無 `lib/api.js` / `db/migrations/` / `supabase/functions/`，純本機 stdlib HTTP server ＋ 單檔 UI。附帶確認：改動檔案內沒有任何 key/secret/測試帳密（`config.example.json` 只有關鍵字設定），server 綁 `127.0.0.1`（server.py:629）不對外。

---

## 附帶觀察（非 bug）

- `docs/CODE_MAP.md` 小落差：登錄的 `export_results_txt(name, results)` 實際簽名多一個 `note`；新寫的可重用 helper `_word_hit` / `hits_any` / `detect_board` / `parse_days` / `start_job` 尚未登錄（全域規範要求新可重用函式當下登錄）。
- `parse_request` 的板名別名比對用 lower、移除用原字串（server.py:164-166 vs 208-209）→ 大寫輸入殘留。實測「GAY版找feverwill的小說」→ `queries=['GAY版','feverwill的小說']`（板名正確判成 gay，但 GAY版 混進關鍵字）。改 `re.sub(re.escape(board_alias), " ", cleaned, flags=re.I)`。UI 可修正，故只列這裡。
- `parse_list_date` 解析失敗回 None（server.py:242-257），而 347 的過濾是 `days and dt and ...` → **日期不明的文章一律放行**。實測非閏年遇到列表上的 `2/29` 會回 None。目前 sort 會把它們排在最後、date 欄位顯示原始 `M/DD`，可接受，但要意識到「10 天內」不保證。
- `parse_request` 抗壓正常：空字串/純標點/單字/`最近999天`/60k 字（4ms）都回合法 task，`FILLER_WORDS` 有 `re.escape`（215），無 catastrophic backtracking。
- `PTT工具.bat` 本體檢查通過：CRLF 53 行 / LF-only 0、UTF-8 無 BOM、`chcp 65001` 在所有中文輸出之前、`set /p` 預設值 1 可直接 Enter、CLI 分支有 errorlevel 判斷＋pause。唯一缺口是網頁分支缺 pause（B3）。
- 環境提醒：審查時機器上已有一支 `server.py --port 8877` 在跑（PID 22596）。若 Zavier 改完要重測，請先確認舊 process 關掉——否則正好會踩到 B2。

---

## VERDICT

`VERDICT: 17 issues found — fix and re-audit`

**Blocker（3，修完再交付）**
1. **B1** index.html:380-395/318 — 掃描中再按追蹤項「掃描」→ 洩漏輪詢 timer ＋ 孤兒 job 取消不到、PTT 請求翻倍。
2. **B2** server.py:629 — `allow_reuse_address` 讓 Windows 上多個 process 靜默共用同一 port（實測 3 個同時 LISTENING；誤用 8899 時請求被別的程式回答），重複開 bat ＝ 輪詢 404 ＋ 永久轉圈；`main()` 對 bind OSError 無處理。
3. **B3** index.html:397-418（＋PTT工具.bat:32-34）— pollJob 全靜默 catch，斷線/404/淘汰都是無訊息永久轉圈、按鈕鎖死；bat 網頁模式失敗視窗一閃就關，使用者拿不到錯誤訊息。

**Nice-to-have（14）**
取消狀態 UI 未處理且丟棄已抓結果、tracks.json 非原子寫入＋讀失敗靜默回 default、`/api/tracks` lost update、handler 無總 try/except（實測 export 壞 payload 直接斷線無回應）、`/api/run` 零型別驗證（字串 queries 逐字元搜尋、pages/days/delay 無上限）、`days=0` 語意反轉、fillForm/readForm 不能無損來回（週末 note 消失、search_pages/max_body_reads 被寫死）、cancel 未知 job 假成功、item.url 未白名單就 fetch/塞 href、board 未約束＋over18 擋頁誤報成板名錯誤、`/api/jobs` 持鎖寫 socket、cancel 無「取消中」回饋、`log_message` 的 `args[1]`、內文讀取失敗未計數。
（另：CODE_MAP 小落差、大寫板名別名殘留、日期不明文章放行，見「附帶觀察」。）
