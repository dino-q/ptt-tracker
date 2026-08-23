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

---

# 熱門 v2 審查 2026-08-22（Angus）

範圍：`f5b5f08`（熱門 v2）＋`beff4f5`（Tor 增量）＋審查中追加的 `5e459cc`（UTC 時區修正）。working tree clean，且 `origin/master..HEAD` 為空＝**三個 commit 都已推送**（所以下一輪每小時 Action 會吃到修好的程式）。
方法：讀三個 commit 的 diff ＋ 離線實測（locale／`_thread_key`／時區算式）＋ 抓 3 篇真實 PTT 文章驗證統計與時間解析 ＋ 對 PTT 實測 `recommend:` 邊界 ＋ **抓線上部署的 `hot.json` 對照**。測完已清乾淨。

## 時區 bug：我獨立重現了，你的修法對症

在收到你 `5e459cc` 的通知之前，我從線上 `https://dino-q.github.io/ptt-tracker/data/hot.json`（updated_at 22:16）抓到同一個症狀並算出根因，兩邊結論一致：

- 線上資料 40 筆中 **16 筆 `per_hour` ≥ 100**，最高 `per_hour=14690.0`（`comments=1469`、發文 08-22 18:54）＝ `comments ÷ 0.1`，正是 `age_h` 撞到 `max(…, 0.1)` 下限的指紋。
- 同一篇在本機（UTC+8）與模擬 runner（UTC）的對照實測：`age_h 3.43h → per_hour 428.1、rising 97.98` vs `age_h 0.10h → per_hour 14690.0、rising 448.2`。**8 小時內的文章全部拿到同一個分母（(0.1+2)^1.6≈3.19）→ 「正在起飛」實際退化成「總留言數」排序**，而 8 小時以上的文章年齡被少算 8 小時 → 反而被高估。
- ✅ 修法驗收：`grep datetime\.now\(\) server.py` **零殘留**；`now_tw()` 回 naive 台灣時間，與 `_parse_article_dt`（PTT 印的也是台灣時間、naive）同一個基準，比較正確；本機 `now_tw()` 與 `datetime.now()` 差 1e-06 秒（＝本機行為完全不變）；模擬 UTC 主機時 `now_tw()` 領先 8.00 小時。`TAIPEI` 在這台 Windows 上實際走 fallback `timezone(UTC+08:00)`（無 tzdata），台灣沒有夏令時間所以與 `ZoneInfo("Asia/Taipei")` 等價。
- ✅ 你問的 `parse_list_date` 交互：`today` 改成台灣今天後**更正確**（PTT 板面的 M/DD 本來就是台灣日期）。舊行為在 Action 的執行窗（台灣 08:07–23:07）剛好沒跨過日界線，所以沒有既存誤判被掩蓋；`dt > today + 1 天 → 視為去年` 的容忍在台灣基準下不變。
- ⚠️ **待確認**：線上 `hot.json` 目前仍是 22:16 那份壞資料（我剛抓的），要等下一次 Action（台灣 23:07）跑完才會換成正確值。請跑完後回頭看一眼 `per_hour` 是否落回合理區間（LIVE 直播文正常會有 200–400／小時，破千就是又壞了）。

## 你點名的 6 點

1. **`recommend:` 邊界 — 實測（Lifeismoney，各 1 頁）**：`recommend:0` → PTT **忽略條件**，回傳含噓文的一般文章（`X2`、空白推文數）；`recommend:-5` → 同樣忽略（回了 X1/X2/X4）；`recommend:999` → 回全爆文，不報錯。所以三種邊界都**不會炸**，但見 ⚠️H4：v2 把 client 端的 `push_score >= min_push` 過濾整個拿掉了，`min_push ≤ 0` 時「熱門」會變成「最近文章」。不存在的板 → `client.search` 走 `_get` 重試 3 次（約 9 秒）後 RuntimeError → 被 per-board `except` 接住並 `job_log`，單板情境會走到 `ok_boards == 0` 的 raise ✓。
2. **`_parse_article_dt` 的 locale — 你的擔心方向對，但目前不會發生，理由與你想的不同**：Python **啟動時不會**呼叫 `setlocale(LC_TIME, ...)`，LC_TIME 保持在 `"C"`，所以 `%a %b` 一律吃英文縮寫，跟 OS 是 zh-TW 或 runner 是 C locale 都無關。實測本機真實文章 `'Sat Aug 22 18:54:13 2026'` → 正常解析成 `2026-08-22 18:54:13`；線上 `hot.json` 的 rising 全是非零值，也反證 ubuntu runner 上解析成功。全 repo 也沒有任何一行 `setlocale`（只有 pip 內部有，跟執行期無關）。
   **但這是一顆一行之遙的地雷**：我實測 `locale.setlocale(locale.LC_TIME, 'Chinese_Taiwan.950')` 或 `setlocale(LC_TIME, '')` 之後，`_parse_article_dt('Sat Aug 22 …')` 直接回 **None**。哪天有人為了數字/日期格式加一行 `setlocale(LC_ALL, '')`，或某個新依賴這麼做，就會全篇 dt=None → rising 全 0、per_hour 消失、排序靜默退化，而**現在沒有任何地方會叫**。→ ⚠️H3。
3. **討論串聚合的代表選擇** — `max(group, key=score)` 的取捨可接受（爆＝100、噓＝負分，所以噓爆原文會讓一篇小推的 Re: 當代表、連結指到回文）；`thread` 篇數有顯示，使用者看得出是討論串。**但誤併是真的**，見 ⚠️H1。
4. **rising 的除零/None** — 乾淨：`max(…, 0.1)` 擋掉除零與負年齡；`dt is None → age_h None → rising 0.0 / per_hour None`；`results.sort(key=lambda r: r.get("rising") or 0)` 對 None 安全。detail 讀取失敗直接 `continue` 的合理性見 ⚠️H2。
5. **Tor 改的 meta 渲染沒有 XSS 面** — 全部走 `document.createElement` ＋ `textContent`，`meta.append("　", span)` 是加文字節點，沒有任何 `innerHTML` 吃資料（`innerHTML` 只用在 `box.innerHTML = ""` 清空與靜態字串）。分類／排序按鈕也是 `textContent`。
6. **hot_cats 分類數量有界** — 每個板固定回 1 個分類，所以頁籤數 ≤ 1（全部）＋ 不重複板數（`hot_boards` UI clamp 上限 20，預設 10），實測線上 9–10 板 → 約 10 顆，不會失控；未對照到的板用板名（線上實際出現 `Badminton`）——中英混排但資訊正確，且 `config.json` 的 `hot_board_categories` 可補。另外 `hot_cats` 永遠回非空 list，所以熱門頁不會出現「其他」頁籤 ✓。

## 殘留（4 項，皆非阻擋；H1／H4 建議這輪順手修）

- ⚠️ **H1 `_thread_key` 不含板名 → 跨板同名標題被併掉、少一篇** — server.py `_thread_key` 只剝 `Re:/Fw:` 與 `[分類]`、去空白轉小寫，而 `threads.setdefault(_thread_key(...))` 也沒有板名前綴。實測：`[閒聊] 今日閒聊` 與 `[問卦] 今日閒聊` → 同一個 key `'今日閒聊'`；`[新聞] 台積電大漲` 與 `[心得] 台積電大漲` → 同一 key。合起來的後果是**不同看板的同名文章（各板的每日閒聊、`[公告] 板規`、同一則新聞被多板轉貼）會被併成一串，只留推文數最高那篇**，其餘從結果裡靜默消失——正好是 Dino 這次抱怨的「某板缺席」同一類症狀。一行修法：`threads.setdefault(f"{c['board']}|{_thread_key(c['title'])}", ...)`（真要跨板聚合再另議，但至少要是刻意的）。
- ⚠️ **H2 detail 讀取失敗 → 整篇消失** — run_hot 的統計迴圈 `except → continue`，前 40 名候選只要有一篇 fetch 失敗（40 次請求，PTT 偶發 429/超時很正常）就從結果裡不見了，只有 job log 留一行。建議保留該篇（`comments=0`、`rising` 用 `score` 當備援排序值）或在 `note` 加「N 篇未取得留言統計」，別讓「進了前 40 卻消失」變成無聲事件。
- ⚠️ **H3 缺少「時間全數解析失敗」的守門** — 這正是時區 bug 只能靠 Dino 看線上截圖才抓到的原因：程式對「age 全部撞下限」「dt 全部 None」完全沒有自覺。建議兩層：(a) run_hot 統計 `dt is None` 與 `age_h <= 0.1` 的篇數，超過一半就 `job_log` 警告（本機與線上都看得到）；(b) `scripts/build_site.py` 在「rising 全 0」或「per_hour 中位數 > 500」時 `sys.exit(1)`，讓 Action 紅燈而不是安靜發佈壞資料。搭配 H3 也順手把 `_parse_article_dt` 改成不依賴 locale（regex ＋ 月份對照表，5 行），把第 2 點那顆地雷一起拆掉。
- ⚠️ **H4 `min_push` 完全託付給 PTT 的 `recommend:` 語法** — v2 移除了 v1 的 `if score < min_push: continue`，正確性 100% 依賴 PTT 端過濾。實測 `recommend:0`／`recommend:-5` PTT 直接忽略條件 → 直接打 `/api/run`（UI 有 clamp、API 沒有）傳 0 或負值，「熱門文章」就變成「最近文章」而毫無警訊。兩行硬化：`min_push = max(1, int(task.get("min_push", 30)))`，並在收候選時保留 `push_score(it.push) >= min_push`（`push` 空白或無法解析時放行），這樣 PTT 哪天改語法也只會少收、不會混入冷文。

補五則觀察（不計入）：結果被 `max_detail` 截到 40 篇但 `note` 沒說明（使用者看到「共 40 篇」不知是上限）；`sortable` 由當前 list 推導，文字過濾到 0 筆時排序控制項會整組消失再出現（閃動）；`push_summary` 會把 `.push.warning`（例「檔案過大」提示列）算成一則 `→`，超長文的 total 差 1；`ptt_tool.py` 仍有 3 處 naive `datetime.now()`（406 匯出檔頭、487/494 週末優惠 CLI）——只有作者匯出的檔頭時間會在 UTC 主機顯示 UTC，屬顯示層，CLI 只在本機跑不受影響；`note += f"；預設依衝火速度排序…"` 是沒有佔位符的 f-string（無害）。

## 已驗證乾淨

- ✅ `push_summary` 單迴圈同時做統計與留言收集，`include_comments=False` 也會統計（run_hot 需要），`Optional[dict]=None` 預設維持向下相容；真實文章實測 `{'推': 782, '噓': 0, '→': 687, 'total': 1469, 'users': 184}`，與頁面相符。
- ✅ 候選階段有 `seen` 去重（同一 URL 不會因跨板搜尋重複計入）、`days` 過濾、`max_posts=60`／板上限，總請求量有界（10 板 × 2 頁搜尋 ＋ 40 篇詳讀 ≈ 60 次請求／輪，delay 0.4 秒仍在禮貌範圍）。
- ✅ 兩層迴圈都有 `job["cancel"]` 檢查；per-board 失敗只記 log 並 `continue`，`ok_boards == 0` 仍會 raise（v2.2 的 F7 修法沒有被這次重寫弄掉）。
- ✅ 排序切換：`[...list].sort()` 對副本排序，不會弄亂 `VIEW_DATA` 原始資料；`switchView` 重設 `SORT="rising"`；`list.some(r => r.rising !== undefined)` 讓省錢頁不顯示排序控制項。
- ✅ 分類頁籤比較器（canon 優先、其餘按篇數）具傳遞性，不會有排序不穩定；`hot_cats` 與省錢的 `classify` 兩套標籤互不干擾。
- ✅ 內建 `hot-now` task 已換成新欄位（`search_pages`／`max_detail`／`min_push: 30`），`parse_request` 的熱門分支同步更新，沒有留下讀不到的舊 `scan_latest_pages` 路徑。

## VERDICT（熱門 v2）

`VERDICT: clean (blockers) — safe to deliver`

blocker 0（時區那條是真 bug，但 `5e459cc` 已修、已推、我獨立驗證修法對症），⚠️ 4 項皆非阻擋。
最划算的下一步：**H1 一行（板名進 thread key，止住「某板缺席」的第二個成因）＋ H4 兩行（min_push 下限與 client 端複驗）＋ H3 的守門**（這輪的教訓就是「時間算錯了沒人喊」，補一個會叫的哨兵比再修一次划算）。另外請在台灣 23:07 那輪 Action 跑完後，回頭確認線上 `per_hour` 已回到合理區間。

環境交還：只做離線測試與唯讀 HTTP 探測（PTT 5 次請求：3 篇文章 ＋ 2 次 recommend 邊界搜尋；線上 hot.json 1 次），沒有起長駐 process、沒有寫入 `data/`／`output/`、scratchpad 已清空。

---

# 熱門 v2 最終確認 2026-08-22（Angus，範圍限 commit b0a3114）

`git show b0a3114 --stat`：只動 `server.py`／`scripts/build_site.py`／`web/index.html`／`site/index.html`／本報告，無夾帶；working tree clean、`origin/master..HEAD` 為空＝**已推送**（下輪 Action 生效）。

- ✅ **H1 討論串 key 帶板名** — `threads.setdefault(f"{c['board']}|{_thread_key(c['title'])}", …)`，正是處方。八卦 5→7 篇的實證與「跨板同名不再互相吃掉」一致。
- ✅ **H4 min_push 夾下限＋候選複驗** — `max(1, int(...))` ＋ 收集時 `push_score(it.push) < min_push → skip`。**實測不會誤殺**：`recommend:30` 對 Gossiping／C_Chat 各 20 篇，`push` 空白 0 篇、`push_score < 30` 0 篇 → 正常運作下複驗一篇都不會丟。（唯一殘留可能：PTT 哪天在搜尋結果不渲染 `.nrec`，空白會被算 0 而全數 skip；要更保險可加 `if it.push.strip() and push_score(...) < min_push`。優先度低，記著就好。）
- ✅ **H2 讀取失敗保留該篇** — `results.append({**c, …, "rising": 0.0})` ＋ `note` 標「N 篇未取得留言統計」。前端相容性確認：`r.comments != null` 對 undefined 成立 → meta 不印留言欄；`comments`／`ts` 排序都 `|| 0` → 這些項自然沉底，不會插到前面。
- ✅ **H3 雙層哨兵** — run_hot：`dt_fail > len(results)/2` 時 job_log 警告；build_site：`rising` 全 0 或 `per_hour` 中位數 > 2000 → `SystemExit` 讓 Action 紅燈。取樣集 `stats = [... if r.get("comments") is not None]` **正確排除了 H2 的無統計項**（否則它們的 rising=0 會把哨兵誤觸）。
- ✅ **locale 防雷有效** — 實測 `setlocale(LC_TIME, 'Chinese_Taiwan.950')` 下新解析器仍正確回 `2026-08-22 18:54:13`（舊 strptime 在同條件下回 None）；壞輸入 `''`／`None`／`Sat Xyz …`／`Wed Feb 30 …`（ValueError）／`garbage`／缺秒數 全部回 None，不拋例外。regex 不會誤把星期當月份（`Sat` 後面不是數字，引擎自然前進到 `Aug`）。
- ✅ **「最新」排序** — `data-sort="time"` ＋ `r.ts || 0`，web／site 兩檔一致；`ts` 只用於排序不顯示，所以雖然 `naive_taipei.timestamp()` 在 UTC 主機上的絕對 epoch 會差 8 小時，**同一批都用同一方式計算，順序正確** ✓。

## 兩則記給未來（不影響本次交付）

- `ts` 不是真 epoch（在非台灣時區主機上偏 8 小時）。**日後若要做「3 小時前」這種相對時間顯示，千萬不要用 `Date.now() - ts*1000`**，否則線上版會再犯一次這次的時區事故；要顯示就在後端算好字串或改存帶 tz 的 ISO 字串。
- build_site 哨兵在「40 篇全部讀取失敗」時會因為 `stats` 為空而整組跳過（`if stats and …`），變成發佈一份完全沒有數字的清單。加一行 `if not stats: raise SystemExit("全部文章都沒有留言統計，拒絕發佈")` 就補滿。
- 顯示層小落差：H2 保留項的 `date` 沿用候選階段的 `%Y-%m-%d`，有統計的項是 `%m-%d %H:%M`，同一份清單會出現兩種日期格式。

## VERDICT（最終）

`VERDICT: clean — safe to deliver`

H1／H2／H3／H4 與 locale 五項全部照處方修正並實測驗收，新增的「最新」排序無回歸、無 XSS 面、與失敗保留項相容。blocker 0、⚠️ 0（上面兩則屬未來提醒，不計入）。
本輪熱門 v2 的完整結論：時區事故已修並推送、缺席的兩個成因（快板熱文沉深頁→recommend 搜尋、跨板同名誤併→key 帶板名）都堵住、時間計算壞掉現在會出聲（job log ＋ Action 紅燈）。剩下的唯一人工確認點還是那個：台灣 23:07 之後看一眼線上 `per_hour` 是否落回合理區間。

環境交還：本輪只做離線解析測試與 2 次 PTT 搜尋（各 1 頁）唯讀探測，沒有起長駐 process、沒有寫入 `data/`／`output/`；scratchpad 內我的檔案已刪（其餘 `fill_*.py`／`test_hot_v2.py` 不是我的，未動）。

---

# 批次 234 審查 2026-08-22（Angus）

範圍：`9952fea`（7 檔 +119/-49）。working tree clean、`origin/master..HEAD` 為空＝已推送。
方法：讀 diff ＋ 追鎖序與 CPython json 編碼行為 ＋ 抓**線上實際部署的 JSON** 量測體積／new 比例／摘要長度 ＋ grep 殘留呼叫。

## 先結掉上一輪的待確認項

線上 `hot.json`（updated_at 22:45，時區修好後的第一批）：**`per_hour` max=379.5、中位=24.8、min=2.3、>2000 者 0 筆**（事故當時 max=14690）。rising 前五名的 per_hour 依序 379.5／251.2／198.8／164.5／144.8，與「LIVE 直播文 200–400／小時」的預期吻合 → **時區修法在生產環境確認生效**，這條可以關掉了。

## 你點名的 5 點

1. **`write_cache_if_track` 新鎖序 — 安全，但有一個顯示層時序瑕疵**
   - 結構正確的地方：`read_cache()` 的檔案 I/O 已在**鎖外**（維持 v2.1 的修法，沒有回頭把 I/O 塞進全域鎖）；無巢狀取鎖 → 無 deadlock；`_TRACK_ID_RE` 檢查提前到讀檔前。
   - **會不會讀到「標了一半」／拋例外：不會。** `/api/jobs` 的快照雖然共用同一個 `job["results"]` list 物件、`json.dumps` 在鎖外執行，但 `_json()` 用的是預設參數（`indent=None`、`default=None`、`sort_keys=False`），CPython 會走 **C 編碼器 `c_make_encoder`**（`ensure_ascii=False` 不影響選擇），整趟編碼不釋放 GIL，其他 Python thread 無法插進去改 dict → 既不會 `dictionary changed size during iteration`，也不會出現半標記的 payload。**但這是靠 CPython 實作細節保證的**：哪天有人為了好讀在 `_json()` 加上 `indent=2`，就會退回純 Python 編碼器（逐項 yield，會被插隊），那時這個競態就真的存在。免疫成本很低：GET 快照改 `[dict(r) for r in job["results"]]`（淺拷貝每個項目）即可，建議順手加上。
   - ⚠️ **真正找到的問題是時序不是競態**：標記發生在 `status="done"` **之後**（run_* 先寫 done，run_job 才呼叫 write_cache_if_track，中間還夾一次 `read_cache` 的檔案 I/O）。若前端那 900ms 的輪詢剛好落在這幾毫秒的窗裡，它拿到的是 **status=done 但沒有 new 標記**的結果，寫進 `VIEW_DATA` 後就 `endJob()` 停止輪詢 → **這次掃描的「新」徽章不會出現，要重新整理或改點快取才看得到**。機率低（毫秒 vs 900ms）但確定存在。修法方向：把標記移到 status 翻成 done 之前（例如 run_job 先算好 new 再讓 run_* 收尾），或前端在追蹤項掃描完成後改讀一次 `/api/cache/<id>`。
2. **`fetch_old` 的壞資料路徑 — 兩種都安全**：Pages 回 **404** → `urlopen` 拋 `HTTPError`（OSError 子類）→ 被 `except Exception` 接住回 None；回 **200 但是 HTML**（自訂 404 頁）→ `json.loads` 拋 `JSONDecodeError` → 同樣回 None；timeout 15s 也一樣。首次部署／斷網 → None → `mark_new_results` 直接 return（不標）、`fill_previews` 全部視為新文（受 budget 保護）✓。
   ⚠️ 殘留一種：JSON 合法但**不是 dict**（例如檔案被寫成 `[]`）→ `(old or {}).get("results")` 對 list 呼叫 `.get` 會 `AttributeError` → build_site 整個炸掉、Action 紅燈。是 fail-loud 不是靜默壞資料，可接受；但一行 `if not isinstance(old, dict): return None` 就免疫，建議補。
   `fill_previews` 本體乾淨：budget 只計「實際抓取」不計沿用（請求量硬上限 40）；抓失敗 `pass` 後該篇沒有 preview，而 `old_prev` 只收「有 preview」的項目 → **下一輪會自動重試**（自癒）；client 延遲建立；900 字截斷有實測（線上最長 913＝900＋截短提示，40/40 與 36/36 都在界內）。
3. **體積量級 — 不需要處理**。實測：線上 `hot.json` 53.9KB（加摘要前約 3–4KB）、`money.json` 29.9KB；本機 `/api/cache/hot-now` 目前 15.5KB（下一次 hot 掃描帶摘要後約 40–50KB）。摘要中位長度 hot 481 字、money 196 字。Pages 有 gzip，實際傳輸約 1/4；一份 PTT 網頁本身就比這大。`/api/jobs` 完成時的一次性 payload 同步變大（約 50KB）也無妨——注意 `results` 只在 `status=="done"` 才送，掃描中的輪詢 payload 沒變重，這點原設計就對了。
4. **`/api/export` 殘留 — 程式面乾淨，文件面有一處要修**。`grep` 全 repo：`server.py:1086` 是移除註解、`docs/CODE_MAP.md:71` 已標「已移除」——都正確。**但 `docs/CODE_MAP.md:49` 還把 `export_results_txt(name, results)` 列為可沿用函式**。依全域規則「寫新程式前先查 CODE_MAP、預設沿用既有實作」，這一行等於給下一個 agent 埋一個「呼叫不存在的函式」的陷阱。順手刪掉或照 71 行的樣式劃掉。UI（web／site）、tests、README 都沒有殘留呼叫 ✓。
5. **`new` 語意 — 我的判斷：維持 url diff，不要加狀態，但把標籤講清楚（並可加一行年齡護欄）**
   - 省錢頁：清單本來就是「最近 3 天的貼文」，url diff＝真的新貼文 ✓ 語意正確。
   - 熱門頁：清單是「前 40 名排行榜」，所以 url diff 的正確讀法是**「新進榜」**而不是「新發文」；掉出再回榜會被再標一次。我認為**可接受**，理由是：(a) 每筆旁邊就有發文時間，使用者能自己判斷；(b) 實測稀疏度健康——線上 22:45 那批 hot 只有 **1/40（2%）** 標新、money **0/36**，徽章沒有淹掉版面，作為「這輪有什麼變化」的提示是有效的；(c) 加時間窗會引入狀態或誤殺（半夜低流量時可能整輪無新）。
   - 建議只做兩件低成本的事：熱門頁把 title/tooltip 寫成「新進榜」與省錢的「新文章」區分；若還想殺掉「三天前的舊文回榜也標新」這種誤導，用手上已有的欄位加一行即可（`r.get("ts")` 在 24 小時內才標）。
   - 另外我確認了**不會累積**：`mark_new_results` 只從舊資料取 `url` 集合，舊檔裡的 `new: true` 不會回流；新結果每輪都是乾淨重建 ✓。
   - 小提醒：`fetch_old` 抓的是 Pages CDN（有 `max-age`），偶爾可能拿到再上一輪的快照 → 同一篇的徽章可能多掛一輪。純顯示層，不必處理，知道就好。

## 已驗證乾淨（其他）

- ✅ `run_hot` 帶出 preview 是**零額外請求**（就在既有的 `client.article` 之後做字串處理），截斷規則與 web 版一致；H2 的「讀取失敗保留項」因為沒進過文章頁所以沒有 preview——**site 版用 `if (r.preview)` 包住整組摘要按鈕**，不會出現點了沒反應的死按鈕；web 版則是照舊按需打 `/api/article`，兩邊都對。
- ✅ 徽章渲染兩檔都是 `document.createElement` ＋ `badge.textContent = "新"`（靜態字串，且資料值一律走 textContent）→ 無 XSS 面。
- ✅ `mark_new_results` 本身：`if not old_results: return`（首輪不全標）、只認 `r.get("url")` 為真的項目、只加 `new=True` 不刪不改其他欄位 → 對舊快取／舊線上 JSON 完全向下相容（沒有 `new` 欄位的資料只是不顯示徽章）。
- ✅ build_site 呼叫順序合理：`mark_new` 用「還沒補摘要」的結果比對 url（與摘要無關），`fill_previews` 再補；hot 不呼叫 `fill_previews`（摘要已在掃描時取得），沒有重複爬取。
- ✅ 移除 `export_results_txt` 沒有動到 `/api/download`／`run_download` 這條現行下載路徑；`safe_filename` 仍被 run_download 與作者匯出使用（不是孤兒函式）。
- ✅ `ptt_tool.run_natural_language` 只加註解、零行為變更（v1 CLI 凍結宣告與 CODE_MAP 一致）。

## VERDICT（批次 234）

`VERDICT: clean (blockers) — safe to deliver`

blocker 0；⚠️ 4 項全屬 polish／文件層：**CODE_MAP:49 的 `export_results_txt` 幽靈條目（建議這輪順手刪，它會誤導下一個 agent）**、new 徽章在「剛跑完那一次」可能因毫秒級時序沒出現、`fetch_old` 對非 dict JSON 缺 `isinstance` 護欄、熱門徽章語意建議標成「新進榜」。另附一則預防性建議：`_json()` 若日後加 `indent`，請同時把 `/api/jobs` 的 results 改成淺拷貝快照，否則現在靠 C 編碼器不釋放 GIL 撐住的那個競態會真的浮出來。

環境交還：本輪全部唯讀——3 次線上 JSON 讀取 ＋ 1 次本機 `/api/cache`，沒有對 PTT 發任何請求、沒有起 process、沒有寫入 `data/`／`output/`；scratchpad 我的暫存檔已刪。

---

# 瀏覽控制批次審查 2026-08-23（Angus）

範圍：`370089c`（5 檔 +284/-19）。working tree clean、`origin/master..HEAD` 為空＝已推送。
方法：讀全部 diff ＋ 用**本機真實快取（money 84 篇／hot 40 篇）與線上部署 JSON** 重跑前端日曆日篩選算式 ＋ ts 公式等價性實測 ＋ 檢查兩版 UI 一致性。全程唯讀。

## 先關兩個舊追蹤項

- ✅ **F8 排程可觀測性（v2.2 遺留）** — `data/refresh.log` 已有 5 筆真實紀錄，含 `08:30:10` 與 `08:30:57` 兩筆 `-> done`，與 `hot-now.json` 的 08:30 mtime 對得上 → 生產環境驗收完成，跟催關閉。
- ✅ **上輪「ts 非真 epoch」備忘** — 本輪改成真 epoch，且我在**線上部署資料**上驗到位：hot 的 `date` 欄 `08-23 06:43` 與 `ts` 換回台灣時間**完全相符**（updated_at 11:24，即 UTC runner 產出）→ `dt.replace(tzinfo=TAIPEI)` 在 UTC 主機上行為正確。備忘作廢。

## 你點名的 5 點

1. **ts 語意變更的一致性 — 沒有會炸的路徑，混存也不會誤篩**
   - 本機（UTC+8）新舊公式**數值完全相等**（實測 `naive.timestamp() - aware.timestamp() = 0.0`），所以本機任何舊快取與新資料混用都無差異。`hot-now` 本機快取（08:30）40/40 有 ts 且與 `date` 欄相符，**不會被日曆日 cutoff 誤篩**。
   - 舊公式若殘存於 UTC 主機產出的資料，其 ts 比真 epoch **多 8 小時（偏未來）** → 前端 `ts*1000 >= cutoff` 只會**多顯示**、不可能誤殺；而線上 JSON 每小時重生，實測目前線上兩支都已是新公式 → 這個窗已經關閉。
   - Python 端只有 run_task／run_hot 兩處產出 ts，沒有其他消費者（`grep` 確認），不存在「舊 ts 進到後端計算」的路徑。
   - 附帶確認一個容易忽略的精度問題：**scan 的 ts 來自板面 M/DD，值是當日 00:00**（實測 `1787328000 → 2026-08-22 00:00`），正好對上「日曆日」語意 → 不會出現「同一天的文章被切掉」的邊界誤差。hot 的 ts 來自文章頁，精確到秒。
2. **置頂免除過濾的互動 — 兩件要判斷，我的意見如下**
   - ⚠️ **文字搜尋不該免除**（見 P2）。天數／分類免除是合理的（那正是置頂的目的），但搜尋「全家」時，不相關的置頂項仍固定顯示在最上方，很容易被讀成「這也是命中結果」。
   - ⚠️ **計數會不一致**（見 P3）：tabs 用 `base = dayFiltered(all)`（不含置頂例外），而 `共 X 篇` 用 `[...pinned, ...list].length`（含）→ 置頂項落在天數視窗外時會出現「全部 15」但「共 16 篇」。語意上可解釋（頁籤＝視窗內分佈、清單＝視窗內＋置頂），但使用者會問。
   - **`CURRENT_LIST` 含置頂項我認為是對的**：它等於「畫面上看到的清單」，「下載全文」與所見一致，這個語意比「只下載過濾結果」更好解釋，不用改。
3. **localStorage 例外處理 — 完整**。`loadPins`／`savePins` 兩邊都有 try/catch，隱私模式或停用儲存時退化成純記憶體 Set，不會拋例外。無上限也不會退化（每筆約 60 bytes、`Set.has` O(1)，離 5MB 上限極遠）。唯一小缺口：置頂的文章若掉出 10 天資料集，那個 pin 會變成「看不到也清不掉」（沒有管理入口），殘留只是 localStorage 裡的字串，影響可忽略。
4. **10 天視窗的爬取量 — 可接受，且 body_reads 確認為 0**
   - browse task 實測配置 `read_body:false` + `max_body_reads:0` + `must_groups:[]` → 走 else 分支且兩層條件都擋住讀內文 → **body_reads 恆 0**；14 頁列表拿到 84 篇，`max_posts=400` 不成為瓶頸（14 頁 × 約 20 篇）。本機 money 掃描＝**14 次請求／輪**（原 6 頁）。
   - 線上一輪總量：money 14 ＋ `fill_previews` ≤60 ＋ hot（20 搜尋＋40 詳讀）≈ **135 次請求／小時**，delay 0.4 秒仍在禮貌範圍；Actions 執行時間約多 1 分鐘。首輪 84 篇摘要在 budget 60 下會剩 24 篇 → 因為 `old_prev` 只收「有 preview」的項，下一輪會自動補完（自癒），預算調到 60 是對的。
5. **本地午夜語意 — 可接受，我記錄如下**：cutoff 用瀏覽者本地午夜，而文章日期是台灣日期，所以非台灣時區的訪客在跨日附近會有幾小時錯位（例如 UTC 訪客的「今天」比台灣晚 8 小時開始）。公開站以台灣讀者為主，**不必修**；真要精確就把 cutoff 改成固定 UTC+8 的午夜（一行）。另附一則同類邊界：`86400e3` 是固定日長，若訪客所在時區當天有 DST 轉換，cutoff 會偏 1 小時（台灣無 DST，不受影響）。

## 需要決定的一件事（我認為交付前該講）

- ⚠️ **P1 預設 3 天顯示 15 篇，比改版前實際看到的量少一半以上；而且觸發這個批次的 8/19 那篇，在預設狀態下仍然看不到。**
  線上與本機實測完全一致：`DAYS=1/3/5/10 → 0/15/36/80 篇`。改版前的伺服器端 `days=3` 用的是 `(today-dt).days > 3`，實際含 4 個日曆日、約 36 篇——**也就是舊的預設視覺量等於新的「5 天」**。而 8/19 的文章在 8/23 需要 `DAYS≥5`（cutoff＝午夜−4 天）才會進來，預設 3 天的 cutoff 是 8/21。
  資料層確實修好了（10 天超集、80 篇都在快取裡，不會再消失）✓，但**如果 Dino 打開預設畫面找那篇 8/19 全家文，他還是看不到**，體感會是「還沒修好」。這是產品決定不是缺陷，我的建議：預設改「5 天」（同時回復舊的可見量、也覆蓋這次的抱怨案例），或交付時明確告知「往前找請按 5／10 天」。
- ⚠️ **P4 熱門頁的「5 天／10 天」是 no-op**：伺服器端 hot task 只抓 `days: 2`，實測線上 hot 在 3／5／10 天都是 40 篇（1 天＝8 篇）。控制項看起來可用卻沒有效果，建議熱門頁只留 1／3 天，或把 hot 的抓取視窗與選項對齊。

## 已驗證乾淨

- ✅ 兩版 UI 邏輯一致：`dayFiltered` 算式、`!r.ts` 保留、PINS 前置、tabs 用 `base`、to-top 門檻 600px、轉傳三段 fallback 都相同。
- ✅ 轉傳的三段 fallback 正確：`navigator.share` 的 `AbortError` 靜默 return（不會誤觸複製）；`navigator.clipboard` 在 `http://127.0.0.1` 也算 secure context，所以本機版可用；最後 `prompt` 兜底。
- ✅ 天數切換會同時 `renderTabs()` 與 `applyFilters()` → 分類篇數跟著視窗變，不會出現「頁籤數字對不上清單」的殘影；切換功能頁時 `DAYS` 重設為 3、按鈕 active 狀態同步復原。
- ✅ `#day-filter` 只在「資料裡有 ts」時顯示 → 舊快取（無 ts）不會出現一個按了沒反應的控制項。
- ✅ 新增的置頂／轉傳按鈕與徽章全部 `createElement` ＋ `textContent`（無 XSS 面）；`div.insertBefore(actions, div.querySelector(".preview"))` 在沒有 preview 時 `querySelector` 回 `null` → 等同 append，合法不會拋錯。
- ✅ 上輪我建議的徽章語意標示已實作：`badge.title` 依 `r.board` 分成「新進榜（上次更新時不在榜上）」與「上次更新後的新文章」。
- ✅ `#to-top` 是固定懸浮鈕，與 Dino「不喜歡懸浮蓋內容」的既有偏好相反，但 commit message 註明是他本次明確要求 → 屬刻意例外，我只記錄（44px、右下角、捲 600px 後才出現，不擋正文）。
- ✅ `max_posts` 改吃 task 參數後仍有預設值 150，其他 scan task（進階頁、weekend-coffee）行為不變。

## VERDICT（瀏覽控制批次）

`VERDICT: clean (blockers) — safe to deliver`

工程面 blocker 0：ts 語意變更沒有留下會炸或會誤篩的路徑（本機新舊等值、線上已全數新公式、fail-open）、localStorage 有防護、爬取量與 body_reads 都在預期內、兩版 UI 一致。
但**交付前請先決定 P1**（預設 3 天＝15 篇、8/19 那篇要按 5 天才看得到）——這批次的起因就是 Dino 覺得文章不見了，資料雖然救回來了，預設畫面卻不會讓他看到那篇；改預設 5 天或明確告知，二選一即可。其餘 P2（置頂不該免除文字搜尋）、P3（置頂使 tabs 與總數不一致）、P4（熱門頁 5／10 天無效果）都是一行級的 polish。

環境交還：全程唯讀——2 次線上 JSON、1 次本機 `/api/meta`、其餘為離線算式驗證；沒有對 PTT 發任何請求、沒有起 process、沒有寫入 `data/`／`output/`；scratchpad 暫存檔已刪。

---

# 熱門 v4 審查 2026-08-23（Angus）

範圍：`d91ed88`（7 檔 +238/-152，run_hot 全重寫）。working tree clean、`origin/master..HEAD` 為空＝已推送。
方法：讀全文（不只 diff，v4 是重寫）＋ 用**本機 hot-now 快取 80 篇與線上已部署 hot.json 80 篇**做結構與分佈驗證 ＋ 用當下 hotboards 的 nuser 重算板級門檻逐篇核對 ＋ 追探索/收錄/沿用三段的資料流。全程唯讀（1 次 hotboards、2 次線上 JSON、0 次 PTT 文章請求）。

## 資料層實測（先給體檢數字）

- 本機快取（17:52）與線上（17:54）都是 80 篇、**80/80 有 accepted_at**、**feed 嚴格依 accepted_at 遞減**（逐項比對通過）、`ts == accepted_at` 80/80 ✓。
- 分佈：40 篇是本輪新收錄（同一個 accepted_at），另 40 篇是舊快取 bootstrap（accepted_at＝原 ts，散落 11:31–16:50）。
- **板級門檻逐篇核對：低於門檻者 0 篇**（新收錄 40/40 過線；bootstrap 沿用 40/40 也剛好都過線，因為它們原本就是 v3 的高留言前 40）→ 沒有 bootstrap 髒資料。
- 留言數 min/中位/max ＝ 84／223／1469；per_hour 中位 12.2、max 545.5、>2000 者 0 → build_site 哨兵不會誤觸。
- 板分佈 12 板（NBA 13／Gossiping 11／Baseball 11／…／Lifeismoney 2）→ 無每板限額，與 moptt 實證一致 ✓。
- 線上 hot.json 體積 **123KB**（80 篇含摘要）——這是下面談 200 上限時的成本基準。

## 你點名的 7 點

1. **登記簿 × 200 上限 — 這裡有真問題，見 ❌V1。**
2. **carried 不過濾板（全站掃描時）— 我認為是對的，不要改。** feed 的語意是「最近變熱的文章」，不是「現在還在熱門板上的文章」。若因為 Kaohsiung 今天掉出人氣前 10 就把昨天收錄的高雄文從 feed 抽掉，等於重演「文章莫名消失」那條抱怨；而且看板膠囊已經讓使用者能自己隱藏不想看的板。指定板／自選板掃描時才過濾（`scan_specific`）也合理，那是使用者明確要求的視野。
3. **accepted_at 繼承鏈 — 兩條路格式一致、且不會被污染。** 線上：`build_site` 只把 `fetch_old("hot")` 的 results 灌進 `hot_task["prev_results"]`；本機：`read_cache(track_id)`，而 track_id 只在 UI 判定「全站＋預設條件」時才帶 `hot-now`。money／weekend 走的是 `run_task`，**根本不讀 prev_results**，`mark_new_results` 的 money 比對用的是 `fetch_old("money")` → 兩套資料互不相通 ✓。使用者自訂的 hot 追蹤項會用自己的 track_id 快取當登記簿，天然隔離 ✓。另外 `rr.pop("new", None)` 有把舊徽章清掉，不會讓「新」跨輪殘留 ✓。
4. **舊格式 bootstrap — 正確。** `rr.setdefault("accepted_at", rr.get("ts") or now_epoch)`：2015 舊文若在舊快取裡，accepted_at 會是 2015 的 epoch → 被 `cutoff = now - 10 天` 直接排掉 ✓；ts 缺失才退成 now（fail-open，最多多留 10 天）。實測 bootstrap 的 40 篇 accepted_at 都落在今天，沒有異常值。
5. **UI — 兩點都沒問題。** ① `SORT` 預設 `time` 對 money 無感：money 的項沒有 `rising` 欄位 → `sortable=false` → 排序控制項隱藏且完全不套排序，維持伺服器順序 ✓。② **bf-toggle 閉包沒有舊資料風險**：`renderBoardFilter(results)` 在每次 render 都會被重新呼叫（line 1018 `renderBoardFilter(dayBase)`），toggle 的 handler 是那一次 render 新建的閉包；點 toggle 只重畫膠囊列、用的正是當前畫面那份資料，資料更新後也會經由 render 重建 handler ✓。
6. **探索只走 `recommend:`（正推）→ 高留言低推的爆噓文探索不到。我的嚴重度判斷：中高，建議這輪或下輪補。** `recommend:N` 只認淨推，所以「300 則留言、20 推、150 噓」這種文章永遠進不了候選，而它正是八卦／政黑最典型的熱門型態——也正是 moptt 用 hits（瀏覽量）會抓到、我們用留言數代理**應該**抓到的那一類。目前的 `push_score(it.push) < disc` 複驗也擋不住這個缺口（它們本來就沒出現在搜尋結果裡）。低成本補法：探索階段 union 一頁 `latest_board_posts(b, pages=1)`，把 nrec 是 `爆`／`XX` 或 `abs(push_score) >= disc` 的項也丟進驗證池（每輪多 10 次請求，約 +5 秒），收錄判準仍是實測總留言數，機制不變。
7. **build_site 哨兵與 v4 相容性 — 不會誤觸，但守門力被架構削弱，見 ⚠️V2。**

## ❌ V1（blocker 級設計缺陷）：200 上限與「收錄登記簿」共用同一份資料，凍結語意會被自己吃掉

- 現狀：`registry` 只來自上一輪的 `results`，而 `results` 被 `[:200]` 截斷 → **被上限擠掉的舊收錄，下一輪就不在登記簿裡了**。而 `if it.url in registry: continue` 是唯一的「已收錄」判斷，所以那些文章會被重新探索、重新驗證、拿到**全新的 accepted_at**，跳回 feed 最前面，還會被 `mark_new_results` 標上「新」（它們不在上一版部署 JSON 裡）。
- 為什麼會踩到（量化）：`max_detail=40` 是每輪上限，本輪就滿載 40 篇。探索面每輪約 10 板 × 2 頁 ≈ 400 篇候選，登記簿只有 200 個位子 → 穩態下永遠有大量「未登記但在搜尋結果裡」的文章可收。線上每小時跑一輪，只要每輪新收錄 20–40 篇，**登記簿 5–10 輪就滿，之後每輪擠掉最舊的 20–40 篇**：
  - 快板（Gossiping／NBA）的舊文已滑出搜尋前 40 → 直接**從 feed 消失**，「保留 10 天」實際只剩 5–10 小時；
  - 慢板（Kaohsiung／Lifeismoney／Elephants，實測都在 feed 裡）的文章仍在 `recommend:` 前 40 → **被重複收錄、重新蓋上今天的時間與「新」徽章**，同一篇每幾小時回鍋一次。
- 這條同時打到 v4 的核心賣點（收錄後凍結、依收錄時間排序）與 Dino 最在意的那件事（文章不要莫名消失／不要莫名重複）。
- 修法（不必動機制、只動持久化）：**把「登記簿」與「顯示上限」拆開**。快取／site JSON 多存一個精簡 ledger（例如 `{"ledger": {url: accepted_at}}`，10 天約 500–1000 筆、50–100KB 以內），`registry` 從 ledger 建、`results` 才套 200 上限；或直接把上限提高到「10 天預期量」（實測 80 篇＝123KB，200 篇約 300KB、gzip 後約 75KB，1000 篇就太重，所以我建議走 ledger）。
- 驗證方式（不用等 10 天）：連續看 3–5 輪部署，(a) `carried` 是否卡在 ~160 而 `new` 一直維持 ~40；(b) 有沒有任何 url 的 accepted_at 往前跳。任一成立就是這條。

## ⚠️ 其他

- ⚠️ **V2 H3 哨兵被「凍結」架構削弱** — `scripts/build_site.py` 的哨兵是 `all((r.get("rising") or 0) == 0 for r in stats)`，但 v4 的 carried 會帶著上次算好的 rising（非 0）跨輪存活 → 只要 feed 裡有沿用項，**「rising 全 0」這個條件就永遠不成立**，等於時間解析壞掉時不會再讓 Action 紅燈（這正是 8/22 時區事故的唯一守門）。修法：哨兵只看本輪新收錄（`accepted_at == max(accepted_at)` 或另外回傳一個 `accepted_new` 計數／清單），對它們做「rising 全 0」與 per_hour 中位數檢查。run_hot 內的 `dt_fail > len(accepted_new)/2` 警告寫得對（分母已經是新收錄），把哨兵對齊成同一個口徑就好。
- ⚠️ **V3 探索盲區（爆噓文）** — 見上第 6 點，嚴重度中高。
- ⚠️ **V4 文案與實際不符** — note 與 UI 欄位都寫「保留 10 天 / feed 保留天數（依收錄時間）」，但在 V1 未修的情況下實際深度是數小時。修 V1 後文案自然成立；若決定不修 V1，文案要改成「最多 200 篇」。
- 附記（不計入）：`hotboards(top=100)` 每輪多 1 次請求換來 nuser 分級，划算；`comment_threshold` 對不在熱門榜的板回落 50 是合理的保守值；指定板／自選板掃描不帶 track_id → 不會寫進 hot-now 快取、也不會污染登記簿（實測 UI 只在預設條件下傳 track_id）✓。

## 已驗證乾淨

- ✅ 探索→聚合→驗證→沿用四段的取消檢查、per-board `except → continue`、`ok_boards == 0 → raise` 都保留；`_thread_key` 仍帶板名（v2.2 的 H1 修法沒被重寫弄掉）。
- ✅ 收錄判準是**實抓文章的總留言數**（不是搜尋結果的推文數），與 docs/moptt_algorithm.md 的結論一致；`recommend:` 只當預過濾且門檻用 `thr//3` 夾 10–50，方向（寧可多撈進驗證）正確。
- ✅ 未過門檻的候選只是「本輪不收錄」，沒有寫進任何黑名單 → 之後留言變多會自然過線（持續觀測語意正確，不會誤殺）。
- ✅ `ts = accepted_at` 與前端「天數篩選／最新熱門」語意一致（都是「何時變熱」）；`carried` 也統一 `r["ts"] = r["accepted_at"]`，不會出現兩種語意混在同一份 feed。
- ✅ 天數篩選在 accepted_at 語意下自洽：DAYS=1＝今天被收錄的；熱門頁開放 1/3/5/10 現在是真的有效（不再是上輪那個 no-op，因為 feed 深度來自登記簿而非 days=2 的抓取視窗）。
- ✅ 移除 `min_push` 參數與 UI 欄位後沒有殘留讀取點（run_hot 全文已無 min_push）。
- ✅ 前端新增的膠囊／收折按鈕全部 `createElement` + `textContent`；`localStorage` 讀寫都有 try/catch（`ptt_board_filter_open`、`ptt_board_excl`、`ptt_pins`）。

## VERDICT（熱門 v4）

`VERDICT: 4 issues found — fix and re-audit`（blocker 1／nice-to-have 3）

機制複製的忠實度與資料正確性我給高分：收錄制、板級門檻、feed 全序、無每板限額、統計凍結、舊文回鍋都對得上研究文件，實測 80 篇零違規。**但 ❌V1（登記簿與 200 顯示上限共用同一份資料）會在幾小時內把「收錄後凍結」這個核心語意吃掉**，症狀是快板文章提早消失、慢板文章反覆回鍋重標「新」——正好命中 Dino 最敏感的那兩件事，所以我把它列為 blocker：修法只是「多存一個 url→accepted_at 的 ledger」，不動演算法。順帶把 ⚠️V2（哨兵改看本輪新收錄）一起補，否則 8/22 那類時間事故的守門在 v4 之後其實已經失效。

環境交還：全程唯讀（1 次 hotboards、2 次線上 JSON、本機快取檔讀取），沒有對 PTT 發文章請求、沒有起 process、沒有寫入 `data/`／`output/`；scratchpad 暫存檔已刪。

---

# 熱門 v4 修正確認 2026-08-23（Angus，範圍限 commit 2dad28a）

`git show 2dad28a --stat`：只動 `server.py`／`scripts/build_site.py`／本報告，無夾帶。方法：讀 diff ＋ 用**本機 152 篇快取與線上已部署 120 篇**驗證 ledger／收錄分組／噓文覆蓋率／天數篩選實際效果。全程唯讀（1 次線上 JSON、讀本機快取）。

## 逐項驗收

- ✅ **V1（blocker）真的修好了** — ledger 獨立持久化鏈完整：run_hot 讀 `task["prev_ledger"]` 或快取的 `ledger` 欄位 → 探索 skip 改查 `it.url in ledger` → 本輪新收錄併入 → **與 carried 用同一個 `cutoff` 修剪** → 存回 `job["ledger"]`（鎖內）→ `write_cache_if_track` 與 build_site 的 hot.json 都帶出去。你問的第①點：**cutoff 一致、不會誤刪 carried 需要的鍵**——`carried` 的條件是 `accepted_at >= cutoff`、ledger 修剪條件是 `a >= cutoff`，同一個述詞，不可能出現「carried 還在但 ledger 已刪」；`registry` 也用 `setdefault` 回填 ledger，舊快取沒有 ledger 欄位時能自我 bootstrap。**不會無限成長**（每輪修剪，上限＝10 天內的收錄數）。實測：本機 feed 152／ledger 152 筆、`ledger 早於 feed 最舊者 = 0`（顯示上限還沒咬到）、線上 120／120 且 `ledger` 欄位已部署 ✓。accepted_at 零漂移我也從分組看到了（見下）。
- ✅ **V2 哨兵對齊** — `fresh = [r for r in stats if r.get("accepted_at") == acc_max]`，正是處方。小提醒（不必改）：某輪**新收錄為 0** 時，`acc_max` 會落在最新一批 carried 上 → 哨兵那輪實際在檢查凍結的舊統計，等於沒有守門；要做到滴水不漏就讓 run_hot 另外回傳 `accepted_new` 的計數／清單給哨兵用。
- ⚠️ **V3 只修了一半，實測沒有生效** — 候選閘門改成 `abs(push_score) >= disc` 且 union 了 `latest_board_posts` 一頁 ✓，但**排序沒改**：`reps.sort(key=lambda c: c["score"], reverse=True)` 之後 `probe = reps[:max_detail]`（40）。X 噓爆文的 `score` 是負值（X1→−10、XX→−100），會排在**所有正推候選之後**，在 40 篇的驗證預算下永遠進不了 probe。實測佐證：本機 152 篇與線上 120 篇裡，**`push` 以 X 開頭者都是 0 篇**，而 `爆` 有 54／55 篇——盲區還在原地。修法兩行：`rep = max(group, key=lambda c: abs(c["score"]))` 與 `reps.sort(key=lambda c: abs(c["score"]), reverse=True)`（順帶也修掉「噓爆原文被小推 Re: 搶走代表位」的老問題）。你問的第②點順便回答：**abs() 對 recommend 結果（全正推）確實無副作用**（`push_score("")=0` 仍會被擋掉），它只是讓補掃的噓文「進得了候選池」，但目前進不了驗證池。
- ⚠️ **V4 文案在 V1 修好後仍然不是事實** — 200 顯示上限現在會先咬到，而且**已經開始咬**：目前 feed 跨度 53.7 小時就有 152 篇，前端天數篩選在這份資料上的效果是 `DAYS=1/3/5/10 → 129/152/152/152`，也就是**「5 天」「10 天」兩個頁籤已經是 no-op**。收錄速率實測 40 → 39 → 33 篇／輪，即使收斂到每輪 10–20 篇，10 天也遠超 200 篇 → feed 實際只會是「最近 200 篇被收錄的文章」（線上每小時一輪約 6–10 小時、本機 6 小時一輪約 1.5 天）。建議二選一：把 note／`f-h-days` 標籤改成「最近 200 篇熱門收錄」並讓熱門頁只留 1／3 天；或把顯示上限拉大（成本參考：本機 152 篇＝246KB、線上 120 篇＝194KB，摘要佔絕大部分——想拉大上限又不想變重，可以只給最新 80 篇留 preview）。
  附帶一件必須講清楚的語意：ledger 現在會阻止「被上限擠出者」重新收錄（這正是 V1 要的），所以**掉出 200 名的文章會在 10 天內永久消失、不再回鍋**。這是比「反覆回鍋標新」更好的取捨，但它仍然是一種「文章會不見」——Dino 對這件事敏感，交付時最好一句話講明「熱門頁是最近 200 篇收錄，往前找請用日期或去省錢頁」。

## 你問的第③點：39→33 算不算收斂曲線

**還不能算，這兩輪相隔只有 36 秒。** 精確分組顯示 `18:03:07 → 39 篇`、`18:03:43 → 33 篇`（加上 `17:52:00 → 40 篇` 那輪 bootstrap），是同一批 backlog 被連續兩次消化，−15% 只說明「池子還很深」。可估的池子大小：每板 recommend 2 頁（≈40）＋補掃 1 頁（≤30）≈70 筆 × 12 板 ≈ 840 個 URL，而每輪驗證上限 40 篇 → 還要十幾輪才會摸到底。我的預期曲線是：**接下來數輪維持 30–40／輪，等 ledger 覆蓋到搜尋可見窗（估 400–800 筆）之後才會掉到「真正新變熱」的速率（線上可能每輪個位數到十幾篇）**。判斷收斂的訊號建議看兩個：ledger 筆數是否趨平、以及每輪新收錄是否掉到 15 以下；在那之前 feed 都會被 200 上限截斷（見 ⚠️V4）。

## 已驗證乾淨（本次改動面）

- ✅ ledger 型別防禦：`prev_ledger` 非 dict 直接忽略、逐筆 `float()` 包 try/except（壞資料不會炸整輪）。
- ✅ `job["ledger"]` 在鎖內設定；`write_cache_if_track` 用 `if job.get("ledger")` 才寫入 → money／weekend（run_task，不產生 ledger）完全不受影響，不會塞空欄位。
- ✅ build_site 兩件事都對：`hot_task["prev_ledger"] = (old_hot or {}).get("ledger")`（首次部署沒有 ledger 時為 None → 走 registry bootstrap）、輸出 `"ledger": hot.get("ledger") or {}`；線上已實際部署（120 筆）✓。
- ✅ 補掃的 `latest_board_posts(b, pages=1, max_posts=30)` 包在自己的 try/except 裡，抓失敗只是 `extra=[]`，不會讓整個板的探索失敗；成本＝每輪多 12 次請求（與我上輪估的 +10 一致）。
- ✅ 收錄判準仍是「實抓文章總留言數 ≥ 板級門檻」，V3 的閘門只影響誰進驗證池，不影響收錄標準 ✓。
- 附記：ledger 目前 11KB，但它只有 build_site 需要，卻跟著 hot.json 送給每個訪客；等 ledger 長到 800–1300 筆會是 60–95KB 的純浪費。建議之後拆成 `data/hot_ledger.json`（頁面不抓、只有 builder 讀），一併緩解 ⚠️V4 的體積壓力。

## VERDICT（v4 修正確認）

`VERDICT: 2 issues found — fix and re-audit`（blocker 0／nice-to-have 2）

**V1 這個 blocker 確實修掉了**（ledger 與顯示上限分離、cutoff 一致、鏈路兩端都持久化、線上已生效），V2 也照處方到位。剩下兩件都是一行到一段的收尾：**⚠️V3 排序沒跟著改 → 噓爆文實測 0 篇進榜，盲區還在**（`abs()` 要用在 `reps.sort` 與 `rep = max` 上）；**⚠️V4 文案／天數頁籤與 200 上限的事實不符（5 天、10 天已經是 no-op）**，並且要向 Dino 說明「掉出 200 名會在 10 天內不再回鍋」這個新語意。這兩項都不阻擋現在的交付。

環境交還：全程唯讀（1 次線上 JSON、讀本機快取檔），沒有對 PTT 發任何請求、沒有起 process、沒有寫入 `data/`／`output/`；scratchpad 暫存檔已刪。

---

# 熱門 v4 收尾確認 2026-08-23（Angus，範圍限 commit 0b86c1e）

`git show 0b86c1e --stat`：只動 `server.py`／`scripts/build_site.py`／本報告；working tree clean、已推送。實測一次本機快取（182 篇）＋一次 `/api/cache`。

- ✅ **V3 機制已完整開門（程式碼層確認）** — 兩處都改了：`rep = max(group, key=lambda c: abs(c["score"]))`、`reps.sort(key=lambda c: abs(c["score"]), reverse=True)`。X 噓爆文現在能與高推文競爭同一個 40 篇驗證額度，「噓爆原文被小推 Re: 搶代表位」也一併解掉。**對正推路徑零副作用**（abs 對正數是恆等，正推候選之間的相對順序不變）。本輪 X 文仍 0 篇我同意不必等自然樣本——收錄判準仍是實測留言數 ≥ 板級門檻，機制正確即可；backlog 消化完（每輪新收錄掉到十幾篇）之後若連幾天仍 0 篇，再回頭看板級門檻對噓文型態是否過高就好。
- ✅ **V4 誠實化到位** — 實測：feed 182 篇（上限 400）、**帶摘要的索引正好是 0–119、120 之後 0 篇**（切齊）、`coverage 2.24 天` 與 note 文字「feed 目前涵蓋約 2.2 天（上限 400 篇／10 天）」一致、feed 嚴格依 accepted_at 遞減。ledger 拆檔正確：`hot.json` 的 payload 已不含 ledger、另寫 `hot_ledger.json`，`fetch_old("hot_ledger")` 有 fallback 到舊的內嵌格式（過渡輪不會掉登記簿）。**本機快取檔仍保留 ledger（182 筆）**所以登記簿沒斷，而 `/api/cache` 回應 keys 只有 `track_id/updated_at/results/note`（實測已剝除）→ 前端不再下載內部狀態。
  附記（不必改）：`results[120:]` 的 `preview = ""` 會就地改到 registry 裡的同一批物件，所以掉出 120 名後摘要永久消失——但 feed 只會往下掉不會往上升，且本機版仍可點「顯示摘要」現抓、靜態站則直接不顯示按鈕，兩邊都優雅。
- ✅ **V2 補強正確** — `job["fresh_urls"]`（鎖內設定）→ build_site `fresh = [r for r in stats if r["url"] in fresh_set]`。零新收錄的那一輪 `fresh` 為空 → `if fresh and …` 直接跳過，既不會誤觸也不會拿 carried 的舊統計假裝守門，語意乾淨。
- ✅ **收斂曲線開始出現**：每輪新收錄 40 → 39 → 33 → **30**，單調下降，與我上輪預估的 backlog 消化路徑一致。ledger 182 筆、feed 182 篇（上限未咬到）。

## VERDICT（收尾）

`VERDICT: clean — safe to deliver`

blocker 0、⚠️ 0。V1（登記簿與顯示上限分離）、V2（哨兵精準圈定本輪新收錄）、V3（abs 排序讓噓爆文進得了驗證池）、V4（上限 400／摘要瘦身／coverage 誠實揭露／ledger 拆檔）四項全部實測驗收通過，可以收案。
唯一保留的觀察不是缺陷而是待觀察值：backlog 消化完之後的穩態收錄速率會決定 feed 實際涵蓋幾天（現在 2.2 天），note 已經會自己說實話，所以不需要再回審。

環境交還：全程唯讀（讀本機快取檔、1 次 `/api/cache`），沒有對 PTT 發任何請求、沒有起 process、沒有寫入 `data/`／`output/`；scratchpad 我的暫存檔已刪。

---

# 閱讀器審查 2026-08-23（Angus，範圍限 commit 22420ad）

6 檔 +322/-43；working tree clean、已推送。方法：讀全部 diff ＋ **用 node 跑 13 組對抗字串驗 URL 正則**（與瀏覽器同引擎語意）＋ article_id 邊界電池 ＋ 實抓 1 篇文章驗 payload 與 TXT 格式 ＋ 檢查 `site/data` 的 git 追蹤狀態。對 PTT 只發 1 次請求。

## 你點名的 5 點

1. **XSS 面 — 乾淨，我用對抗案例逐一驗過。** 正則 `/(https?:\/\/[^\s]+)/g` 的任何 match **必然以 `http://` 或 `https://` 開頭**（13 組案例全部成立）：`javascript:alert(1)`／`data:text/html,<script>…`／`vbscript:`／前置控制字元 `javascript:` **全部無 match**（原樣當文字節點輸出）；`httpsx://evil.com/a.jpg` 無 match。`http://a.com/x.jpg"onerror=alert(1)` 會 match 成 LINK，但值是用 `a.href = u` **屬性賦值**、整條路徑沒有任何 `innerHTML`（`container.textContent = ""` ＋ `createElement`）→ 引號不會被當 HTML 解析，**onerror 無法被注入** ✓。imgur 判斷 `/^https?:\/\/i\.imgur\.com\//i` 的點有轉義且要求結尾斜線，所以 `https://i.imgur.com.evil.com/a` 只會變成連結、不會變 `<img>` ✓。
   兩則附帶觀察（都不是漏洞）：`xhttps://evil.com/a.jpg` 會抓到子字串 `https://evil.com/a.jpg` 並渲染成圖（子字串匹配的必然結果，後果僅是對圖床發一個 GET，已用 `referrerpolicy=no-referrer` 降低外洩）；`HTTPS://EVIL.com/a.png`（大寫 scheme）**不會**被連結化（正則沒有 `i` flag）——想支援就加 `i`，加了也不會有 XSS 風險（仍要求字面 scheme）。
2. **article_id 碰撞／路徑安全 — 安全。** 主分支 `/bbs/(board)/(file).html` 的兩段都不可能含 `/`，所以 aid 永遠不含斜線或反斜線（電池測試 9 組全部確認）→ 檔名與前端 fetch 路徑都跳不出 `data/articles/`。唯一「起首是點」的情況是 `https://www.ptt.cc/bbs/../M.123.html → '.._M.123'`，但 (a) 結果清單的 url 一律是真實 PTT 文章連結、不會長這樣；(b) 就算真的出現，`.._M.123.json` 是**單一檔名**而非路徑段，URL 正規化的 dot-segment 移除只處理剛好等於 `.` 或 `..` 的段，所以不會往上跳 ✓。fallback 分支（`\W+ → _`）確有碰撞（`a?x=1`／`a?x-1`／`a?x_1`／`a#x=1` 全部 → `a_x_1`），但那個分支只有「不符 PTT 文章網址格式」才會走到，實務不可觸及；要保險就 `aid.lstrip(".")` 或加一道 `^[\w.-]{1,60}$` 白名單。
3. **/api/article payload 與 PTT 量級 — 大小沒問題，但沒有節流，見 ⚠️R1。** 實測一篇 139 則留言的文章：body 6664 字＋139 則 → JSON **27KB**；以上限推算（body 12000＋300 則留言）最壞約 40–60KB，本機直連無所謂。
4. **build 端補抓與 stale 檔 — 你的推理正確，我確認了關鍵前提。** `.gitignore:11` 有 `site/data/` → Actions 的 checkout **不含任何舊文章檔** → 每輪 artifact 只包含本輪 `write_articles` 實際寫出的清單 → **掉出維護窗的舊檔自然消失，不會累積** ✓（也因此 CDN 搬運 `fetch_old_article` 是唯一的跨輪保存手段，這個設計是自洽的）。覆蓋率數學也對：維護清單＝money 85 ＋ hot 最新 200 ≈ 285 篇，每輪 fresh ≈ 30–40（掃描時已抓，零額外請求）＋ 搬運（不耗 PTT）＋ 補抓 40 → 未覆蓋部分每輪 −40，本機目前 66 檔，約 5–6 輪後飽和、之後補抓自然歸零 ✓。carry_cap 320 > 285 所以不會卡住搬運。**但搬運的計數語意有個坑，見 ⚠️R2。**
5. **批次下載 TXT 無迴歸 — 實測確認（我原本懷疑有）。** 我以為 `uid + content` 會吃掉 `": "` 分隔符，實抓驗證後是我看錯：`content` 變數保留原始的 `": …"`，`lstrip(": ")[:500]` 只作用在 `comment_list` 的 content 欄位。實際 TXT 行仍是 `推 warriors30: 所以是給兩個版本喔 有點玄 08/22 00:43`，**格式與 500 字截斷都與舊版一致**，`include_comments` 語意不變 ✓。

## ⚠️ 兩則（皆非阻擋）

- ⚠️ **R1 `/api/article` 沒有併發／速率保護** — 每個請求 `PTTClient(delay=0.2)` 都是新 client，而 `_get` 的 `time.sleep(delay)` 是**抓完之後**才睡，所以跨請求之間毫無節流；ThreadingHTTPServer 又是一請求一 thread → 使用者連點 10–20 篇「閱讀全文」就是 10–20 個幾乎同時對 PTT 的請求。UI 有 `pre.dataset.filled` 快取（同一篇不會重抓）✓，人手速度也有限，所以我列 nice-to-have；但這是整個功能唯一對 PTT 無上限的路徑，建議加一個全域 `threading.Semaphore(2)` 或共用 client＋lock，成本一行。
- ⚠️ **R2 `write_articles` 的搬運計數只算成功、不算嘗試** — `if pkg is None and carried < carry_cap: pkg = fetch_old_article(aid); if pkg is not None: carried += 1`：CDN 回 404（該篇從未烘焙過）時 `carried` 不增加 → 守門條件恆為真 → **最壞情況每輪對 Pages 發出約 285 次 GET，每次 timeout 10 秒**。覆蓋率還沒長滿的現在（66/285）就有兩百多次 404 嘗試；若哪天 Pages 慢或掛掉，一次 build 會從 3 分鐘變成最多 ~47 分鐘（不會失敗、只會很久，Action 6 小時上限內不會被砍，所以不會有人發現）。修法：把計數改成「嘗試數」（`attempts += 1` 放在 `if pkg is None and attempts < cap` 之前）或把 timeout 從 10 秒降到 3–5 秒，兩者都是一行。

## 已驗證乾淨（其他）

- ✅ `comment_list` 與 `push_summary`、TXT 文字三者同一個 `.push` 迴圈收集，且都在 `decompose` 之前 → 零額外請求、也不會被簽名檔裁切影響（沿用上輪已驗證的順序）。
- ✅ `Article.comment_list: Optional[list] = None` 有預設值 → 舊呼叫端與舊快取完全向下相容；`article_package` 對 `art.comment_list` 用 `or []` 防 None。
- ✅ run_hot 在收錄驗證時把已抓的 `art` 存進 `job["articles"]`（鎖內設定），確實是零額外請求；build_site 再 `fresh_articles.update(hot.get("articles") or {})` 併入 → 資料流沒有重複抓取。
- ✅ 閱讀器渲染全程 `createElement`／`textContent`（留言的 tag／user／content／time、樓層 `1F` 起算、推噓配色都是 class 切換），沒有任何 `innerHTML` 吃資料。
- ✅ 讀取失敗有優雅退路：本機版 `catch` 會顯示「摘要＋全文讀取失敗：原因」；線上版無烘焙檔（404）退回摘要＋原文連結 → 不會出現空白展開區。
- ✅ `fetch_old_article` 有 `isinstance(d, dict)` 檢查（Pages 回非 JSON／HTML 時回 None，不會炸整輪）。
- ✅ `write_articles` 有 `seen` 去重（money 與 hot 清單若有同一篇不會寫兩次）、`aid` 為空直接跳過。

## VERDICT（閱讀器）

`VERDICT: clean (blockers) — safe to deliver`

blocker 0。最需要確認的 XSS 面我用對抗字串逐一驗過：**任何被渲染成 `img.src`／`a.href` 的字串必然以 http(s):// 開頭，且全程屬性賦值無 innerHTML → 無注入面**；`article_id` 跳不出目錄；TXT 路徑實測無迴歸；stale 文章檔會因 `site/data/` 被 gitignore 而自然清除（你的推理正確）。兩則 ⚠️ 都是「還沒爆但會爆」型的收尾：R1（連點多篇沒有節流）與 R2（CDN 搬運只算成功次數，Pages 出問題時 build 會拖到 40 分鐘級），各一行可修，不阻擋交付。

環境交還：對 PTT 只發 1 次請求（驗 payload 與 TXT 格式），其餘為離線正則／id 電池與本機檔案讀取；沒有起 process、沒有寫入 `data/`／`output/`／`site/`；scratchpad 我的暫存檔已刪。
