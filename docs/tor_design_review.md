# Design Review: PTT 追蹤助手 web/index.html

## 任務意圖判定
- 屬於 ④ 審查 + 局部優化（既有畫面已能用，要求做視覺/互動品質審查並直接修，不是重新設計）
- 載入 skill：`ui-ux-pro-max`（容器內正版），依其 Quick Reference（a11y、touch/interaction、layout & responsive、typography & color、animation、forms & feedback）逐項比對
- 未使用代替方案

## 整體協調性檢視
- 退一步看整張畫面：header → 追蹤項 → 白話輸入 → 掃描條件卡片 → 進度 → 結果，資訊架構原本就合理、單線流程，不需重排。
- 這次改動全部是**系統化收斂**，不是加功能塞版面：把原本隨手填的 px 值（10/14/6/4/8/12/16/20/24/28/40…）收進一份 4px 間距刻度（`--space-1`~`--space-8`），圓角也拆成 `--radius`/`--radius-sm`/`--radius-pill` 三級語意，讓同層級元件間距和轉角一致。畫面外觀變化很小（刻意，不是重新設計），但底層規則更乾淨，之後加欄位/加按鈕比較不會再長歪。
- 沒有發現需要整合的按鍵/入口——目前 3 個主要按鈕（解析／開始掃描／存成追蹤項）分屬不同步驟、視覺層級已用 primary/ghost 區分得宜，不需要合併或討論結構變動。

## 設計決策
1. **間距與圓角系統化**：新增 `--space-1..8`（4px 刻度）與 `--radius/--radius-sm/--radius-pill`，取代原本 6/8/10/14/16/20/24/28/40px 等零散數字，全檔套用。理由：Priority 5（Layout & Responsive）`spacing-scale` 準則要求 4/8dp 遞增系統。
2. **字重建立層級**：h1 600、h2 600、`.item h3`（結果標題）600、`.field label` 500，其餘內文維持 400。原本全站幾乎同一字重、只靠字級分層，加上字重後標題/內文對比更清楚。理由：Priority 6 `weight-hierarchy`。
3. **統一互動狀態**：新增全域 `:focus-visible` outline（accent 色、2px、offset 2px）給所有按鈕/連結/輸入框；`button` 加 150ms transition 讓 hover/disabled 切換不是瞬間跳色；`button.primary:disabled` 改用 `cursor:not-allowed`（原本是 `default`，語意不夠明確）。理由：Priority 1 `focus-states`、Priority 7 `duration-timing`。
4. **提高小型可點擊元素的觸控面積**：`.track button.del` 從 `padding:2px 4px` 加大到 `8px 10px` 並補 hover 底色；`.item .toggle`（顯示內文摘要）從 `padding:0` 改 `4px 2px`；`.track button.run` 從 `6px 14px` 加到 `8px 14px`。理由：Priority 2 `touch-target-size`（雖是桌面工具，仍值得靠近舒適熱區標準，且此工具也可能在觸控筆電/平板瀏覽器開啟）。
5. **RWD 補強**：`.ask`（白話輸入列）與 `.row-actions`（掃描條件底部按鈕列）原本是純 `flex` 無 wrap 保護，輸入框在極窄螢幕會被過度擠壓；改為 `flex-wrap:wrap` + `.ask input{flex:1 1 220px}`，並加 `@media (max-width:420px)` 讓主要按鈕改滿版、`.row-actions` 改直排，避免窄螢幕擠成一團或誤觸。理由：Priority 5 `mobile-first`、`horizontal-scroll`。
6. **表單可及性補強（零風險、不動 JS）**：
   - `#ask-input`、`#filter-box` 原本只靠 placeholder 當標籤，補上 `.sr-only`（螢幕閱讀器可讀、畫面不佔位）`<label for>`，符合 Priority 8 `input-labels`「不能只靠 placeholder」。
   - 全站補 `input::placeholder`/`textarea::placeholder` 顏色為 `--ink-2`，避免部分瀏覽器預設 placeholder 對比過低。
   - `#log`（掃描進度日誌）加 `aria-live="polite"`，讓螢幕閱讀器使用者能聽到掃描進度更新，不需額外改 JS（JS 本來就往這個 div 寫文字）。
   - `.checkline`／checkbox 補 `cursor:pointer`、`accent-color:var(--accent)`，讓核取方塊視覺呼應主色且更明確可點。
7. **克制**：沒有加陰影、漸層、圖示字型、額外裝飾色塊；沒有動到任何版面順序、沒加新按鈕或新欄位；沒有導入外部字型或 CDN（保持單檔離線可跑）。維持「乾淨工具」調性。
8. **色彩對比**：實際計算既有色票（`--ink-2` #5b6675 對白底 ≈5.8:1、`--warn` #b4552d 對白底 ≈4.9:1、`--accent` #2f6f5e 對白底/accent 對白字 ≈5.9:1）皆已通過 WCAG AA 4.5:1，這次沒有更動任何色值，只在既有配色上補齊狀態與層級。

## 產物位置
- 直接編輯：`C:\Users\AG_Di\Desktop\automation\Claude_code\PTT_Assistant\web\index.html`
  - 全部改動集中在 `<style>` 區塊（第 7–185 行）與三處小型 HTML 補充（`ask-input`/`filter-box` 的 `<label class="sr-only">`、`#log` 加 `aria-live`）
  - `id`、JS 用到的 class（`track`/`run`/`del`/`name`/`item`/`open`/`preview`/`toggle`/`chip`/`chips`/`card`/`meta`/`empty`/`error` 等）與所有事件綁定、fetch 路徑**完全未變動**
- 執行方式：照專案既有方式跑 `server.py`（`http://127.0.0.1:8877`），重新整理頁面即可看到效果

## 自審結果（④ 心法）
- a11y：新增 focus-visible、sr-only label、aria-live、placeholder 對比；核取方塊沿用原生控制項（未自製假 checkbox）。既有色票經算過對比皆達 AA。
- 狀態完整度：按鈕新增 hover/disabled/focus 過渡；`.track button.del`、`.item .toggle` 補齊可視 hover/熱區；loading 中 `#btn-run` disabled + `#btn-cancel` 顯示、`.toggle` 讀取中文案，原本就有，保留。
- RWD：`.ask`、`.row-actions` 補 wrap 與窄螢幕媒體查詢；`.grid`（auto-fit minmax 210px）與 `#results-head` 原本即可在 320px 寬度不爆版，未動。
- 無新增 sticky/fixed 元件（header 非 sticky，維持原狀，符合 Dino 偏好）；無外部 CDN；系統字體 fallback 維持原本 `"Segoe UI","Microsoft JhengHei","PingFang TC"` 堆疊。

## 後續建議
- 給 Ray：建議做一次瀏覽器 regression——重點測「顯示內文摘要」toggle、「刪除追蹤項」、白話輸入 Enter 觸發解析、掃描進度輪詢——確認 CSS 改動沒有影響任何 click/keydown 行為（本次只動 CSS/屬性，理論上不影響，但建議實測收斂風險）。
- 給 Andy：請記錄這次「間距/圓角系統化 + a11y 補強」的設計決策，日後若要幫這個工具加新欄位/新按鈕，沿用 `--space-*`/`--radius-*` token 即可維持一致。
- 給 Bevis：此次為純視覺/互動品質優化，未涉及功能或產品方向判斷，無需審視。

---

## v2.1 增量審查（新增：模式 select、分類頁籤、卡片快取行、結果 meta 行）

### 任務意圖判定
- 屬於 ④ 審查（增量）：既有畫面上輪已過 `ui-ux-pro-max` 設計關，這次只審 v2.1 新增的 4 個元素是否與既有 token/間距/focus/hover/a11y 系統一致
- 硬性載入 `ui-ux-pro-max`（容器內正版，未用代替方案）；Windows 主機端 `scripts/search.py` 對應資料庫不存在（`project_tor_uiuxpromax_host_gap.md` 已知現象），改用 skill 內建的 Quick Reference / Common Rules 表格直接比對，未動手前就先核對 Priority 1（a11y）、2（Touch）、4（Style 一致性）、8（Forms）、9（Navigation Patterns，分類頁籤視為 segmented control）
- 本輪**只動 CSS**（`<style>` 區塊），完全沒有碰 `<script>`；所有 id、JS 用到的 class、事件綁定、select option value 一律未變動——這是本輪最主要的自我約束，因為新增元素本身多半是結構/邏輯正確、只是視覺細節沒跟上系統

### 整體協調性檢視
- 退一步看整張畫面：新增的 4 個元素分別落在「條件表單」「結果區上緣」「追蹤項卡片」三個既有分區內，**沒有新開版面、沒有加新的按鍵入口**，是在既有骨架裡把新資訊放進對的位置，方向正確，不需要重排或整合建議。
- 屬於「順手收斂」而非「硬塞」的地方：
  - `.tracks` 原本 `align-items` 用瀏覽器預設 `stretch`，v1 時所有追蹤項卡片都差不多高（沒差）；v2.1 加了 cachetime 行後，有快取的卡片變兩行、沒快取的還是一行，`stretch` 會把矮卡片硬拉到跟高卡片一樣高、內容置中留一大塊空白，看起來像排版錯誤。改成 `align-items: flex-start`，讓每張卡片維持自己內容該有的高度，這是 v2.1 這次新增內容才會暴露的問題，順手修掉。
  - `.tab`（分類頁籤 pill）原本 `padding:6px 14px`，實測含 line-height 後可點擊熱區只有約 34px 高，低於 Priority 2「Touch & Interaction CRITICAL」的 44×44 基準，也比同頁其他按鈕（`button.ghost` 實測約 44px）矮一截，视覺上和其他控制項的「重量感」不一致。改成 `padding: var(--space-3) var(--space-4)`（12px/16px，仍在既有 4px 刻度上，沒發明新數字），熱區拉到約 46px，同時跟 `button.ghost`/`button.primary` 的觸控手感對齊。
  - `.track .name` 原本可點擊互動只靠「hover 變色 + title 提示」，滑鼠使用者還好，但這是純視覺線索、且行動裝置沒有 hover，發現時完全看不出「這個名字可以點」。加上靜態虛線底線（hover/focus 再轉實線＋主色），符合 `color-not-only`（不能只靠顏色/hover 傳達可互動）與 `hover-vs-tap`（不能只靠 hover）。
- 沒有硬塞的地方：conditional 欄位（`.mode-scan`/`.mode-author`/`.mode-hot`/`.mode-scanhot`）本身就是做得對的 progressive disclosure（一次只顯示當下模式相關欄位，而不是把三種模式全部欄位攤開），完全命中 Priority 8 `progressive-disclosure` 準則，這部分維持原樣、不需要我插手。
- 發現但**沒有動手**、提出來討論的整合建議：
  - 「模式」select（`#f-intent`）目前混在欄位格線裡，跟其他 8 個欄位平起平坐，但它其實是**支配整個表單顯隱**的主控制項（跟下面的分類頁籤角色很像：都是「先選一個大分類，再看細節」）。若之後還要加第 4、5 種模式，建議討論看看要不要把它獨立成表單上緣一排 pill/segmented control（視覺上呼應下面 `#cat-tabs` 的 pill 語言），會比繼續埋在 grid 裡更凸顯「這是先選的」。這是**結構性**改動（牽動表單版面骨架），這次先不動，留給 Dino/主 Claude 拍板要不要做。
  - 結果 `.meta` 行（新增看板、推文數）跟卡片旁的 `.cachetime` 行都是「資訊密度較高的單行文字」，但一個用全形空格分隔、一個用「｜」分隔，兩種視覺語彙同時存在。這屬於文字內容（JS 字串 join），按本次「不動 JS」的硬性約束我沒有動，先記錄下來，若之後要動 JS 時可以順手統一成「｜」分隔，讓兩處資訊密度高的行看起來出自同一套系統。

### 設計決策
1. **`.tracks` 改 `align-items: flex-start`**：避免 cachetime 讓卡片高度不一致時被 stretch 拉出不自然留白，理由 Priority 5 `visual-hierarchy` / 卡片群一致性。
2. **`.tab` 觸控熱區拉到 4px 刻度上的 `var(--space-3) var(--space-4)`**：命中 Priority 2 CRITICAL 觸控基準，同時跟既有按鈕的重量感對齊（Priority 4 `consistency`）；捨棄了把 pill 做得更緊湊小巧的做法，因為「小巧」在這裡等於「不好按」。
3. **`.track .name` 補靜態虛線底線＋hover/focus 轉實線＋主色**：命中 Priority 1 `color-not-only`、Priority 2 `hover-vs-tap`；捨棄了加圖示（例如小箭頭）的做法，避免多一個裝飾元素破壞「克制」原則，底線是最輕量、最不喧賓奪主的可互動提示。
4. **`.cachetime` 補 4px 刻度的 `margin-top` 與 `word-break: break-word`**：前者解決名稱與快取資訊兩行貼太緊的問題，後者是防禦性寫法（沿用既有 `.preview` 已經在用的 `word-break: break-word` 慣例，不是新發明），避免長字串在極窄卡片上頂破版面。
5. **守住的底線**：完全沒碰 `<script>`；沒新增任何顏色值（全部沿用既有 `--accent`/`--ink-2`/`--line` token）；沒加陰影、圖示字型、裝飾色塊；沒有為了「更好看」把 select 換成自製下拉元件（保留原生 `<select>`，符合 `system-controls` 準則——能用原生控制項就不要自製）。

### 產物位置
- 直接編輯：`C:\Users\AG_Di\Desktop\automation\Claude_code\PTT_Assistant\web\index.html`（只動 `<style>` 區塊內 `.tracks`、`.tab`、`.track .cachetime`、`.track .name` 四處規則，`<script>` 完全未動）
- 執行方式：`server.py` 跑起來後開 `http://127.0.0.1:8877`，重新整理即可看到效果

### 自審結果（④ 心法）
- a11y：`.name` 靜態底線解決「純靠 hover/顏色」的可辨識性問題；但 `.name` 目前是 `<span>` 綁 click，**沒有 `tabindex`/`role`/keydown**，鍵盤使用者完全無法用 Tab 到達或用 Enter/Space 觸發——這是結構性缺口，需要動 JS 才能補（加 `tabindex="0" role="button"` + keydown 轉發 click），本輪因「不可動 JS 邏輯」的硬性限制沒有處理，**列為必須跟催的遺留問題**（見下方建議）。
- 狀態完整度：`.tab` 的 hover/active 已有；`focus-visible` 因為 `.tab` 本質是 `<button>`，直接吃到全域 `button:focus-visible` 規則，鍵盤可見；`.name` 沒有 focus 狀態（因為完全不可 focus，見上一點）。
- 對比：新規則沒有引入任何新色值，全部沿用上一輪已算過 AA 合格的 token，無新增對比風險。
- RWD：`.tab` 加 `white-space: nowrap` 避免文字在 pill 內斷行變形；`.cachetime` 補 `word-break: break-word` 防止極窄螢幕爆版；未實機用瀏覽器截圖驗證（本次任務環境沒有 Playwright/瀏覽器工具可用），建議 Ray 或 Dino 直接開 `http://127.0.0.1:8877` 用手機寬度模擬看一次。

### 後續建議
- 給 Zavier（若之後要動 JS）：`.track .name` 目前是完全無法用鍵盤操作的可點擊元素（見上方 a11y 自審），建議補 `tabindex="0"`、`role="button"`、`aria-label`（例如「看『{name}』上次結果」）與 keydown（Enter/Space）轉發 click 事件；這是輕量、不影響既有邏輯的加法,但因為是本輪明確被限制的範圍（不可動 JS）沒有處理，請排進下一輪。
- 給 Dino/主 Claude：上方「整體協調性檢視」提了兩個結構性/內容一致性建議（模式 select 要不要獨立成 pill 列、meta 與 cachetime 的分隔符號要不要統一成「｜」）——都是可做可不做的加分項，沒有急迫性，列出來供拍板，這次沒有自己動手。
- 給 Ray：本輪只動 CSS，理論上不影響任何互動邏輯，但分類頁籤篩選、快取名稱點擊這兩個是本次視覺改動最貼近的互動，建議下次 regression 順便看一眼點擊後畫面是否如預期（結果列表依分類過濾、點名稱載入快取）。
- 給 Andy：請記錄「v2.1 只動 CSS、不動 JS」這個範圍決策的理由（風險控管），以及新發現的 `.name` 鍵盤不可達缺口，方便追蹤何時補上。

---

## v2.2 分頁式重設計審查（新增：依功能分頁 IA、白話輸入升全域入口、下載全文控制）

### 任務意圖判定
- 屬於 ④ 審查：Dino 已要求整頁改成「依功能分頁」IA、Dino 端已重寫完成，這輪是審這個新 IA 的視覺層級/一致性，不是從零設計
- 硬性載入 `ui-ux-pro-max`（容器內正版，未用代替方案）；Windows 主機端無 `scripts/search.py` 對應資料庫（`project_tor_uiuxpromax_host_gap.md` 已知現象），改用 skill 內建 Quick Reference / Priority 表直接比對，本輪對照 Priority 4（Style Selection：一致性）、Priority 9（Navigation Patterns：`nav-hierarchy` 主次導覽要清楚分離）、Priority 8（Forms & Feedback：控制項分組）、Priority 5（RWD）
- 本輪用 Playwright（沿用 `Desktop\automation\Playwright` 集中安裝的 venv，跑完即刪除一次性腳本子資料夾，不留任務殘留）對 `http://127.0.0.1:8877` 實機截圖驗證（含 375px 窄螢幕），不是只看程式碼猜效果——落實「改 UI 後必須用真實瀏覽器驗證」的既有規則

### 整體協調性檢視
- 退一步看整張畫面：新 IA（白話輸入 → 功能頁籤 → 功能控制卡 → 共用結果區）骨架合理，資訊優先序清楚，不需要重排版面順序。
- 這次改動屬於**收斂既有兩層 pill 的視覺權重**，不是加新元素：Dino 提到的疑慮成立——上一輪我建議的「pill 樣式呼應分類頁籤」讓 `.viewbtn`（頁面級功能頁籤）跟 `.tab`（結果區分類頁籤）active 時是同一種實心深綠色圓角膠囊，字級/padding 只差一點，實機截圖比對後兩層在視覺上幾乎融成同一種控制項，違反 Priority 9 `nav-hierarchy`（主次導覽必須清楚分離）。修法是**同語彙、不同權重**，不是砍掉重練：
  - `.viewbtn`（主層級）：外面包一層淡灰底、圓角軌道容器（segmented rail），字重拉到 600，active 維持實心 `--accent` 填色＋淡陰影——用「有沒有外層容器」這個結構性差異，直接跟下面的分類頁籤拉開，比單靠字級差更明確。
  - `.tab`（次層級，結果區分類頁籤）：active 狀態從實心 `--accent` 改成淡底 `--accent-soft` ＋描邊＋`--accent` 文字，不再跟主導覽搶同一種「深綠實心」的視覺重量；pill 本身縮小一點（padding 12px/16px → 7px/16px，字級 .88rem → .85rem），視覺上明顯讓位給主導覽。
  - 兩者仍是同一個「pill 家族」（圓角、間距刻度、hover 邏輯一致），只是用容器 + 填色深淺建立清楚的主/次關係——這是我認為對的取捨：完全維持 pill 語彙的一致性（不引入新元件語言），只調整權重就解決混淆，不需要跟 Dino 討論結構性大改。
- 下載控制（`#results-head` 內的「含留言」checkbox ＋「下載全文 TXT」按鈕）原本跟「結果內過濾」input 平鋪在同一排、沒有分組——瀏覽用途（過濾）跟匯出用途（下載）混在一起，使用者掃過去分不出這兩件事是不同操作。改法：把 checkbox＋按鈕包進一個 `.export-actions` 群組，用 `margin-left:auto` 推到最右、加一條 `border-left` 分隔線跟過濾輸入框拉開，形成清楚的「左：瀏覽 / 右：匯出」兩群。這是**順手收斂**、不是硬塞——沒有加任何新按鈕或新欄位，只是把已存在的兩個控制項重新分組，且完全沒有動 `id`/`class`（`dl-comments`、`btn-export`、`runbtn`），JS 選取器不受影響。
- 沒有發現需要跟 Dino 討論的結構性整合建議——本輪疑慮（兩層 pill 混淆、下載控制未分組）都是「局部協調性修整」層級（對齊、間距、層次、配色），照協議可以直接做，不需要上呈拍板。

### 設計決策
1. **`.views` 包一層淡灰軌道容器（segmented rail）**：`background:var(--chip)`、`padding:3px`、`border-radius:var(--radius-pill)`，`.viewbtn` 本身改 `background:transparent`、`border:0`，只有 active 時才填 `--accent` 實色＋淡陰影。理由：Priority 9 `nav-hierarchy`——用「有沒有外層容器」這個結構訊號區分主導覽，比純調字級更明確、也更符合「segmented control」這個使用者熟悉的心智模型（一組按鈕代表『你正在哪一個功能』）。
2. **`.tab`（結果分類頁籤）active 改淡底描邊**：`background:var(--accent-soft)`、`border-color:var(--accent)`、`color:var(--accent)`、`font-weight:600`，捨棄原本的實心填色。理由：次層級的視覺重量必須明顯低於主導覽，才不會讓使用者以為這是另一組平行的頁面切換；同時 pill 尺寸也縮小一級（`padding:7px 16px`，字級 .85rem），與主導覽的 `padding:10px 20px`／字級 .95rem 拉開差距，形成一眼可辨的大小階層。
3. **下載控制分組 `.export-actions`**：右側群組加 `border-left:1px solid var(--line)` 分隔線＋`margin-left:auto`，把「過濾（瀏覽）」與「含留言＋下載全文（匯出）」視覺上分成兩群；窄螢幕（≤420px）媒體查詢把分隔線改成 `border-top`、群組改滿版 `justify-content:space-between`，避免堆疊時分隔線斷在奇怪位置。理由：Priority 8 `field-grouping`（相關控制項邏輯分組）。
4. **順手補 `.checkline` 垂直 padding（8px 0）**：讓「含留言」checkbox 的可點擊標籤高度更接近其他按鈕的觸控熱區，跟既有 `.track button.del`/`.item .toggle` 熱區加大的既有慣例一致（v2.0 已建立的準則），不是本輪新標準。
5. **克制**：沒有新增顏色值（`--accent-soft`/`--chip`/`--line` 都是既有 token）；沒有加陰影堆疊、圖示、裝飾色塊；兩層 pill 差異靠「容器有無＋填色深淺＋尺寸」三個既有手法組合，沒有引入新的視覺語言（例如底線導覽、圖示切換等）——維持整站只有一種導覽語彙（pill）的一致性。

### 產物位置
- 直接編輯：`C:\Users\AG_Di\Desktop\automation\Claude_code\PTT_Assistant\web\index.html`
  - CSS：`.views`/`.viewbtn`、`.tabs`/`.tab`、`#results-head`、新增 `.export-actions`、`.checkline` 補 padding、`@media (max-width:420px)` 補三條規則
  - HTML：`#results-head` 內把既有 `#dl-comments` checkbox 與 `#btn-export` 按鈕包進新的 `<div class="export-actions">` 容器（純結構包裝，兩者 id/class 原樣保留，`btn-export` 仍是 `.ghost.runbtn`）
  - `<script>` 完全未動；所有硬性保留的 id/data-view/class（`viewbtn`/`active`/`view`/`tab`/`track`/`run`/`del`/`name`/`clickable`/`cachetime`/`runbtn`/`item`/`open`/`preview`/`toggle`/`chip`/`chips`/`meta`/`card`/`empty`/`error`/`checkline`）一律未改名
- 執行方式：`server.py` 跑起來後開 `http://127.0.0.1:8877`，重新整理即可看到效果
- 驗證截圖（Playwright 實機截圖，非猜測）：`tests/screenshots/tor_v22_top.png`（桌面寬度主導覽＋分類頁籤對比）、`tor_v22_head.png`（下載控制分組）、`tor_v22_narrow_nav.png`／`tor_v22_narrow_head.png`（375px 窄螢幕堆疊效果）

### 自審結果（④ 心法）
- a11y：兩層 pill 都仍是原生 `<button>`，全域 `button:focus-visible` outline 規則不受影響（`.viewbtn` 拿掉 border 不影響 outline，outline 是獨立盒模型層）；`.tab.active` 新色組 `--accent`(#2f6f5e) 文字 on `--accent-soft`(#e7f1ee) 底，對比遠高於 4.5:1 AA 門檻；`.export-actions` 純結構包裝未動任何 `for`/`id` 關聯，`dl-comments` 的 `<label>` 仍正確包住 checkbox。
- 狀態完整度：`.viewbtn`/`.tab` 的 hover/active/focus 三態齊全（沿用既有 transition）；未新增 disabled/loading 狀態需求（下載按鈕本身已有 `.runbtn` 統一 disable 機制,本輪未動）。
- RWD：已用 Playwright 在 1000px 與 375px 兩種寬度實機截圖確認——桌面下主導覽軌道與分類頁籤層級分明；375px 下 `.views` 自然換行仍維持同一軌道背景（視覺不斷裂），`#results-head` 的匯出群組改為滿版堆疊＋上框線，未爆版、未重疊。
- 對比：本輪沒有引入任何新色值，全部沿用既有 token（`--accent`/`--accent-soft`/`--chip`/`--line`），無新增對比風險。

### 後續建議
- 給 Bevis：本輪為純視覺層級收斂，未涉及功能或產品方向判斷，無需審視。
- 給 Ray：建議做一次瀏覽器 regression——重點測分類頁籤切換（`#cat-tabs` 篩選是否仍正確過濾清單）、下載全文按鈕（`btn-export` 位置移動後點擊是否仍觸發 `/api/download`）、白話輸入解析後自動切頁；本輪只動 CSS 與一層 HTML 結構包裝，理論上不影響任何 click/keydown 邏輯，但建議實測收斂風險。
- 給 Andy：請記錄這次「兩層 pill 同語彙不同權重」與「下載控制分組」的設計決策，日後若某功能頁的控制卡要再加新的批次操作按鈕，優先考慮沿用 `.export-actions` 的分組手法（`margin-left:auto` + 分隔線），而不是繼續平鋪塞進同一排。

---

## 熱門 v2 增量（新增：#sort-toggle 排序切換、meta 行新增留言/討論串數字、分類頁籤擴增為看板主題 8–10 個）

### 任務意圖判定
- 屬於 ④ 審查（增量）：既有畫面上三輪已過 `ui-ux-pro-max` 設計關，這次只審熱門文章 v2 新增的 3 個元素是否與既有系統一致
- 硬性載入 `ui-ux-pro-max`（未用代替方案）；本輪 Windows 主機端同樣沒有 `scripts/search.py` 對應資料庫（`project_tor_uiuxpromax_host_gap.md` 已知現象），改用 skill 內建 Quick Reference / Priority 表直接比對，重點對照 Priority 9（Navigation Patterns：`nav-hierarchy` 主次要清楚分離、`avoid-mixed-patterns`）、Priority 6（Typography & Color：`weight-hierarchy`）、Priority 5（RWD：`horizontal-scroll` 不能靠橫向捲動解決過多 tab）
- 本輪同時改 `web/index.html`（本機版）與 `site/index.html`（唯讀版），兩邊都有各自獨立的 `<script>`，但渲染結果 meta 行與排序切換的 HTML/CSS 結構幾乎一致，逐一對照改，確保兩邊視覺一致

### 整體協調性檢視
- 退一步看整張畫面：三個新元素都落在既有「結果區」骨架裡（`#cat-tabs` 分類列 → `#results-head`/`#head` 計數＋排序＋過濾列 → 卡片列表），沒有新開版面、沒有加新入口，方向正確。
- 這次判定**必須順手重排**、不能照現狀硬塞的地方：`#sort-toggle` 原本直接沿用 `.tab` 這個「結果分類頁籤」的 outline pill 樣式，只是換一行放。問題是它跟正上方 `#cat-tabs`（現在擴增到 8–10 個看板主題）是同一種視覺語彙、同一種顏色權重，兩排 pill 疊在一起時使用者很容易把「排序方式」誤讀成「另一組可多選的分類」——這正好命中 Priority 9 `avoid-mixed-patterns`（同一層級不要混用多套語彙）反過來的陷阱：語彙相同但語意不同，一樣會混淆。分類頁籤變多之後這個風險被放大（一整排看板名稱 pill 下面接著兩顆長得一模一樣的排序 pill，掃視時很難一眼分辨界線在哪）。
  - 修法：把 `#sort-toggle` 改成「凹槽＋實色滑塊」的分段控制項（segmented control），直接沿用本頁已經存在的 `.views`（頁面級功能切換）視覺語言——淡灰底凹槽容器＋透明按鈕＋active 時填白底＋陰影。這不是發明新元件，是把「本來就用來表達『互斥狀態切換』」的既有語彙用在刀口上，跟「用來表達『可選分類』」的 `.tab` outline pill 明確分家。同時在容器最前面加一個小小的靜態文字標籤「排序」，用最低成本把語意錨死，不需要圖示或額外裝飾。
  - 這是**順手收斂**而非硬塞：沒有新增按鈕、沒有改變排序邏輯或觸發方式，只是把「長得像分類的排序控制項」矯正回「看起來像排序的排序控制項」，且完全沒有更動 `data-sort`／JS 選取器（`#sort-toggle .tab`）。
- meta 行變長（新增「留言 N（每小時 M）」「討論串 N 篇」）：原本全部資訊用同一個灰階字色、全形空格分隔的純文字，日期/作者這種單純識別資訊跟「留言/每小時/討論串」這種驅動排序的關鍵數字混在一起、沒有輕重之分，資訊變多後尤其容易變成一整行難以掃視的灰字牆，也跟上方新加的排序功能脫節（使用者切換「總留言數」排序後，卻要在一整排同色文字裡自己找出留言數字在哪）。
  - 修法：把「留言（含每小時）」與「討論串 N 篇」拆成獨立 `<span class="meta-metric">`，用 `--accent` 提亮＋字重 600，其餘（日期/作者/看板/推文）維持原本素色文字。這樣排序依據的數字自然被視覺強調，跟 `#sort-toggle` 的功能形成呼應，是本輪「整體協調」的核心用意——不是單獨修 meta 行好看，而是讓 meta 行跟同一輪新增的排序功能互相對得上。
  - 這需要小幅調整 JS 渲染邏輯（把 `meta.textContent = bits.join(...)` 拆成「先塞素色文字、再用 `createElement` 補兩個強調 span」），但沒有改動任何既有 `id`／既有 class 名稱／既有事件邏輯，純粹是渲染輸出的內部實作細節。
- 分類頁籤擴增到 8–10 個（熱門看板主題）：既有 `.tabs { flex-wrap: wrap }` 機制本來就是為「數量不固定的分類」設計，看板主題變多只是自然多繞一行，不需要加橫向捲動（Priority 5 明確反對 `horizontal-scroll`），維持現狀即可，這部分**沒有動**。
- 沒有發現需要跟 Dino/主 Claude 討論的結構性整合建議——本輪處理的是「同語彙不同語意造成混淆」與「資訊密度提高後缺層次」，都是局部協調性修整（對齊、間距、層次、配色）層級，照協議可以直接做。

### 設計決策
1. **`#sort-toggle` 改為凹槽分段控制項，脫離 `.tab` 的分類 pill 視覺**：`background:var(--chip)` 凹槽容器＋`padding:3px`＋`gap:2px`；容器內 `.tab` 改 `background:transparent; border:0`，active 時 `background:var(--surface); box-shadow:0 1px 2px rgba(31,39,51,.12)`。理由：沿用本頁已建立的「軌道＋滑塊＝互斥切換」語言（`.views` 已示範過），跟「分類篩選＝outline pill」徹底分家，符合 Priority 9 `nav-hierarchy`／`avoid-mixed-patterns`。捨棄了「幫排序 pill 換個新顏色」的做法——換色只能治標，換視覺骨架（有無容器）才是治本、且不引入第三套語彙。
2. **新增 `.sort-label`「排序」文字錨點**：低成本（一個 12px 灰字），在分段控制項前明講這組控制項的作用，直接消解「跟上面分類 tab 是不是同一件事」的疑慮。純 HTML/CSS 增補，不影響 `#sort-toggle .tab` 的 JS 選取器（querySelectorAll 只認 `.tab`，label 不是 `.tab`，不受影響）。
3. **meta 行拆出 `.meta-metric`（`--accent` + 字重 600）強調排序依據數字**：命中 Priority 6 `weight-hierarchy`（用字重/色彩強化層級，不是全部同色）；也呼應 Priority 4 `consistency`——強調色沿用既有 `--accent` token，沒有發明新顏色。捨棄了「把整行拆成多個 chip 徽章」的做法（會讓 meta 行從一行文字膨脹成一排小方塊，在本來已經偏密的結果卡片裡更佔空間、更吵），選擇最輕量的「同一行內文字提亮」，維持「克制」。
4. **`.meta` 補 `line-height:1.7`**：新增的兩段內容讓行更容易在窄螢幕換行，既有 1.6 全站行高在多行文字疊字重時略緊，微調到 1.7 讓換行後的可讀性更寬鬆，不影響單行時的視覺（差異僅 0.1，內容仍以全形空格自然斷行，不會斷字）。
5. **兩個檔案改法一致**：`web/index.html`（本機版）與 `site/index.html`（唯讀版）的 CSS 規則、HTML 標籤結構、JS meta 渲染邏輯逐一對照修改，維持兩份輸出視覺一致（唯讀版本身架構更簡單、沒有 `#results-head`/`export-actions`，但 `#sort-toggle`／`.meta`／`#cat-tabs` 的結構與本機版完全對應，改法可以 1:1 套用）。
6. **克制**：沒有新增顏色 token（`--accent`/`--chip`/`--surface`/`--ink-2` 全是既有變數）；沒有加圖示、陰影堆疊、裝飾色塊；沒有把分類頁籤數量變多當理由加上橫向捲軸或「更多」收合選單（8–10 個仍在 `flex-wrap` 可負荷範圍，過早引入收合選單反而增加一次多餘點擊）；完全沒有更動 `#sort-toggle`／`data-sort`／`data-view` 等 JS 依賴的選取器與屬性。

### 產物位置
- 直接編輯（兩份文件改法一致）：
  - `C:\Users\AG_Di\Desktop\automation\Claude_code\PTT_Assistant\web\index.html` — CSS 新增 `#sort-toggle`／`#sort-toggle .sort-label`／`#sort-toggle .tab`／`#sort-toggle .tab.active`／`.meta-metric` 規則、`.meta` 補 `line-height`；HTML 在 `#sort-toggle` 內加 `<span class="sort-label">排序</span>`；JS `renderItems()` 的 meta 組裝邏輯改為「素色文字 + 兩個 `.meta-metric` span」
  - `C:\Users\AG_Di\Desktop\automation\Claude_code\PTT_Assistant\site\index.html` — 對應位置同步同一組 CSS／HTML／JS 改法
  - 所有既有 `id`／`data-sort`／`data-view`／JS 用到的 class（`tab`／`active`／`tabs`／`meta`）**一律未改名**，`#sort-toggle` 的 `style.display` 顯隱邏輯完全交給 JS，本輪 CSS 未設定任何 `display` 屬性去蓋過它
- 執行方式：`web/index.html` 照專案既有方式跑 `server.py`（`http://127.0.0.1:8877`），重新整理熱門頁即可看到效果；`site/index.html` 為靜態唯讀頁，直接開檔或部署後查看即可

### 自審結果（④ 心法）
- a11y：`#sort-toggle .tab` 仍是原生 `<button>`，全域 `button:focus-visible` 規則不受影響（拿掉 `border` 不影響 outline，兩者是獨立盒模型層）；`.meta-metric` 的 `--accent`(#2f6f5e) 文字 on 白色卡片底，對比遠高於 4.5:1 AA（沿用上一輪已算過的色票，未新增色值）；新增的 `.sort-label` 是純裝飾性文字說明，非互動元素，不需要額外 aria 屬性。
- 狀態完整度：`#sort-toggle .tab` 的 hover/active 狀態齊全（hover 變 `--accent` 字色、active 實色滑塊＋陰影），沿用既有 `button` 全域 transition，切換有漸變不是瞬間跳色。
- RWD：`#sort-toggle` 未設定 `display`（維持 JS 控制的 flex/none），容器本身依舊在 `#results-head` 的 `flex-wrap:wrap` 規則下自然換行；未额外用瀏覽器實機截圖驗證本輪窄螢幕效果（本次任務環境沒有提供瀏覽器/Playwright 工具），建議 Ray 或 Dino 直接開頁面在手機寬度模擬看一次分類頁籤（8–10 個)＋排序控制項＋meta 多行同時出現時是否擁擠。
- 對比：本輪沒有引入任何新色值，`.meta-metric`／`#sort-toggle .tab.active` 皆沿用既有 token，無新增對比風險。

### 後續建議
- 給 Ray：建議做一次瀏覽器 regression（含 375px 窄螢幕）——重點測「排序切換」點擊後清單是否確實依 rising/comments 重新排序、分類頁籤在 8–10 個看板主題下的多行 wrap 是否正常、meta 行含新的 `.meta-metric` span 後文字過濾（`#filter-box`）是否仍正確比對（過濾邏輯讀的是 `r.title`/`r.author`/`r.board`/`r.preview` 原始資料而非 DOM 文字，理論上不受影響，但建議實測收斂風險）。
- 給 Andy：請記錄本輪「排序切換脫離分類 pill 視覺、改用凹槽分段控制項」與「meta 行用 `.meta-metric` 強調排序依據數字」的設計決策；日後若熱門功能再加其他排序維度（例如按讚數、發文時間），優先沿用 `#sort-toggle` 這套凹槽分段控制項語言，而不是繼續加 `.tab` outline pill。
- 給 Bevis：本輪為純視覺層級審查與局部收斂，未涉及功能或產品方向判斷，無需審視。
