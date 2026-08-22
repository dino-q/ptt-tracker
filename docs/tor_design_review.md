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
