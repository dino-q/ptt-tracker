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
- `parse_request` 的板名別名比對用 lower、移除用原字串（server.py:164-166 vs 208-209）→ 大寫輸入殘留。實測「MARVEL版找abc123的文章」→ `queries=['MARVEL版','abc123的文章']`（板名正確判出，但大寫板名字串混進關鍵字）。改 `re.sub(re.escape(board_alias), " ", cleaned, flags=re.I)`。UI 可修正，故只列這裡。
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

---

# 複審 2026-08-22（Angus 第二輪）

範圍：只驗「修法本身有沒有到位、有沒有引入新問題」。方法：讀改動段落 ＋ 對 8877 上跑的修後 server 黑箱實測 ＋ 隔離測 tracks 原子寫入 ＋ 另起 8973 測埠衝突（測完已清）。
先確認測的是新 code：8877 目前的 listener 是 PID 38408、啟動時間 17:00:24，晚於 `server.py`(16:59:55) 與 `web/index.html`(16:59:07) 的 mtime；`GET /` 回來的 HTML 含 `POLL_FAILS` 與「已有掃描進行中」→ Playwright 那兩支測到的確實是修後版本。

## Blocker 驗收

- ✅ **B1 重複啟動掃描** — index.html:385 `if (JOB) return` ＋ 389 `clearInterval(POLL)` ＋ 390 `POLL_FAILS = 0`。timer 洩漏路徑消失（新舊 interval 不會並存），`tests/verify_guard.py` 用行為斷言（出現「已有掃描進行中」、btn-run disabled、原掃描仍完成 N 篇）守住回歸。**但守衛不是同步的，留 R1。**
- ✅ **B2 埠重複綁定** — server.py:667-675 自訂 `Server(allow_reuse_address = False)` ＋ `OSError` 友善中文訊息 ＋ `SystemExit(1)`。實測：
  - 第二個實例 → 「啟動失敗：port 8973 已被占用…（[WinError 10048]…）」＋ exit code 1；
  - `netstat -ano | grep 8973.*LISTENING` 只 1 筆（修前實測同一支開 3 次會有 3 筆 LISTENING）；8877 同樣只 1 筆；
  - 硬砍 process 後**立刻**重綁成功並回 200 → Windows 上沒有引入「關掉要等 TIME_WAIT 才能重開」的回歸。
  - `PTT工具.bat` 網頁分支已補 `set "ERR=%errorlevel%"` ＋ 錯誤提示 ＋ `pause`（CRLF 59 行 / LF-only 0，UTF-8 無 BOM，chcp 仍在中文輸出之前）→ 啟動失敗不再一閃就關。
  - 附註（非問題）：`allow_reuse_address = False` 在 Linux/WSL 上會讓「關掉再馬上開」撞約 60 秒 EADDRINUSE。本專案是 Windows 專用（bat + venv），現在無影響，但哪天搬環境要記得。
- ✅ **B3 輪詢靜默吞沒** — index.html:424-432 連續失敗計數（≥5 次 ≈ 4.5s）或訊息含 `not found|404` 立即 `clearInterval` ＋ 恢復 btn-run/btn-cancel ＋ 顯示「與伺服器失聯…」。實測 `GET /api/jobs/deadbeef` 仍回 `{"error": "job not found"}`（404）→ 正則吃得到，server 關掉時 fetch reject 也會走計數路徑。**顯示位置與判定方式留 R2/R3。**

## 其他修法驗收

- ✅ **handler 總 try/except** — server.py:536-556。實測 `POST /api/export {"results":["abc"]}` 從「連線直接斷、無回應（curl 000）」變成 `500 {"error": "伺服器錯誤：結果格式不正確，沒有可匯出的項目"}`；`export_results_txt` 另加 `isinstance(r, dict)` 過濾（466-469）。**排除 BrokenPipe/ConnectionAborted/ConnectionReset 這三種再送 500 的做法是對的**——那正是「header 已送出」的情境，避免在同一條連線疊第二份 response。
  - 小建議（非阻擋）：那個 ValueError 屬於使用者輸入問題，回 400 比 500 貼切。
- ✅ **tracks.json 原子寫入＋壞檔備份** — server.py:125-152。隔離實測（Python 3.14.2 venv）：首次自動建立、存檔 reload 正常、**無 .tmp 殘留**、`with_suffix(".json.tmp")` 路徑解析正確；壞 JSON 與 0-byte 兩種都會 rename 成 `tracks.json.bak` ＋ console 警告 ＋ 回預設，下次啟動自動重建乾淨檔。`.gitignore` 也一併收了 `tracks.json.bak` / `*.json.tmp`。
- ✅ **/api/jobs 鎖內快照** — server.py:585-599：鎖內只組 dict（`log` 切片複製、`progress` 用 `dict()` 複製），`json.dumps` 與 socket write 都移到鎖外 → 慢速 client 不再擋住 worker 的 job_log/progress。`results` 雖仍是同一個 list 物件，但 worker 是一次性寫入且寫完不再變更（424-427），實務安全。
- ✅ **days 標示** — index.html:226「只看最近幾天（0＝不限）」，語意不再反著猜。
- ✅ **weekend 旗標** — index.html:289/349/364：改由 `fillForm` 記錄 `WEEKEND_FLAG`，開頁載入內建週末追蹤項後直接按「開始掃描」不再把 note 洗掉。**留 R4（黏性）。**
- ✅ **git** — root commit `3a762cb`，working tree clean，`.gitignore` 含 `.venv/ output/ tracks.json tracks.json.bak *.json.tmp config.json tests/screenshots/`；tracks.json 不入庫是對的（預設值在程式碼裡，重建不會掉東西）。現在有可回滾點了。

## 殘留（4 項，皆非阻擋）

- ⚠️ **R1 `runTask` 的守衛不是同步的** — **web/index.html:385 vs 391/394**。`JOB` 與 `btn-run.disabled` 都在 `await post("/api/run")` **之後**才設，空窗期內第二次點擊仍會通過 `if (JOB)` 並建立第二個 job → 舊 job 變成**取消不到的孤兒**（會繼續打 PTT 到跑完）。影響已比修前小（timer 不再洩漏、UI 不會卡死），本機空窗只有數 ms，但 server 正在爬蟲、多條 thread 競爭時會拉長；`verify_guard.py` 測的是人類速度的點擊，測不到這條。2 行修法：進 `try` 前先 `$("btn-run").disabled = true`，並加 `STARTING` 旗標（或先 `JOB = "pending"` 佔位，成功換真 id、失敗清回 null）。
- ⚠️ **R2 停止輪詢後畫面還寫「掃描中」** — **web/index.html:412-432**。失聯、`error`、`cancelled` 三種收尾都沒有隱藏 `#progress`（只有 `showResults()` 會隱藏）。失聯訊息寫進 `#form-error`（在條件卡片內、位於 progress 之上），而使用者剛被 `scrollIntoView` 帶到 progress 區 → 很可能只看到定格的「掃描中」而看不到訊息。建議停止時把同一句話也 append 進 `#log`（它有 `aria-live="polite"` 且就在視線內），或直接隱藏 `#progress`。
- ⚠️ **R3 失聯判定靠錯誤訊息字串** — **web/index.html:427 `/not found|404/i`**，因為 `api()`（294-299）把 `r.status` 丟掉了。目前能命中（server 實測回 `{"error":"job not found"}`），但哪天文案改成中文（「找不到掃描」）就會靜默失效，退回「連續 5 次」才停。建議 `api()` 裡 `const err = new Error(...); err.status = r.status; throw err;`，改用 `e.status === 404` 判斷。
- ⚠️ **R4 `WEEKEND_FLAG` 具黏性** — **web/index.html:349/364**。按過內建週末追蹤項後，使用者手改板名/關鍵字去掃股版，`readForm` 仍送 `weekend: true` → 結果頁掛上不相干的「目標週末…」提示。純顯示層瑕疵（比修好前「提示消失」好），要修就在使用者手動改 `#f-board`/`#f-queries` 時清旗標。

補一則觀察（不計入）：`tracks.json.bak` 每次壞檔都覆蓋舊的（server.py:143）→ 先壞一次（有內容）再壞一次（0-byte）就把可救的版本蓋掉（實測連續兩次後 .bak 內容是第二次的 `{broken2`）。建議 `.bak` 已存在就不覆蓋、或帶時間戳；另外壞檔警告只印在 console，UI 端使用者只會發現「自訂追蹤項不見了」而無提示。

## 仍未修（依協調者決定保留為後續事項，已實測仍在）

`/api/run` 零型別驗證與無上限（實測 `{"queries":"ab"}` 仍回 200 並逐字元跑 2 次搜尋）、cancel 未知 job 回假 `{"ok":true}`（實測 200）、取消時丟棄已抓到的結果、`/api/tracks` read-modify-write lost update、`item.url` 未白名單就 fetch/塞 href、`board` 未做字元約束＋over18 擋頁誤報成板名錯誤、`log_message` 的 `args[1]`、內文讀取失敗未計數、`readForm` 寫死 `search_pages`/`max_body_reads`（追蹤項來回仍會掉值）、大寫板名別名殘留、日期不明文章放行、CODE_MAP 簽名/新 helper 落差。

## VERDICT（複審）

`VERDICT: clean (blockers) — safe to deliver` ｜ blocker 0（B1/B2/B3 三條全部實測驗收通過），殘留 4 項 ⚠️ 全為非阻擋後續事項。
若還有一輪餘裕，最划算的是 **R1（2 行）＋ R2（1 行）**——這兩條正好補完 B1/B3 的最後一哩，其餘可排進下次。

環境交還：我起的測試 process（8973）已全部清掉，`netstat` 8877 只剩你那一支（PID 38408）；探測時誤建的 `output/x_20260822_1706.txt` 已刪除，`git status` clean。測試期間我用直接 API 打了 1 個小 job（Stock 板、2 個單字關鍵字、不讀內文），已自然跑完。

---

# 最終確認 2026-08-22（Angus 第三輪，範圍限 commit a8479cc）

`git show a8479cc` 只動 `web/index.html`（+30/-5）與本報告，無夾帶其他檔案；working tree clean。
先確認測的是新前端：`curl http://127.0.0.1:8877/` 抓回的 HTML 與 `web/index.html` **byte-identical**（`_file()` 每個請求重讀檔案，前端改動即時生效，你的說法成立）；抽出 `<script>` 用 `node --check` 通過（10,164 字，無語法錯）。

- ✅ **R1 啟動競態** — index.html:391-392 先 `JOB = "pending"` ＋ `disabled = true` **才**進 `await`，入口 `if (JOB)`（389）吃得到 truthy 的 `"pending"` → await 空窗期的第二次點擊被同步擋掉；catch（406-410）歸還 `JOB = null` ＋ 恢復按鈕，失敗後不會卡死。`btn-cancel` 加 `JOB !== "pending"`（457）避免打出 `/api/jobs/pending/cancel`（該按鈕在 pending 期間本來就還沒顯示，屬雙保險，正確）。逐路徑檢查 POLL 生命週期：唯一建立點在 398、終止點 413/428 各自 `clearInterval` 且建立前先清（389）→ 不存在「JOB=pending 時還有舊 interval 在跑」的組合。
- ✅ **R2 收尾訊息進使用者視線** — 三種收尾都 append 進 `#log`（432-437、443-445）並捲到底；`#log` 有 `aria-live="polite"` 且就在進度區內。時序正確：三處都在 `clearInterval` 之後才 append，不會被下一輪 `$("log").textContent = j.log.join("\n")`（408）洗掉。（`#progress` 的 h2 仍寫「掃描中」，但 log 已明說「掃描已停止：…」，達到我原本要求的效果。）
- ✅ **R3 改用 status code** — `api()` 掛 `err.status = r.status`（297-301），判定改 `e.status === 404`（441）。網路層失敗（fetch reject）沒有 `status`（undefined）→ 落回「連續 5 次」計數，行為正確；不再受錯誤文案改字影響。
- ✅ **R4 旗標黏性** — `$("f-board")` 的 `input` 監聽清 `WEEKEND_FLAG`（459）。關鍵細節正確：`fillForm` 是程式化賦值（`$("f-board").value = ...`），**不會**觸發 `input` 事件，所以按追蹤項載入條件時旗標不會被自己清掉（且 349 的旗標賦值在 342 之後，即使誤觸也不影響）。
- ✅ 服務端未動（`git show --stat` 只有 index.html），上一輪 B1/B2/B3 與原子寫入等驗收結果繼續有效，無需回歸。

## 觀察（皆非問題，記給下一輪）

- `runTask` 的 catch 沒有 `clearInterval(POLL)`：只有在 `post()` 成功、`setInterval` 已建立、之後的 DOM 呼叫（`scrollIntoView`）拋錯時才會留下孤兒 interval。實務上不會發生，補一行更對稱。
- 同理，`post()` 若回 200 但 body 沒有 `job_id`（本 server 不可能，`/api/run` 永遠帶），`JOB` 會變 `undefined` → 按鈕停在 disabled。要更保險可加 `if (!j.job_id) throw new Error("伺服器未回傳 job_id")`。
- `GET /` 沒有 `Cache-Control` / `ETag` / `Last-Modified`（實測回應標頭只有 Server/Date/Content-Type/Content-Length）。導航（非重新整理）時瀏覽器可能用啟發式快取給舊 HTML；日後改前端後若「看起來沒生效」，先想到這點。加 `Cache-Control: no-store` 一行可免疫。
- `tracks.json.bak` 被第二次壞檔覆蓋（已列後續事項，同意不在本輪處理）。
- R4 只清在 `#f-board`；使用者只改關鍵字不改板名時旗標仍留著（顯示層小瑕疵，可接受）。
- 上一輪列的「仍未修」清單（`/api/run` 型別與上限驗證、cancel 未知 job 假成功、取消時丟棄已抓結果、`item.url` 未白名單、`board` 未約束、`log_message` 的 `args[1]`、內文讀取失敗未計數、`readForm` 寫死 `search_pages`/`max_body_reads`、CODE_MAP 落差等）不變，屬後續事項。

## VERDICT（最終）

`VERDICT: clean — safe to deliver`

blocker 0、⚠️ 0。三輪累計：3 個 blocker（重複啟動掃描的孤兒 job／Windows 埠靜默重複綁定／輪詢靜默吞沒）＋ 4 個殘留全部修完並實測驗收；其餘為不阻擋的後續事項，已在本報告留清單。可以交付 Dino。

---

# v2.1 審查 2026-08-22（Angus）

範圍：v2.0 三個 commit 之後的未 commit 改動（`git diff` ＋ 3 個未追蹤檔），共 7 檔 +731/-49。方法：讀全部 diff ＋ 離線實測（title_sort_key／push_score／classify／快取併發與壞檔／pythonw stdout）＋ 對 8877 實機黑箱測（/api/meta、/api/cache、/api/run 驗證、run_hot 端到端）＋ 讀排程 XML。測完已清掉自己起的東西。

## Pre-flight

- ⚠️ **`data/cache/*.json` 沒有進 `.gitignore`** — `git check-ignore` 確認未被忽略，`git status` 把 `?? data/` 列為待加入。這樣 commit 會把兩份快取（12KB、每 6 小時被改寫、內容是 PTT 抓來的）納入版控，之後每天製造雜訊 diff。`.gitignore` 已經收了 `tracks.json`、`output/`、`*.json.tmp`，快取同理。**commit 前補 `data/cache/`（或整個 `data/`）**，事後補要多一步 `git rm --cached`。
- ✅ diff 範圍與宣稱一致，沒有夾帶無關檔案；ptt_tool.py 的改動都是**向下相容**擴充（`SearchItem.push` 有預設值、`export_author_creations` 新參數都有預設、`tag="[創作]"` 時檔名維持 v1 的 `作者_板_創作.txt`）。

## 你點名的 7 個問題

1. **auto_refresh_loop × UI 手動掃描** — 等待機制**正確**：`refresh_auto_tracks` 持 job 物件參照（server.py:799）而非每次查 JOBS，且 20 個上限的淘汰本來就跳過 `running`，不會踢掉正在等的 job。**但快取寫入會互相打到，見 F1。**（另 server.py:799 `JOBS[jid]` 直取理論上可 KeyError——需要 job 瞬間結束又立刻湧入 20 個新 job，實務不可能，`.get()` 更保險。）
2. **run_job → write_cache_if_track** — **對的**。三個 run_* 都自己 except 全包，所以 write 一定會被呼叫；`write_cache_if_track` 開頭檢查 `status != "done"` → cancelled/error 不寫（server.py:747-752）✓；它自己的 `json.dumps` 與檔案 I/O 都在 try 內（763-767），最壞只 print 一行，不會炸掉 worker thread ✓。
3. **/api/cache 路徑安全** — `_TRACK_ID_RE` 白名單有效。離線實測 `../tracks`、`..%2ftracks`、`a/b`、空字串、`t1.json`、中文全部回 None；實機 `GET /api/cache/../../server.py`（--path-as-is）與 `%2e%2e%2ftracks` 都回 404（`self.path` 未 URL-decode，`%` 本身就不在白名單內）✓。壞檔 → `read_cache` 回 None → 404「尚無快取」，不會 500 也不噴 traceback ✓。**但壞檔不會自癒，見 F2。**
4. **on_progress 拋 InterruptedError** — **乾淨**。`report()` 在 per-article `try` **之外**，所以 `InterruptedError`（OSError 子類）不會被 `except Exception as exc: body = ...` 吃掉,一路傳到 `run_author_export` 的 `except InterruptedError` → status=cancelled；`write_text` 在迴圈之後 → **取消不會留半成品 TXT** ✓。附註：取消只在「每篇之間」生效，`client.search`（最多 20 頁）期間按取消要等搜尋跑完才反應。
5. **loadCache × 進行中 JOB／updateMode 時序** — `updateMode` 時序**正確**（`fillForm` 先填欄位、最後才 `updateMode()`；`display=""` 讓 class 的 flex/grid 復原）。**loadCache 與進行中掃描會互相干擾,見 F5。**
6. **title_sort_key 邊界** — 主用例正確（1/2/10/43 數字序、系列分群、無編號＝第 0 集排最前）；純數字標題與全形括號不會炸（series 變空字串、排最前）。**殘留一個真的排序錯誤,見 F9。**
7. **排程 pythonw** — 實測 `sys.stdout=None` 時 `print()` 是**靜默 no-op、不會拋例外**,所以你手動觸發拿到 exit 0 是可信的；排程 XML 沒有 `<WorkingDirectory>` 也**沒問題**,因為所有路徑都由 `ROOT = Path(__file__).resolve().parent` 推導,與 cwd 無關；`MultipleInstancesPolicy=IgnoreNew` 避免排程自己重疊 ✓、`DisallowStartIfOnBatteries=false` ✓。**但輸出全丟失,見 F8；跨 process 撞同一份快取見 F1。**（另 `LogonType=InteractiveToken`：08:30 沒登入就不會跑,常駐 server 的 6 小時迴圈可補,可接受。）

## Blocker（3）

- ❌ **F1 快取暫存檔名碰撞 → 更新靜默丟失／可能寫壞快取** — **server.py:763** `tmp = cache_path(track_id).with_suffix(".json.tmp")`：同一個 track 的所有寫入者共用**同一個** `{id}.json.tmp`。離線實測兩個 thread 同時寫同一 track：一個以 `[WinError 32] 檔案正由另一個程序使用` 失敗,只印一行「寫入快取失敗」就算了（排程模式沒有 console,見 F8 → 完全無聲）；另一種交錯順序（A 寫入中途 B 以 `w` 模式截斷同一檔,A 再 replace）會把半截 JSON 搬進正式檔 → `read_cache` 回 None → UI 變「尚無快取」。三條真實觸發路徑：
  - (a) **最可能**：bat 啟動 server → `auto_refresh_loop` 立刻補掃過期快取,使用者此時剛開頁、按了同一個追蹤項的「掃描」（UI 有帶 track_id）→ 同 track 兩個 job；
  - (b) 每日 08:30 排程 `--refresh-only` 與常駐 server 的 6 小時迴圈同時掃同一組 track（**兩個 process**,Windows 檔案鎖更容易踩）；
  - (c) 兩個瀏覽器分頁各按同一追蹤項。

  修法：tmp 檔名加唯一後綴（`f"{track_id}.{os.getpid()}.{uuid.uuid4().hex[:6]}.json.tmp"`）；`*.json.tmp` 已在 .gitignore 內,不影響版控。
- ❌ **F2 壞掉／半截的快取 6 小時內不會自我修復** — **server.py:777-783（`cache_age_hours` 只看 mtime）＋ 793（`age < AUTO_REFRESH_HOURS` 就 skip）**。實測把快取寫成 `{broken`：`read_cache`→None、`cache_summary`→None、`cache_age_hours`→**0.0**（檔案很新）→ 自動更新判定「還新」直接跳過 → UI 六小時內一直「尚無快取」、追蹤項名稱不可點,而背景迴圈每 15 分鐘都認為自己沒事。與 F1 疊起來就是「靜默壞掉且不自癒」。一行修法：`if not force and age is not None and age < AUTO_REFRESH_HOURS and read_cache(tid) is not None: continue`。
- ❌ **F3 `data/cache/` 未 gitignore** — 見 Pre-flight。嚴格說是 commit 衛生而非執行期 bug,但**必須在 commit 前處理**,所以放這裡。

## Nice-to-have（6）

- ⚠️ **F4 自動更新失敗沒有退避,每 15 分鐘無限重試** — **server.py:786-815**。job 以 error 收尾就不會寫快取 → `age is None` → 下一個 15 分鐘 tick 又整套重掃（hot-now 一輪 ≈ 熱門排行 + 10 個板列表 = 11+ 次請求）。斷網或被 PTT 擋一整天＝96 輪全套重掃,而且沒有任何可見訊息。建議記下「上次嘗試時間」（記憶體變數或 `{id}.fail` 檔）,失敗後至少等 30 分鐘或指數退避。這條和專案 footer 寫的「請求間有禮貌延遲」是同一個承諾。
- ⚠️ **F5 掃描進行中點追蹤項名稱看快取 → 進度區消失、結果被無預警換掉** — **web/index.html:414 `loadCache` → 587 `showResults()` → 588 `$("progress").style.display = "none"`**。掃描仍在跑（JOB/POLL 沒動,取消鈕還在）,但 log 與進度條被藏起來；等 job 完成,`pollJob` 再呼叫一次 `showResults()`,把使用者正在讀的快取內容**換成新結果並捲動**。修法：`loadCache` 開頭 `if (JOB) { $("form-error").textContent = "掃描進行中,請等它完成或先取消,再看快取。"; return; }`（最省）,或讓 `showResults` 收一個「不要動 progress、不要捲動」的參數。
- ⚠️ **F6 開頁就自動捲到結果區** — **web/index.html:597**（init → `loadCache` → `showResults` → `scrollIntoView({block:"start"})`）。每次開頁畫面都從標題／白話輸入區被捲走,使用者不容易發現上面還有輸入框；Dino 對「捲動被搶」特別敏感（全域偏好有記）。修法：初次載入那一次跳過 `scrollIntoView`。
- ⚠️ **F7 run_hot 全部看板都抓失敗仍回報「成功 0 篇」** — **server.py:646-648**（per-board `except → continue`）,沒有 run_task 裡 `if not seen: raise`（348）那種全失敗判定。PTT 掛掉時 UI 會顯示「沒有符合條件的文章。可以放寬『必含條件』或增加天數再試」——完全誤導。修法：計數失敗板,`if fails and fails == len(boards): raise RuntimeError("所有看板都抓取失敗,請確認網路或稍後再試。")`。
- ⚠️ **F8 排程執行的輸出全部丟失、失敗仍是 exit 0** — `--refresh-only` 走的全是 `print()`（server.py:766/788/807/813）,pythonw 在排程下沒有 console → 進度、「寫入快取失敗」、traceback 全部無處可看,而**快取寫入失敗不會改變 exit code** → 排程紀錄顯示成功、快取其實沒更新,無從察覺。修法：`--refresh-only` 開頭把 stdout/stderr 導向 `data/refresh.log`（或用 logging + RotatingFileHandler）,並在有任何 track 失敗時 `raise SystemExit(1)`。
- ⚠️ **F9 title_sort_key：數字前沒有分隔符時,系列名與集數判定不同步** — **ptt_tool.py:318-327**。`nums` 的 regex 要求數字前有 `(`／`（`／`-`／`－`／`_`／空白／`第`,但 series 的剝除 regex `[\s\-－_]*[\(（]?\d{1,4}[\)）]?\s*$` 不要求 → 實測 `[創作] 未央光年43` 得到 `('未央光年', 0, ...)`,系列對了但集數變 0,**被排到第 1 集之前**。PTT 標題不加空格很常見。修法：用同一個 match 同時取兩者（`m = re.search(r'[\s\-－_]*[\(（]?(\d{1,4})[\)）]?\s*$', base)`,有 m 就 `n=int(m.group(1))`、`series=base[:m.start()]`）。
  附帶兩點（同一支函式,可一併處理）：`未央光年 第3集` 尾端有「集」剝不掉 → 自成一個系列；`Re: [創作] …` 因 `tag in x.title` 是 substring 比對**會被收進 TXT**,且 `strip_ptt_category` 只剝開頭 `[...]` → series 變 `Re:[創作]未央光年`、位置突兀。建議 tag 比對時排除 `title.startswith("Re:")`。

## 已驗證乾淨

- ✅ **實機 run_hot 端到端**：21 篇、`爆`=100 排最前、`board`／`push`／`score`／`cats` 欄位齊全、note 正確（「全站人氣前 10 板…」）；`push_score` 邊界（空→0、`爆`→100、`X1`→-10、`XX`／`X`→-100、`abc`→0、含空白→正確）合理。
- ✅ **`track_id` 非法值不會落地**：`POST /api/run` 帶 `track_id: "../evil"` → 被 sanitize 成 None（server.py:994-996）,實測兩份快取檔 mtime 完全沒變。
- ✅ **`/api/meta` 加的 `cache` 欄位不會污染 tracks.json** — 加在 `load_tracks()` 每次回傳的新副本上,而 `/api/tracks` save 只吃 `{name, task}`。
- ✅ **分類**：`classify` 走 `_word_hit`,短英數詞有字邊界（實測 `kfc` 命中、`kfcx` 不命中）；全沒中→空 list→UI 歸「其他」；完全沒有分類命中時整條頁籤隱藏（index.html:604）。
- ✅ **UI 模式切換**：`intVal` 有 clamp（hot 模式 pages 最低 1）；`readForm` 按 intent 只送該模式需要的欄位；`runTask` 對 hot 免板名、author_export 檢查作者,與 server 端 400 驗證一致（實測 author_export 缺作者 → 400）。
- ✅ **向下相容**：v2.0 舊結果沒有 `push`／`cats`,UI 用 `r.push`／`(r.cats || [])` 都有防守；`SearchItem.push` 帶預設值不影響既有呼叫端；匯出 TXT 缺欄位不會多印分隔符。
- ✅ **測試品質**：`verify_v21.py` 是行為斷言（`0 < n_store < n_all`、點「全部」還原、模式切換欄位顯隱翻轉）,不是存在性斷言；`verify_ui.py` 改用 `btn-run` disabled→enabled 當完成訊號是對的（v2.1 開頁 `#results` 就可見,舊的可見性判定會假通過）,而且掃描 0 篇時 `n > 0` 仍會 fail,沒有引入假陽性。
- ✅ **CODE_MAP 維護到位**（新函式幾乎都登錄、附 🆕 日期、還加了「排程」段）。只差 `cache_age_hours`、`_word_hit` 沒列、`export_results_txt` 簽名少了 `note`（沿用上輪的小落差）。
- ✅ `路徑相依_搬移前必讀.md` 有記排程名稱、pythonw 完整指令與搬移後重建方式。

## VERDICT（v2.1）

`VERDICT: 9 issues found — fix and re-audit`（blocker 3 ／ nice-to-have 6）

最關鍵：**F1 + F2 是同一條鏈**（快取被併發寫壞 → 六小時不自癒 → v2.1 的招牌功能「開頁即看」變成「尚無快取」）,兩處合計約 3 行,建議這輪一起修；**F3 是 commit 前必做**（否則抓來的快取進版控、每天雜訊 diff）。修完只需回測這三點,其餘 6 項可排下一輪。

環境交還：本輪只起了離線 python 測試（隔離在 scratchpad 暫存資料夾,已刪）與對 8877 的 HTTP 探測,沒有起任何長駐 process；探測時經 `/api/run` 跑了 1 個 hot job（10 板各 1 頁,未寫快取）,已自然結束。`data/cache/` 兩份檔案的 mtime 未被我改動。

---

# v2.2 複審 2026-08-22（Angus）

範圍：v2.1 審查後的全部未 commit 改動（10 檔 +1371/-230，含 index.html 全檔重寫）。方法：讀 diff ＋ 離線實測（title_sort_key／快取併發／_refresh_log／article 含留言與 clean_ptt_body 交互）＋ 對 8877 實機黑箱測（/files/ 14 種變形、/api/download 驗證）。測完已清掉自己的暫存資料夾。

## 上輪 9 項處置驗收

- ✅ **F1（快取 tmp 碰撞）部分修好** — server.py:`tmp = CACHE_DIR / f"{track_id}.{os.getpid()}.{uuid4().hex[:6]}.json.tmp"`。**寫壞快取的路徑消失了**（不再共用暫存檔、不會被別人截斷）。但實測 4 個併發寫入者：仍有一個以 `[WinError 5] 存取被拒` 失敗（Windows 上多方同時 `os.replace` 同一個目的檔會撞），**該次更新靜默丟失**，而且**留下孤兒 `.tmp` 永不清理**（實測殘留 `t1.<pid>.<rand>.json.tmp`）。→ 降級為 ⚠️R1，見下。
- ✅ **F2 壞快取視同過期** — `... and age < AUTO_REFRESH_HOURS and read_cache(tid) is not None`（refresh_auto_tracks），六小時凍結問題解除。
- ✅ **F3 `.gitignore` 加 `data/`** — `git status` 已不再列 `?? data/`，快取與 refresh.log 都不會進版控。
- ✅ **F7 run_hot 全失敗會 raise** — `ok_boards` 計數（server.py:641/650/674），不再回報「成功 0 篇」。
- ✅ **F8 排程可觀測** — `_refresh_log()` 隔離實測通過（自動建 data/、UTF-8 中文、附加時間戳）；`--refresh-only` 依 `refresh_auto_tracks()` 回傳值 `raise SystemExit(0 if ok else 1)`。**注意：`data/refresh.log` 目前是空的／不存在**，因為修好後還沒有任何一次排程或過期重掃跑過——排程 08:30 那次是修法之前跑的，等於這條路徑還沒被真實驗證過，明天 08:30 後記得看一眼那個檔有沒有出現。
- ✅ **F9 title_sort_key** — 實測：`未央光年43` → `('未央光年', 43)`（排在 (10) 之後，正確）；`Re:`／`Fw:` 前綴剝除後與本系列同群。殘留無害邊界：`未央光年 第3集` 仍自成系列（尾端「集」剝不掉）、`代碼12345` → `('代碼1', 2345)`，同一標題內部一致，不影響排序穩定性。
- ✅ **F6 開頁搶捲動** — init 結尾只 `switchView("money")`，沒有 scrollIntoView，確認消失。
- ⏸ F4（自動更新失敗無退避）、F5（完成自動切頁蓋掉閱讀中內容）依你決定留下。附註：**F5 在新 IA 下已明顯減輕** — `loadCacheInto` 完全不碰 `#progress`，而 `#progress`／`#results` 都在 `.view` 區塊之外，所以看快取或切頁都不會讓進行中的進度區消失。

## v2.2 新功能：你點名的 5 點

1. **`/files/` 路徑安全 — 過關**。實機 14 種變形全部 404（`../server.py`、`..%2f..%2f`、`%2e%2e%5c`、`..\`、`C:%5CWindows%5Cwin.ini`、`//127.0.0.1/c$/...`、`server.py`、`tracks.json`、`%00.txt`、`xxx.txt%00.png`、不存在檔、空路徑），只有 output/ 內真實 `.txt` 回 200 + `Content-Disposition: attachment; filename*=UTF-8''…`。三層防護的分工正確：`Path(unquote(...)).name` 取 basename（Windows 上 `\` 也算分隔符，所以 `..\` 也被吃掉）、`.lower().endswith(".txt")`、`target.resolve().parent != OUTPUT_DIR.resolve()`。`.TXT` 允許但仍限 output/ 內（Windows FS 大小寫不敏感），可接受。**symlink／junction 逃脫會被 `resolve()` 擋掉**；hardlink 擋不了，但那需要攻擊者已能寫入 output/，屬同一信任邊界，不算洞。
2. **run_download 白名單／上限 — 夠**。`urls` 先過 `isinstance(str) and startswith("https://www.ptt.cc/bbs/")` 再 `[:300]`（順序正確，不會被 300 個垃圾擠掉真網址）；逐篇容錯且把失敗寫進 TXT（不是靜默跳過）；取消只在每篇之間生效、且 `write_text` 在迴圈之後 → **取消不留半成品檔**；`safe_filename(name)` 擋檔名逃脫。殘留兩點見 ⚠️R4／R5。
   **留言與 clean_ptt_body 的交互 — 順序正確，實測證實**：`.push` 在 decompose 之前收集，而字串是在 `text = clean_ptt_body(text)` **之後**才 append。抓一篇真實爆文對照：`with_comments.body.startswith(no_comments.body) == True`（本文 965 字完全相同，之後接 1484 行留言）→ 簽名檔裁切與 `※ 發信站` 切斷**不可能**誤砍留言。另一個更重要的連帶：`run_task` 與 `/api/article` 都走預設 `include_comments=False`，所以留言不會污染 `must_groups` 關鍵字比對與摘要——這點如果反了會造成大量誤判，做對了。
3. **JOB／VIEW_DATA 狀態機 — 正確**。`kind === "download"` 完成時只 `offerDownload`，不動 `VIEW_DATA`、不切頁；非 download 才寫 `VIEW_DATA[view]` 並 `switchView(view)`。失敗路徑齊全：`runTask` 與下載按鈕的 catch 都 `JOB = null; setRunButtons(true)`，`pollJob` 的 error／cancelled／失聯三條都走 `endJob()`（clearInterval + JOB=null + 按鈕恢復）。`pollJob` 開頭 `if (!JOB || JOB === "pending") return` 補上了 pending 期間的空轉。**切頁時進行中 job**：`switchView` 不碰 JOB／POLL，且 `#progress` 在 `.view` 之外 → 進度區跨頁持續可見、job 照跑，完成後自動切回 `JOB_VIEW`。另外「熱門頁只有全站＋預設條件（`!board && min_push===50 && hot_boards===10`）才回寫 hot-now 快取」這個判斷做得對，避免單板掃描汙染每日快取——但省錢頁沒有同樣的保護，見 ⚠️R3。
4. **offerDownload 的 `window.location.href` — 有風險但觸發窄**，見 ⚠️R2。
5. **F1 修法實測** — 見上（部分修好，殘留 ⚠️R1）。

## 殘留（6 項，皆非阻擋）

- ⚠️ **R1 併發 replace 仍會丟更新、且留孤兒 tmp** — write_cache_if_track。實測 4 併發：1 個 `[WinError 5]`，該次更新靜默丟失（只 `print`，pythonw 下無人看見），失敗的 `.tmp` 留在 `data/cache/` 永不刪。修法三件套：per-track `threading.Lock` 序列化同 process、`os.replace` 失敗重試 2 次（間隔 0.2s）、`finally: tmp.unlink(missing_ok=True)`。影響已比 v2.1 小很多（不再寫壞檔；自動更新那條因為 mtime 沒變會在下個 15 分鐘 tick 自癒；手動掃描那條使用者畫面上仍看得到結果），所以列 nice-to-have。
- ⚠️ **R2 `offerDownload` 用 `window.location.href`，遇到非 attachment 回應會把整個 App 導走** — web/index.html:903。`/files/` 的 404 是 `application/json`（實機確認），只要 `job.file` 對應的檔案被手動刪掉／搬走，點「再次下載」或完成時的自動觸發就會把頁面換成 `{"error":"not found"}`，四頁的 `VIEW_DATA` 記憶體狀態一次全失。函式裡已經建好 `<a>` 元素，最省修法：`a.download = file; a.click();`（有 `download` 屬性時非 attachment 回應也走下載而不是導航），或 `fetch` 檢查 `r.ok` 後再用 blob。
- ⚠️ **R3 省錢頁「更新優惠總覽」不論條件都回寫每日快取** — web/index.html:617-618 固定傳 `track_id="lifeismoney-browse"`，但 `f-m-days`／`f-m-pages`（預設 3／6）就在按鈕旁邊可改。使用者改成 days=1、pages=1 掃一次 → 每日快取被較窄的結果覆蓋且 mtime 變新 → **接下來 6 小時「開頁即看」都拿到這份窄結果**。熱門頁已經用 `isDefault` 避免這件事，省錢頁照抄一行即可（`days===3 && pages===6` 才傳 track_id）。
- ⚠️ **R4 run_download 全部失敗仍回報成功** — server.py:736-746：`ok` 為 0 時照樣寫檔、status=done、UI 自動觸發下載一個只有【讀取失敗】清單的 TXT。你這輪已經幫 run_hot 加了全失敗 raise（F7），run_download 應該一致：`if not ok: raise RuntimeError("全部文章都讀取失敗，請確認網路或稍後再試。")`。
- ⚠️ **R5 超過 300 篇靜默截斷** — server.py:697-698 取前 300，但 UI 顯示「共 400 篇」且沒有任何提示（只有 TXT 檔頭寫「共 300 篇」）。建議 UI 在 `CURRENT_LIST.length > 300` 時先提醒，或把截斷資訊寫進 job note。
- ⚠️ **R6 快取寫入失敗不會進 refresh.log、也不影響 exit code** — `write_cache_if_track` 失敗只 `print`，而 `refresh_auto_tracks` 記錄的是 **job status**，所以 refresh.log 會寫 `-> done`、`--refresh-only` 回 0，實際上快取沒更新。修法：write_cache_if_track 失敗時也呼叫 `_refresh_log`，或在 job done 後確認 `read_cache(tid)["updated_at"]` 真的變了才算成功。

補三則觀察（不計入）：`urls` 不去重（重複網址會重抓，CURRENT_LIST 理論上已去重，屬防禦性）；追蹤項的「掃描」按鈕 class 是 `run` 不是 `runbtn`，不會被 `setRunButtons` 停用（功能上仍被 `if (JOB)` 擋住並顯示訊息，只是 affordance 不一致）；含留言的體積 — 實測單篇爆文 965 字 → 50,916 字，300 篇可達數十 MB，`run_download` 全在記憶體組 chunks、`/files/` 也 `read_bytes()` 全量讀，單機桌面沒問題但值得知道。

## 已驗證乾淨（v2.2 新增部分）

- ✅ `POST /api/download` 空 urls → 400；全部非 ptt.cc → job error「沒有可下載的文章網址」（不會靜默產生空檔）。
- ✅ jobs payload 新增 `kind`／`file` 不影響舊欄位；`author_export` 同時回結果清單與 file，UI 兩者都用得到。
- ✅ 舊 `/api/export` 保留但 UI 不再呼叫，沒有死路徑衝突。
- ✅ `CURRENT_LIST` 由 `renderItems` 設定＝畫面上實際顯示（分類＋文字過濾後）的清單，「下載全文」與所見一致；沒有資料的頁面 `#results` 整段隱藏，下載鈕點不到（`!data` 也有守衛）。
- ✅ 結果渲染仍全走 `textContent`，`innerHTML` 只放靜態字串；`export-path` 的連結用 createElement + textContent。
- ✅ verify_guard 改寫成新 IA 的行為斷言（掃描中所有 runbtn 停用、跨頁按鈕也擋、完成後自動切回進階頁），比舊版覆蓋更廣；verify_ui 同步改成白話解析導向 + 完成訊號判定。
- ✅ CODE_MAP 已登錄 `run_download`、`/api/download`、`GET /files/`、`article(include_comments)`，並標註舊 `/api/export` 的現況。

## VERDICT（v2.2）

`VERDICT: clean (blockers) — safe to deliver`

blocker 0（v2.1 的 3 個 blocker 全部修掉並實測驗收，F1 留一個非阻擋殘留），⚠️ 6 項全為後續事項。
若要再挑一輪最划算的：**R3（一行，避免每日快取被窄條件汙染 6 小時）＋ R2（一行，`a.download` 防整個 App 被導走）＋ R1 的 `finally: tmp.unlink`（一行）**。另外提醒明天 08:30 排程跑完後看一眼 `data/refresh.log` 有沒有生出來——F8 的修法目前還沒被真實排程驗證過。

環境交還：本輪只做離線測試（隔離在 scratchpad，已刪）與對 8877 的 HTTP 探測（含 1 篇真實 PTT 文章讀取 ×2，用於驗證留言與本文順序），沒有起任何長駐 process、沒有寫入 `data/` 或 `output/`。
