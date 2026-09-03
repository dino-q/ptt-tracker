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
- 直接編輯：`C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html`
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
- 直接編輯：`C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html`（只動 `<style>` 區塊內 `.tracks`、`.tab`、`.track .cachetime`、`.track .name` 四處規則，`<script>` 完全未動）
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
- 直接編輯：`C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html`
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
  - `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html` — CSS 新增 `#sort-toggle`／`#sort-toggle .sort-label`／`#sort-toggle .tab`／`#sort-toggle .tab.active`／`.meta-metric` 規則、`.meta` 補 `line-height`；HTML 在 `#sort-toggle` 內加 `<span class="sort-label">排序</span>`；JS `renderItems()` 的 meta 組裝邏輯改為「素色文字 + 兩個 `.meta-metric` span」
  - `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\site\index.html` — 對應位置同步同一組 CSS／HTML／JS 改法
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

---

## 瀏覽控制四件套增量審查（新增：#day-filter 天數篩選、.item-actions 卡片動作列＋.badge-pin、#to-top 回頂圓鈕）

### 任務意圖判定
- 屬於 ④ 審查（增量）：既有畫面已過五輪 `ui-ux-pro-max` 設計關，這次只審本輪新增/新出現組合的 4 個元素是否與既有系統一致、以及「多控制項同時出現」是否仍協調
- 硬性載入 `ui-ux-pro-max`（未用代替方案）；Windows 主機端同樣沒有 `scripts/search.py` 對應資料庫，改用 skill 內建 Quick Reference / Priority 表直接比對，本輪重點對照 Priority 5（Layout & Responsive：擁擠度與換行）、Priority 2（Touch & Interaction：熱區/間距）、Priority 4（Style Selection：一致性）
- 本輪用 Playwright 對 `http://127.0.0.1:8877` 實機截圖驗證（桌面 1000px 與 375px 窄螢幕都截），並直接讀取 DOM bounding box 量測 `#results-head` 各子項的實際寬度與換行位置，不是憑肉眼猜——這題材主 Claude 明確要求「請實看評估」，所以先用真實資料（84 篇／10 天）跑過一次熱門與省錢兩個視圖再動手
- 任務資料夾用完即刪（`Desktop\automation\Playwright\ptt_assistant_ui_check\`），不留一次性截圖殘留

### 整體協調性檢視
- 退一步看整張畫面：4 個新元素分別落在「結果區上緣控制列」「卡片內」「視窗右下角」三處既有骨架位置，沒有新開版面、沒有加新的功能入口，方向正確。
- **實測發現的真實問題（不是憑空猜的）**：用 Playwright 量測 `#results-head` 在熱門結果（`#day-filter` 與 `#sort-toggle` 同時出現）的 bounding box，desktop 848px 容器下第一行剛好塞滿「共 N 篇＋範圍凹槽＋排序凹槽＋過濾輸入框」，`.export-actions`（含留言＋下載）正確 wrap 到第二行並靠右對齊（`margin-left:auto` 運作正常，這是好消息，v2.2 那版的分組設計禁得起本輪疊加考驗）。但截圖比對後發現：`#day-filter` 與 `#sort-toggle` 兩個凹槽控制項的底色 `--chip`（#eef1f4）跟頁面背景 `--bg`（#f4f5f7）幾乎同色，肉眼幾乎看不到凹槽的邊界，兩組並排時視覺上融成一長串文字按鈕（「範圍 1天 3天 5天 10天 排序 正在起飛 總留言數 最新」），這正是題目提醒的「擁擠感」的真正成因——不是控制項數量本身有問題（每個都有清楚文字標籤，功能上不重疊），而是**視覺容器對比不足，導致本來該分成兩組的控制項讀起來像一組**。這是本輪必須處理、且屬於「局部協調性修整」（配色/層次）範圍，可以直接動手，不必上呈討論。
- 這是**順手收斂而非硬塞**：沒有新增任何按鈕或欄位，只調整既有 token 對比與間距，讓「同時出現的兩個凹槽控制項」讀起來清楚分家。同時這個修法是**系統級**（改 `--chip` 這個共用 token），連帶讓 `.views` 主導覽軌道、`#cat-tabs` 用不到但同色系的其他凹槽元件全部一起變清楚，不是只治標本輪這一處。
- `.item-actions`（顯示摘要／置頂／轉傳）與 `.badge-pin`：實機截圖確認三個文字按鈕之間有 `--space-3`（12px）間距，足以避免手機誤觸相鄰按鈕；`.badge-pin` 用中性 `--chip`／`--ink-2` 配色（不是 accent 或 warn），跟 `.badge-new`（藍）並列時語意不會互相干擾，維持既定的「新舊徽章都是次強調、不搶標題」語言。這部分結構本身做得對，沒有需要收斂之處。
- `#to-top`：桌面與 375px 實測皆確認固定在視窗角落、只在捲動 600px 後出現、44×44 符合觸控下限、不阻擋卡片內任何互動元素（卡片內文字/按鈕在其覆蓋範圍外或僅覆蓋卡片右側留白）。依「最不干擾」原則做了視覺減重（見下方設計決策），但功能與尺寸完全保留，未移除。
- 沒有發現需要跟主 Claude/Dino 討論的結構性整合建議——本輪都是配色 token 對比與間距層級的局部修整，照協議可以直接做。

### 設計決策
1. **`--chip` 從 `#eef1f4` 調整為 `#e7eaef`**：跟 `--bg`（#f4f5f7）拉開到肉眼可辨的對比，同時跟既有 `--line`（#e3e7ec）色相一致不突兀。理由：Priority 5 佈局準則要求控制項分組要能被感知；這是目前唯一會讓兩個同語彙凹槽控制項並排時清楚分家的方法（比加邊框更輕量，不引入新視覺語言）。影響範圍：`.views` 導覽軌道、`#day-filter`／`#sort-toggle` 凹槽底、`.chip`（比對關鍵字小標籤）、`.badge-pin` 背景——全部一起變清楚，且都在白卡片或淺灰頁面上使用，對比只會提升不會有可讀性風險（`--ink-2` 文字在新底色上實測仍遠高於 4.5:1）。
2. **新增 `#day-filter + #sort-toggle { margin-left: var(--space-2) }`**：用 CSS 結構鄰接選擇器，只在兩者緊鄰出現時疊加額外間距（在既有 flex gap 之上），用「留白」而非邊框把兩組控制項的視覺邊界拉開。選用 margin 而非 border/padding 的原因：margin 不會讓凹槽底色跟著延伸，乾淨地只增加空白間隔，不會製造「灰底裡面又有一條線」的視覺雜訊。已用 Playwright 量測確認加了這 8px 後 `#filter-box`（`flex:1`）自然縮窄吸收多的寬度，不會把 `.export-actions` 推到 wrap 位置改變。
3. **`#to-top` 視覺減重（尺寸/功能不動）**：背景改 `rgba(255,255,255,.88)` + `backdrop-filter: blur(4px)`，陰影從 `0 2px 8px rgba(...,.18)` 降到 `0 2px 6px rgba(...,.14)`，hover 時才轉回不透明白底。理由：呼應「Dino 不喜歡懸浮元件蓋內容」的既有偏好與本輪明確要求「以最不干擾為準則」——既然這是這次明確要的功能、不能拿掉，就把它做得更像「浮在內容上的半透明提示」而不是「一張蓋住東西的實心卡片」。尺寸維持 44×44（觸控下限不能再縮）、位置維持右下角＋捲動 600px 才出現，這兩點是既有／指定規格，未更動。
4. **克制**：沒有新增顏色 token 種類（`--chip` 只調整既有色值,不是新增變數）；沒有給 `.item-actions`／`.badge-pin` 加任何裝飾（維持中性/文字按鈕語言）；沒有把 `#day-filter`／`#sort-toggle` 合併成一個控制項或砍掉其中一個——两者语意不同（时间范围 vs 排序方式），保留双控制项是对的，问题只在视觉分隔，不在数量。

### 產物位置
- 直接編輯（兩份文件改法一致）：
  - `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html` — `:root` 的 `--chip` 色值調整；新增 `#day-filter + #sort-toggle` 規則；`#to-top`／`#to-top:hover` 背景與陰影調整
  - `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\site\index.html` — 同步同一組三處改法
  - 所有既有 `id`／`data-days`／`data-sort`／JS 用到的 class（`day-filter`／`sort-toggle`／`act`／`badge-pin`／`to-top`／`item-actions`／`tab`／`active`）**一律未改名**；`#day-filter`／`#to-top` 的 `display` 顯隱仍完全交給 JS（`style.display`），本輪 CSS 未設定任何 `display` 屬性去蓋過它
- 執行方式：`web/index.html` 照專案既有方式跑 `server.py`（`http://127.0.0.1:8877`），重新整理即可看到效果；`site/index.html` 為靜態唯讀頁，直接開檔或部署後查看即可

### 自審結果（④ 心法）
- a11y：`--chip` 調整後在其上顯示的 `--ink-2` 文字對比只增不減（沿用既有色票公式，未新增色相）；`#day-filter`／`#sort-toggle`／`.item-actions` 內按鈕皆為原生 `<button>`，全域 `button:focus-visible` 規則不受影響；`#to-top` 加 `backdrop-filter` 不影響其 `aria-label="回到最上方"`（既有屬性，本輪未動）。
- 狀態完整度：三個卡片動作按鈕（摘要／置頂／轉傳）與四個天數按鈕的 hover/active/focus 狀態沿用既有 `.tab`／`.act` 規則，齊全；`#to-top` 新增 hover 時背景轉回不透明白底，讓互動反饋比純陰影變化更明確。
- 對比：改動一個既有 token（`--chip`）與新增一組半透明背景（`#to-top`），皆已實機截圖確認可讀性沒有變差、反而更清楚；未引入任何新色相。
- RWD：已用 Playwright 在 1000px 與 375px 兩種寬度實機截圖＋量測 bounding box 確認——桌面下 `#results-head` 第一行剛好塞滿主要控制項、`.export-actions` 正確 wrap 到第二行並靠右；375px 下 `#day-filter`／`#sort-toggle` 各自獨立成行，凹槽底色調整後清楚可辨，不再讀起來像連續文字列；`#to-top` 在兩種寬度下都只覆蓋卡片右側留白，未蓋住任何可互動元素。

### 後續建議
- 給 Ray：建議做一次瀏覽器 regression——重點測「天數篩選」切換後清單/分類頁籤篇數是否正確重算（`renderTabs()`／`applyFilters()` 依 `DAYS` 重跑）、卡片「置頂」「轉傳」按鈕的 localStorage 行為與 `navigator.share`/剪貼簿 fallback、`#to-top` 捲動閾值與平滑捲動。本輪只動 CSS token／間距／背景透明度，理論上不影響任何 click/keydown 邏輯，但建議實測收斂風險。
- 給 Andy：請記錄「`--chip` 對比不足是本輪擁擠感真正成因、非控制項數量問題」這個判斷過程，日後若要再疊加第三個同語彙凹槽控制項到同一排，優先檢查底色對比與鄰接間距，而不是急著砍功能或改版面。
- 給 Bevis：目前置頂項會略過天數/分類/文字三重篩選（永遠顯示在最前），這是既有 JS 邏輯、非本輪改動，若使用者之後反映「置頂的舊文章一直卡在最上面、篩選不掉」，屬於產品行為判斷，麻煩您定奪是否要讓置頂項也吃天數篩選。

---

## hallmark 整頁重設計（2026-08-23：Dino 直評「像拼裝」，授權整頁重做）

### 任務意圖判定
- 屬於 ①/② 混合但以「整頁重設計」為主——Dino 明講這次要「整頁重設計，不是增量修補」，且指名用 `hallmark` skill（已 clone 到本機 scratchpad），不是慣用的 `ui-ux-pro-max`。
- 讀了 `hallmark` 的 `SKILL.md` 與 `references/verbs/redesign.md`：判定屬於 **multi-page 重設計流程**（兩個檔案要共用同一套視覺語言，命中 redesign.md § Step 0 的「使用者點名一個以上檔案」訊號）→ 先立 `design.md`（見專案根目錄 `design.md`），再套用到兩份頁面，而不是各自獨立挑色/挑字。
- 額外載入 `references/genres/modern-minimal.md`、`typography.md`、`layout-and-space.md`、`color.md`、`anti-patterns.md`、`responsive.md`、`macrostructures.md`（索引）、`slop-test.md`（前 120 行，收斂 gate 清單）——未載入 nav/footer 的 `component-cookbook.md` 全文，因為判定這兩份頁面不是行銷頁，N1–N13／Ft1–Ft8 archetype 不適用（見下方「巨觀結構判定」），只挑讀了 genre 檔裡的 nav/footer 段落確認這個判斷站得住。
- 未使用代替方案；`hallmark` 是這次任務指定的容器內 clone skill，非容器內建包，路徑見 prompt 給的 scratchpad 位置。

### 整體協調性檢視
- 退一步看整張畫面（不是只盯著結果區）：Dino 的「像拼裝」直評精準——十幾輪 `ui-ux-pro-max` 局部審查每次都對，但每次都是「這一小塊要不要收斂」的局部判斷，沒有一次重新問「整張畫面的骨架是不是該重排」。累積結果：結果區頭部三段控制項（看板 chips／分類 chips／範圍+排序+搜尋+匯出）雖然每段內部都做對了（凹槽 vs outline pill 語彙分清楚、觸控熱區夠、對比夠），但三段之間**沒有共同的容器**——各自浮在頁面背景上，靠零散的 `margin-bottom` 隔開，讀起來像三張各自為政的工具條，不是一個系統。這正是「local 都對、global 不對」的典型徵狀，也是為什麼要授權整頁重做而不是繼續局部修。
- **這次是重排而非硬塞**：核心改動是把 `#note` / `#board-filter` / `#cat-tabs` / `#results-head`（`web/`）或 `#head`（`site/`）/ `#export-path` 全部收進一個新增的 `.results-toolbar` 面板容器（帶邊框、陰影、內距），並把 `#board-filter` 與 `#cat-tabs` 再包進 `.filter-groups`（flex 容器，兩者盡量併成同一行、擠不下才各自換行）。這個改動**沒有新增任何按鈕、欄位、或功能**，純粹是「原本就存在的資訊該用什麼容器裝」的骨架問題——完全符合 Dino 要求的「先看整張畫面該怎麼組織，不是把新東西塞進角落」。
- 同時把整站配色/字體/圓角/陰影/間距重新收攏進 `design.md` 定義的單一系統（見下方設計決策），不是零散 hex/px。這是本輪跟過去六輪最大的差異：過去六輪是「在既有 token 上修補」，這次是「重新鑄造 token 系統」，因為累積下來的 `--bg`/`--surface`/`--ink` 等零散 hex 變數已經無法再靠局部修補讓畫面「一眼協調」——這也是「能用不等於協調」的具體案例。
- **巨觀結構判定（明講偏離 hallmark 預設）**：hallmark 的 21 個 macrostructure 全部是「行銷頁形狀」（hero/feature grid/pricing…），這兩份檔案是使用者真正在操作的工具（表單→掃描→結果），21 選 1 硬套只會產生語意錯誤的骨架（例如逼自己塞一個「Hero」進一個掃描表單頁）。依 `custom-theme.md` § Bespoke depth 的允許條件（brief 的結構本身就不合任何 catalog macrostructure），採用 **bespoke 深度**：只借用 hallmark 的字體/色彩/間距/狀態/防 AI 味紀律，結構維持「條件表單→進度→結果」這個工具頁本來就對的骨架，**不強冠 nav（N1–N13）／footer（Ft1–Ft8）archetype 代號**——`.views` 功能頁籤本質上是 app 內的分頁切換，不是行銷網站的頂部導覽；頁尾維持一行免責聲明（語言上接近 Ft2 inline，但不用行銷頁尾的「product/company/resources」欄位邏輯）。這個判定已寫進 `design.md` 開頭，供之後任何人接手時知道「為什麼沒有 nav archetype 代號」。
- 沒有發現需要跟主 Claude/Dino 討論的**新的**結構性整合建議——這次授權的重設計已經是最大幅度的結構收斂（三段控制項→一個面板），沒有留下需要進一步整合的按鍵/入口。

### 設計決策
1. **Genre：modern-minimal**（Stripe/Linear 學派的工具調性）。訊號：這是資料掃描工具（dashboard/dev-tool 感），命中 hallmark genre 偵測的 platform/dev-tool 類；不是 atmospheric（沒有暗色氛圍需求）也不是 playful（不是消費性/娛樂內容）。
2. **Palette：延續既有 teal 品牌色（hue≈166），但重鑄成完整 OKLCH 四層調色盤**（paper/ink/neutral/accent，見 `design.md`）。理由：舊版 `--accent:#2f6f5e` 是前六輪刻意選定並算過對比的品牌色，不是隨手預設藍紫，依 hallmark redesign 規則「保留使用者已命名的品牌色」延續色相；但改用 OKLCH 建構後，`--bg`/`--surface`/`--chip` 等中性色第一次有系統性的色相帶入（原本是零散挑的灰階 hex，跟 accent 的暖冷關係是巧合不是設計），現在全部往 166° teal 微調，符合 `color.md`「neutrals 要往 anchor hue 帶」的紀律。
3. **Typography：2+1 規則的務實折衷**——display 用 Space Grotesk（Google Fonts + 系統字 fallback，只吃英數字元）、body 維持系統 CJK 無襯線堆疊（不是 hallmark 預設的 Geist/Switzer 等 Latin 字體）、outlier 用 JetBrains Mono（僅用於 `#log` 與數字 `tabular-nums` 兩個角色）。**明講偏離**：body 用系統字而非 Google Fonts 是刻意的，因為內容幾乎全繁中，Latin body 字體對中文零效果、只會多一個離線失敗風險，不符合 Dino「本機版可能離線」的硬性限制——這是「查證後的偏離」，不是偷懶沒查 hallmark 規則。
4. **結果工具列重排（本輪核心）**：新增 `.results-toolbar`（面板容器：邊框/陰影/內距）與 `.filter-groups`（flex 併行容器）兩個純附加的 wrapper `<div>`，把既有 `#note`/`#board-filter`/`#cat-tabs`/`#results-head`（或 `#head`）/`#export-path` 收進去。**零 JS 改動**——所有 `id`、JS 用到的 `class`（`viewbtn`/`active`/`view`/`tab`/`track`/`run`/`del`/`name`/`clickable`/`cachetime`/`runbtn`/`item`/`open`/`preview`/`toggle`/`chip`/`chips`/`meta`/`meta-metric`/`card`/`empty`/`error`/`badge-new`/`badge-pin`/`item-actions`/`act`/`checkline`/`sort-label`）與 `data-view`/`data-days`/`data-sort` 屬性**逐一核對**，只加外層包裝、不改名不刪除。
5. **狀態紀律補齊**：全部互動元素統一 `min-height:44px`（觸控下限，也讓 `.ask` 一排的輸入框跟按鈕高度一致，命中 slop-test gate 39）；補齊 `:active`（`.viewbtn`/`.tab`/`button.primary`/`button.ghost`/`.track button.run`/`#to-top`/`.act`/`.toggle`）；全域 `prefers-reduced-motion: reduce` 降級（前六輪都沒補這個，這次一併補上）；`html`/`body` 加 `overflow-x: clip`（slop-test gate 34 的硬性防線，前六輪也沒有，這次補上）。
6. **搜尋圖示（唯一新增的裝飾元素）**：`#ask-input` 與 `#filter-box` 補上同一顆手繪 SVG 放大鏡（data URI background-image，非圖示字型/emoji），維持「同一套圖示語彙只用一次角色（搜尋類輸入框）」的紀律，不擴散到其他地方。
7. **克制**：沒有加漸層、玻璃感、裝飾色塊、圖示字型、emoji；沒有新增第三種按鈕語言（仍只有 primary/ghost 兩級）；沒有把 `.views` 或 `#sort-toggle`/`#day-filter` 這兩套已經分清楚語彙的控制項再改造——這兩套是前幾輪已經打磨對的部分，這次原樣沿用只套新色票，沒有為了「整頁重設計」而動不需要動的東西。

### 產物位置
- `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html`——`<style>` 區塊全面重寫（新 token 系統）；`<body>` 只動兩處：① `header.site` 內加 `.mark` 色塊 + `.head-text` 包裝；② `#results` 內把既有子元素收進新增的 `.results-toolbar` / `.filter-groups` 包裝。`<script>` 區塊逐行核對後**完全未動**。
- `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\site\index.html`——同一套改法（`<style>` 重寫＋`header`/`.results-toolbar`／`.filter-groups` 包裝），`<script>` 未動。
- `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\design.md`（新建，專案根目錄）——鎖定的設計系統，記載 genre/palette/typography/spacing/motion/CTA voice/巨觀結構判定，之後任何人改這兩份頁面先讀這份。
- 執行方式：`web/index.html` 照舊跑 `server.py`（`http://127.0.0.1:8877`）；`site/index.html` 為靜態頁，建議用 http server 開（本輪用 `file://` 直接開檔測試時 `fetch()` 因瀏覽器同源限制會失敗顯示「載入失敗」，這是測試方法本身的限制，不是本輪改動造成，部署後走 http(s) 正常）。

### 自審結果（④ 心法 + hallmark slop-test 自評）
- **三套行為測試全綠**（Playwright 實機跑，非猜測）：
  - `tests/verify_v21.py`——ALL PASS（開頁即看快取、分類頁籤過濾、天數篩選單調性、置頂跳位、回頂、熱門排序遞減、看板自選隱藏/還原、白話解析導向、批次下載含留言 TXT）
  - `tests/verify_ui.py`——ALL PASS（白話解析導向進階頁、真實掃描、結果過濾歸零/還原、內文摘要展開）
  - `tests/verify_guard.py`——ALL PASS（掃描中所有 `.runbtn` 停用、原掃描正常完成並自動切回）
- **RWD**：額外用 Playwright 在 375px 寬度截圖 money/hot/advanced 三個功能頁與 `site/index.html`，四張截圖 `document.documentElement.scrollWidth` 均為 375（無橫向溢出，命中 slop-test gate 34）；`.views` 頁籤在窄螢幕自然換行、每顆按鈕文字仍單行不斷行（命中 gate 49）；`.track .name` 這種說明性文字換兩行不算違規（非按鈕/CTA/導覽連結）。
- **a11y**：全域 `:focus-visible` 用 `outline`（非 `border`，不擠壓版面，命中 gate 39）、2px `--color-focus`，不 transition（鍵盤使用者立即可見，命中 slop-test 第 15 條）；三態齊全（hover/focus-visible/active/disabled，disabled 三通道：opacity+cursor+原生屬性）；對比沿用既有已算過的色相結構重鑄成 OKLCH，肉眼實測（見截圖）文字對比清楚無washed-out 情形。
- **對比**：新色票用 OKLCH 明度差重新核算（accent 41% L vs 白系卡片 99%、ink 24% L vs bg 97%，明度差均遠超 50% 的快篩門檻），未做 APCA 精算工具驗證，但明度差幅度遠超過原本已通過 AA 4.5:1 的舊版色票結構，風險評估為低。
- **hallmark slop-test 自評**（前 40 條逐項對照，非全 58 條逐一列出但涵蓋所有高風險項）：無漸層／無 Inter-everywhere（用 Space Grotesk+CJK 系統字配對）／無 3 欄 icon 卡／無 card-in-card／無側邊色條卡片／無純黑純白（modern-minimal genre 允許純白但仍用微 tint 的 oklch）／有 macrostructure 判定聲明（bespoke，理由見上）／無 `transition:all`／無彈跳 easing／focus ring 不淡入／無慶祝式 toast／無佔位人名/新創陳詞／無 zero-chroma 中性色／accent 佔比遠低於 5%／間距全部在 4px 刻度上／`overflow-x:clip` 已加／reduced-motion 已加／字體家族數＝3（display+body+mono outlier，未逾三；outlier 僅 2 個角色未逾 2 槽）／無斜體標題／輸入框狀態齊全（`min-height:44px` 統一、outline 而非 border 做 focus、disabled 三通道）。**已知遺留、非本輪範圍**：APCA 精算與深色模式未做（Dino 本次任務明講「深色模式不要求」）。

### 後續建議
- 給 Bevis：本輪為視覺/資訊架構重排，未變更任何功能或掃描邏輯，若後續要新增第 5 個功能頁，設計上已預留骨架（`.views` 頁籤 + `.results-toolbar` 面板可直接沿用），建議新功能上線前提醒我一併檢查是否要沿用同一套結果工具列。
- 給 Ray：建議針對 `site/index.html` 補一次「用 http server（不是 file://）開啟」的 regression，確認 `fetch("data/money.json")` 在真實部署路徑下正常，本輪只用 `file://` 快速視覺檢查、已知這個限制不是本輪改動造成。

---

## 全文閱讀器增量審查（2026-08-23：長文＋百則留言在卡片內捲動的體驗）

### 任務意圖判定
- 屬於 ④ 審查（增量）：hallmark 整頁重設計已鎖定 `design.md` 的系統，這次只審「新加入的全文閱讀器」（`.preview` 內捲容器：`.art-body`/`.art-line`/`.art-img`/`.art-comments-head`/`.cmt` 留言列）有沒有融入既有系統，不重新挑色/挑字/開新版面。
- 硬性先載入 `ui-ux-pro-max`（容器內正版，未用代替方案），對照其 Quick Reference 逐項核對：Priority 5（Layout & Responsive）`scroll-behavior`/`horizontal-scroll`、Priority 6（Typography & Color）`line-height`/`line-length`、Priority 2（Touch）`touch-spacing`。
- 用 Playwright 實機開 `http://127.0.0.1:8877`（熱門頁，真實案例：留言 139、每小時 3.3 那則），量測 DOM 尺寸與截圖，不是憑印象猜；另外用 `python -m http.server` 起了 `site/` 的臨時伺服器，找到另一則留言 124 的案例交叉核對兩檔一致。

### 整體協調性檢視
- 退一步看整張畫面：全文閱讀器是**既有 `.preview` 內捲容器裡新長出來的內容**（原本只有純文字 `pre.textContent`），沒有新開版面、沒有新增按鍵入口——`.toggle`「閱讀全文」按鈕與 `.item-actions` 動作列都是原本就有的，這次只審內容本身的排版。沒有需要跟主 Claude 討論的結構整合建議。
- 樓層欄對齊：實測量了 1F／9F／139F 三種位數，`.cmt-floor{min-width:36px}` 已經讓後面的 tag 欄一律從同一個 x 座標起排（36px 固定框，位數不同不影響），**這部分原本就做對，不需要改**——這是先量測再動手才發現「以為有問題、其實沒問題」的案例，避免了不必要的改動。
- 真正需要收斂的是兩處「新元素沒接上既有 4px 間距刻度」的地方：`.cmt` 用了 `gap:6px`／`padding:3px 0`（6、3 都不在 `--space-1..9` 的 4px 刻度上），`.art-img` 的 `margin:var(--space-2)` 對一張整段寬度的貼圖來說太窄、且完全沒有框線把外站圖床的雜色圖片收進卡片語彙——這兩處判定為「順手收斂進既有系統」，不是新增裝飾。
- 手機 375px 是本輪發現的真正体验缺口：目前的 flex-wrap 會把「時間」欄擠成留言區塊的孤立第三行（樓層/標籤/作者一行、內文一行、時間又自己一行），跟內文脫節。用既有的 `@media (max-width: 26.25rem)`（`web/index.html` 本來就有這個斷點，`site/index.html` 之前沒有、這次補上同一個值，維持兩檔斷點值統一不漂移）搭配 CSS `order` 把時間挪到「樓層/標籤/作者」那一行、靠右對齊收尾，內文改成獨立整行、用 hanging indent 對齊作者欄——**只動 CSS `order`／`margin`／`padding`，DOM 順序、`createElement`/`textContent` 邏輯完全沒有動**。

### 設計決策
1. **`.cmt` 間距併回 4px 刻度**：`gap:6px→var(--space-2)`、`padding:3px 0→var(--space-1) 0`。理由：Layout & Responsive 的 `spacing-scale` 準則要求 4/8px 遞增系統；139 列乘上來的高度差可忽略（多約 140px 內容，於 72vh 內捲容器裡不影響可視密度）。
2. **`.art-img` 留白升一階＋補框線**：`margin:var(--space-2)→var(--space-3)`，並加 `border:1px solid var(--color-line)`。理由：圖片是內文中最重的元素（面積遠大於一行文字），留白理應比文字行距寬一階才不會貼著鄰行文字（Typography & Color `whitespace-balance`）；外站圖床貼圖（本例是白底表格截圖）原本直接漂在 `--color-surface-2` 背景上邊界模糊，加一條細框線把它收進跟 `.item` 卡片同一套「有邊界的容器」語彙，不是新發明的視覺語言。
3. **`.preview` 加 `overscroll-behavior: contain`**：直接回應題目點名的「72vh 內捲與頁面捲動的雙捲軸感受」。用 Playwright 實測驗證：把內捲容器滑到最底後持續在原地滾動 10 次，`window.scrollY` 前後完全不變（858→858）——確認滾動動能不會從內捲容器「溢出」帶動外層頁面，這正是雙捲軸最惱人的症狀（滑到底卻不知不覺把整頁往下拖）。這行 CSS 不改變任何版面，是純行為修正。
4. **手機（≤26.25rem）留言列重排，只用 flex `order`，不碰 DOM**：`.cmt-time{order:1; margin-left:auto}`、`.cmt-content{order:2; flex:1 1 100%; box-sizing:border-box; padding-left:calc(36px + var(--space-2))}`。效果：樓層/標籤/作者/時間留在同一條「標頭列」（時間靠右對齊收尾，呼應桌面版「內文後面接時間」的資訊順位，只是窄螢幕改成標頭尾端），內文另起一整行、用 44px（36px 樓層寬 + 一格間距）hanging indent 對齊作者欄，取代原本「內文、時間各自孤立成一行」的預設 flex-wrap 結果。`site/index.html` 原本沒有 26.25rem 斷點，這次新增時特別沿用 `web/index.html` 已經在用的同一個數值（不是另訂一個新斷點），避免兩檔漂移。
5. **克制**：沒有加 scroll fade／漸層陰影去暗示「還有更多內容可捲」——技術上可行（多重 background-image 的 scroll-shadow 手法），但需要精準抓 `--color-surface-2` 色值疊層，出錯風險（露出接縫或色差）大於帶來的效益，且 design.md 沒有這個視覺語彙，判定為「為了炫技加裝飾」而捨棄；沒有改用 CSS Grid 重寫 `.cmt` 版面（原本 flex + order 就能達到效果，沒必要換一套佈局技術製造新的維護成本）；沒有加 zebra 條紋背景（既有 dashed border-bottom 已經足夠分隔 139 列，加背景色會是視覺上多一層裝飾）。

### 產物位置
- `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html`——`.preview`／`.art-img`／`.cmt` 三處 CSS 規則微調；`@media (max-width: 26.25rem)` 既有區塊內新增 `.cmt-time`／`.cmt-content` 兩條規則。
- `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\site\index.html`——同一組 CSS 改法；另新增 `@media (max-width: 26.25rem)` 區塊（原本沒有），只放這次的 `.cmt-time`/`.cmt-content` 兩條規則。
- 兩檔的 `<script>` 區塊、`id`、JS 用到的 class（`preview`/`toggle`/`open`/`art-body`/`art-line`/`art-img`/`art-comments-head`/`cmt`/`cmt-floor`/`cmt-tag`/`push`/`boo`/`arrow`/`cmt-user`/`cmt-content`/`cmt-time`）與 `createElement`/`textContent` 渲染邏輯**逐行核對後完全未動**。
- 執行方式：`web/index.html` 照舊跑 `server.py`（`http://127.0.0.1:8877`）；`site/index.html` 建議用 http server 開（`file://` 會因 `fetch()` 同源限制載入失敗，跟本輪改動無關，屬既有已知限制）。

### 自審結果（④ 心法）
- a11y：本輪未動任何色值，`.cmt-tag.push`/`.boo`/`.arrow` 沿用既有色彩系統（沒有只靠顏色傳達推/噓/→，本來就有文字本身「推」「噓」「→」作為第二訊號，符合 `color-not-only`）；`.preview` 目前仍無 `tabindex`，鍵盤使用者無法用方向鍵單獨捲動這個內捲區（只能用 Tab 走到裡面的連結/圖片再用瀏覽器內建捲動），這屬於要動 JS 屬性的範圍，本輪依指示只改 CSS，**留給後續**（見下方建議）。
- 狀態完整度：留言列本身無互動狀態（純顯示），不適用 hover/focus 檢核；`.art-line` 裡的連結沿用全域 `a` 的 hover/focus 樣式，未動。
- RWD：Playwright 實測 375px 寬度，`document.documentElement.scrollWidth` 恆為 375（無橫向溢出）；用真實留言（含「IP+時間」這種異常長的 time 內容，`site/` 熱門頁一則留言 124 的案例）壓力測試——這種案例下標頭列（樓層/標籤/作者/時間）會因塞不下而自行再折成兩行，但不會溢出版面、不會截斷文字，屬於可接受的邊界退化，比改動前「每一列都固定三行」是進步而非退步。
- 對比：`.cmt-floor`/`.cmt-time` 用既有 `--color-ink-2` 對 `--color-surface-2` 背景，色值本輪未變動，沿用先前已核算過的 OKLCH 明度差。

### 後續建議
- 給 Zavier：若之後要補鍵盤可捲動性（`.preview` 加 `tabindex="0"` 讓鍵盤使用者能直接方向鍵捲動內捲區），需要動 JS（`pre.className = "preview"` 那行旁補一個屬性設定），這超出本輪「只改 CSS」的授權範圍，麻煩之後排時間補上。
- 給 Ray：建議做一次瀏覽器 regression，重點測「閱讀全文」展開/收合、內捲區域捲動（含滑到底部再滾動確認不會拖動外層頁面）、375px 下留言列不因這次的 `order` 改動而看起來斷裂或跳位——本輪只動 CSS，理論上不影響任何 click/fetch 邏輯，但建議實測收斂風險。
- 給 Andy：請記錄「樓層欄其實本來就對齊、不需要動」與「間距沒接上 4px 刻度、雙捲軸靠 `overscroll-behavior:contain` 而非改版面結構」這兩個判斷過程，日後若再有人覺得留言列「看起來很擠」，先量測（如本輪用 Playwright 抓 boundingClientRect）再決定要不要動,不要憑印象重排。
- 給 Andy：請記錄本輪「從六輪局部修補轉為 hallmark 整頁重設計」的判斷分水嶺（累積的零散 token 已無法靠局部修補達成協調，需要重鑄系統）、以及 `design.md` 這個新的單一事實來源上線，之後任何人改這兩份頁面的視覺，優先讀 `design.md` 而非直接讀 CSS 猜規則。

## 篩選面板精修（2026-08-23：Dino 反映「按鈕太多，很難理解」後，主線已收斂 IA，這輪做視覺精修）

### 任務意圖判定
- 屬於 ②顧問（既有畫面已收斂完 IA，要把 `#filter-panel` 展開後的視覺品質、`#filter-btn` 的層級與過渡拉到專業水準），沿用 `design.md` 鎖定的 hallmark 系統，不引入新色票/新字體/新語彙。
- 硬性先載入 `ui-ux-pro-max`（容器內正版，未用代替方案），對照 Quick Reference：Priority 5（Layout & Responsive）`visual-hierarchy`/`spacing-scale`、Priority 6（Typography & Color）`weight-hierarchy`、Priority 7（Animation）`state-transition`/`reduced-motion`、Priority 1（Accessibility）`focus-states`。
- 用 Playwright 對兩份檔案（`web/index.html` 走既有 `http://127.0.0.1:8877`；`site/index.html` 額外起 `python -m http.server 8899` 本機臨時伺服器，因為它靠 `fetch()` 讀本地 json，`file://` 會被同源限制擋掉）分別在 1280px 與 375px 兩種寬度、money／hot 兩種資料形態下實測截圖比對，不是憑印象改。

### 整體協調性檢視
- 退一步看整張畫面：這次「新東西」是使用者展開 `#filter-panel` 後看到的五組控制項（模式／範圍／排序／看板／下載），本來就有、不是新加功能，問題是它們原本只是**單純 column 堆疊**、彼此看不出關係、且其中「模式」（`#mode-toggle`）跟「看板」用的視覺語彙（外框 pill）跟「範圍」「排序」（凹槽分段控制）不一致——同一層級的設定用了兩套不同形狀語言，這正是「局部湊功能、沒顧整體」的典型症狀。
- 判定為**順手重排讓整體更乾淨**，不是硬塞：把 `#filter-panel` 從 `flex-direction: column` 改成 `flex-flow: row wrap`，讓「模式／範圍／排序」這幾顆天然較窄的控制項在桌面寬度足夠時自然併到同一行（實測 1280px 下三組會擠上同一行），只有較寬的看板列表、需要獨立呼吸的下載動作才會自己起新的一行——這不是新發明的分組結構，是讓 CSS flex-wrap 順著內容寬度自然产生分組節奏，比手動幫五組各自畫框更克制。窄螢幕（375px）因為每組內容本身已經比可視寬度寬，天然還是退化回一行一組，不受影響、不會變差。
- 沒有發現需要動結構、需要跟主 Claude 討論的按鍵整合案——五組控制項全部保留、位置不變，這輪只動「同一批控制項之間的視覺關係」，不是砍功能或搬入口。

### 設計決策
1. **模式／範圍／排序統一成同一種「凹槽＋實色滑塊」語彙**：原本只有 `#sort-toggle`/`#day-filter` 用這套分段控制樣式並帶 `.sort-label`（範圍／排序），`#mode-toggle` 卻沿用外框 pill 樣式、也沒有標籤（兩顆按鈕「近期熱門」「含回鍋」讓人一時看不出這是一組單選設定還是兩顆獨立分類）。這次把 `#mode-toggle` 併入同一組選擇器、並在 HTML 補一個 `<span class="sort-label">模式</span>`——三組現在完全同語彙同對齊，使用者掃視時能立刻辨認「這排都是單選設定」。`#board-filter` 刻意不補標籤：它的收合鈕文字本身就是「看板篩選（N 板）」，已經自帶標籤語意，重複加會是贅字。
2. **`#filter-btn` 改成獨立完整樣式，不再依賴 `.ghost`/`.tab`**：審查時發現 `web/index.html` 用 `class="ghost"`（矩形、`--radius` 12px）、`site/index.html` 用 `class="tab"`（膠囊、`--radius-pill`）——兩份「應視覺一致」的頁面同一顆按鈕形狀不同，判定為未察覺的漂移，這次補齊。改用完整的 id 層級樣式，圓角改採 `--radius-sm`（8px）跟緊鄰的 `#filter-box` 對齊，讓兩者同排時圓角呼應、視覺權重相稱；`has-active` 從「只變邊框色」升級成 `background:accent-soft`（沿用 `.tab.active`/`.note` 已有的淡底語彙，不是新色），非預設篩選時更容易被瞄到。
3. **展開/收合加過渡，尊重 reduced-motion**：`#filter-panel` 加 `opacity`/`transform` 過渡＋`display ... allow-discrete`／`@starting-style`（CSS Transitions Level 2 標準寫法，展開時從上方 4px 處淡入，不需要動 JS 的 `style.display` 邏輯，該行為完全沿用）；不支援的舊瀏覽器會直接忽略這組宣告、退化成原本的瞬間開合，不會壞。已用 Playwright `emulate_media(reduced_motion="reduce")` 實測：開啟後 100ms 內面板 `opacity` 已是 `1`、子項目已可見，確認全域既有的 `prefers-reduced-motion` 規則正確覆蓋到這裡。
4. **`.export-actions` 補回左側分隔線**：審查時發現桌面版原本完全沒有這條分隔線的宣告，但既有的 375px 媒體查詢卻在「重設」`margin-left:0;padding-left:0;border-left:0`——這三個屬性在桌面版根本沒被設定過，是死程式碼/遺留斷點，判定為先前修改時漏補的桌面基準值。這次補上 `margin-left`/`padding-left`/`border-left`，讓「下載」這個動作跟前面的篩選 chips 有清楚的分隔，尤其省錢頁面板內原本只有「範圍＋下載」兩組、容易顯得單薄，這條分隔線讓它讀起來是「範圍 | 下載」兩段式，不是空蕩蕩的一排。
5. **空狀態補成虛線卡片**：`#no-data`（功能頁尚未有資料）與 `#items .empty`（過濾後 0 篇）原本只是一行裸灰字，這次統一收進跟 `#filter-panel` 頂端已建立的「虛線＝次要／暫時性邊界」語彙一致的卡片（`border:1px dashed`、置中、`--space-8` 留白），讓「沒有資料」看起來是設計過的狀態，不是漏畫。
6. **375px 搜尋框＋篩選鈕同排**：實測發現改動前兩份頁面在窄螢幕下「篩選」鈕會被擠到搜尋框下面自成一行（`web` 甚至因為 `#filter-box{flex-basis:100%}` 的舊規則逼搜尋框強制滿版、把篩選鈕擠到第三行）。這次移除該強制滿版規則、把 `#filter-box` 的 mobile 最小寬度從 160px 降到 120px，並讓次要的「共 N 篇」計數用 `order:3;flex-basis:100%` 排到自己整行——搜尋框＋篩選鈕現在窄螢幕也維持同排，跟桌面行為一致；`site/index.html` 原本連這個媒體查詢區塊都沒有對應規則，這次一併補上同一組值，避免兩份頁面再度漂移。
7. **克制**：沒有幫每組控制項加背景框/ 卡中卡（會製造裝飾感、跟 hallmark「無裝飾、靠留白與字重分層」的方向衝突）；`#board-filter` 沒有勉強套用「凹槽分段」樣式（它是多選、非分段單選，維持外框 pill 語彙才符合語意，不是為了「統一」而錯誤統一）；沒有加箭頭圖示/rotate 動畫在 `#filter-btn` 上——JS 本身已把展開/收合狀態寫進按鈕文字（`▾`/`▴`），CSS 加圖示會跟文字內容打架，違反鐵則也是多餘裝飾。

### 產物位置
- `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\web\index.html`——`<style>` 內：分段控制選擇器群組（併入 `#mode-toggle`）、`#filter-btn`／`.has-active`、`#filter-panel`（含 `@starting-style`）、`.export-actions`、`#no-data`、`#items .empty`、`@media (max-width:26.25rem)` 內 `#results-head`/`#filter-box` 幾條規則；`<body>` 內僅在 `#mode-toggle` 加一個 `<span class="sort-label">模式</span>`。
- `C:\Users\AG_Di\Desktop\automation\Claude_code\side_project\PTT_Assistant\site\index.html`——同一組 CSS 改法（含新增的 mobile `#count`/`#filter-box` 規則，原本這個檔案的媒體查詢區塊沒有對應項目）；`<body>` 同樣補 `#mode-toggle` 的 `模式` 標籤。
- 兩份檔案的 `<script>`、所有 `id`/`class`/`data-*`（`filter-btn`/`filter-panel`/`has-active`/`mode-toggle`/`day-filter`/`sort-toggle`/`board-filter`/`bf-toggle`/`export-actions`/`dl-comments`/`btn-export` 等）與事件綁定邏輯**逐行核對後完全未動**；`#filter-panel` 的 `display` 仍完全由 JS 控制（flex/none），CSS 只加了不影響該屬性判讀的 opacity/transform 過渡。
- 執行方式：`web/index.html` 照舊跑既有 server（`http://127.0.0.1:8877`）；`site/index.html` 本機測試需自起靜態伺服器（如 `python -m http.server`），`file://` 會因 `fetch()` 同源限制載入失敗，屬既有已知限制、與本輪改動無關。

### 自審結果（④ 心法）
- a11y：`#filter-btn` 鍵盤 Tab 順序、focus ring 皆已用 Playwright 實測（`#filter-box` → Tab → 落在 `#filter-btn`，且沿用全域 `:focus-visible` accent 外框，實測截圖可見清楚的外框）；色彩沿用既有已核算過對比的 token，未新增色值。
- 狀態完整度：`#filter-btn` 新補 `hover`/`active`/`has-active` 三態（原本只有 `has-active` 一種），過渡沿用全域 `button{transition:...}`；`#filter-panel` 展開/收合過渡已測試一般模式與 `prefers-reduced-motion:reduce` 兩種情境皆正常。
- RWD：375px 下 money／hot 兩種資料型態（僅範圍＋下載 vs. 五組全開）皆已截圖核對，未爆版、搜尋框＋篩選鈕同排、看板膠囊多列自然換行不受影響。
- 對比：`has-active` 新用的 `--color-accent-soft` 背景是既有 token（`.tab.active`/`.note` 已在用），未新增顏色，無需重新算對比。
- 測試：`tests/verify_v21.py` 於改動前後各跑一次皆為 `ALL PASS`（含篩選面板展開收合、天數/排序/看板篩選、批次下載等既有斷言）。

### 後續建議
- 給 Ray：建議針對 `#filter-panel` 展開/收合、`#mode-toggle` 新標籤不影響既有 `.tab` 點擊事件、`.export-actions` 分隔線在各種資料形態下不同排列組合，跑一次瀏覽器 regression——本輪只動 CSS/新增一個不帶 `.tab` class 的 `<span>`，理論上零風險，但建議實測收斂。
- 給 Andy：請記錄「`.export-actions` 桌面基準值遺失、被 mobile 媒體查詢重設一個從未存在的值」這個案例——這是「改動時只顧局部（加 mobile 覆寫）、沒回頭確認桌面基準是否真的定義過」的具體教訓，日後審查 CSS 覆寫規則時可以此為例。
- 給 Bevis：這次調整純粹是視覺精修，沒有動任何資訊架構或功能，不影響產品方向判斷，僅供備查。
