# Design — PTT 追蹤助手

鎖定的設計系統。`web/index.html`（本機完整版，四功能頁）與 `site/index.html`
（線上唯讀版，兩功能頁）共用同一套系統。兩份檔案各自把 token 內嵌在自己的
`<style>` 區塊（不共用外部 css 檔）——`site/` 是獨立部署的靜態頁面，`web/` 要
在離線環境可跑，各自內嵌可避免額外的網路依賴或部署路徑耦合；日後任一份要調整
視覺，先改這份 `design.md` 再套用到兩邊，避免兩邊各自漂移。

2026-08-23 由 Tor（設計主管）依 Dino 指示、套用 `hallmark` skill 的整頁重設計
流程建立（取代前六輪 `ui-ux-pro-max` 局部審查建立的舊 token）。

## 任務性質：bespoke，不是任一 catalog 巨觀結構

Hallmark 的 21 個 macrostructure 都是「行銷頁形狀」（hero、feature grid、
pricing、footer…）。這兩份檔案是**真正在跑的工具介面**（表單 → 掃描 → 結果
列表），不是介紹這個工具的行銷頁，21 選 1 硬套只會產生錯誤的骨架。依
`custom-theme.md` § Bespoke depth 的允許條件（結構本身就不合任何 catalog
macrostructure），這次採用 **bespoke 深度**：只借用 hallmark 的字體/色彩/間距/
狀態/防 AI 味紀律，結構由既有的「條件表單 → 進度 → 結果」骨架自然推導,不強行
套用 marketing 的 nav（N1–N13）／footer（Ft1–Ft8）archetype 分類——這點在此明講,
是刻意的偏離,不是漏掉。

## Genre

modern-minimal（Stripe / Linear 學派的工具調性：素色、留白、pill 控制項、單一
克制的 accent）。訊號：這是一個資料工具（scan/dashboard 感），符合 genre
detection 的 "platform / dev-tool" 類。

## 版面骨架（兩檔共用）

1. 頁頭（品牌小色塊 + 標題 + 副標）
2. 白話輸入列（全域快速入口，只在 `web/index.html` 有）
3. 功能頁籤（segmented control，`web/` 4 個、`site/` 2 個）
4. 各功能頁的條件卡片（表單）
5. 進度／掃描日誌（只在 `web/index.html` 有）
6. **結果工具列（本輪核心重排）**：把「看板 chips + 分類 chips + 範圍 + 排序
   + 搜尋 + 匯出」收進同一張 `.results-toolbar` 面板，而不是三段各自漂浮的
   控制項。看板 chips 與分類 chips 現在包在同一個 `.filter-groups` flex 容器
   裡，會盡量併成同一行、空間不夠才各自換行；範圍/排序/搜尋/匯出維持在
   `#results-head`（`web/`）或 `#head`（`site/`）同一列。
7. 結果卡片列表
8. 頁尾（一行免責聲明，Ft2 inline 語言，但不強冠 Ft-code——這是工具頁尾不是
   行銷頁尾）

## Palette（OKLCH，teal 錨點延續既有品牌色）

既有 `--accent:#2f6f5e` 是先前版本刻意選定、並在註解裡算過對比的品牌色
（不是隨手挑的預設藍/紫），依 redesign 規則「保留使用者已命名的品牌色」延續
這個色相（hue ≈166），但重新用 OKLCH 建構完整四層調色盤，不再是零散 hex。

```css
:root {
  --color-bg:          oklch(97.2% 0.006 166);
  --color-surface:     oklch(99.3% 0.002 166);
  --color-surface-2:   oklch(95.8% 0.007 166);
  --color-ink:         oklch(24%   0.014 166);
  --color-ink-2:       oklch(47%   0.013 166);
  --color-line:        oklch(89%   0.008 166);
  --color-chip:        oklch(92.5% 0.010 166);
  --color-accent:      oklch(41%   0.082 166);
  --color-accent-ink:  oklch(98%   0.004 166);
  --color-accent-soft: oklch(92.5% 0.032 166);
  --color-focus:       oklch(56%   0.10  166);
  --color-warn:        oklch(48%   0.115 35);
  --color-new:         oklch(45%   0.100 255);
  --color-new-soft:    oklch(93%   0.028 255);
}
```

accent 只用在：active 狀態、連結 hover、focus ring、`.meta-metric` 熱度數字、
主要按鈕填色——維持 hallmark 色彩紀律「accent 佔比 ≤3–5%」。

## Typography（2+1 規則，內容以繁中為主的務實折衷）

```css
--font-display: "Space Grotesk", "Microsoft JhengHei", "PingFang TC", sans-serif;
--font-body:    "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif;
--font-mono:    "JetBrains Mono", Consolas, monospace;
```

明講一個對 hallmark 預設值的刻意偏離：body 用系統 CJK 無襯線堆疊，不是
Google Fonts 的 Latin 字體（Geist / Switzer 等）。原因——這個頁面內容幾乎全是
繁體中文，任何 Latin 字體對中文字符都不生效（瀏覽器逐字符 fallback），若把
body 硬換成一個 Latin web font，唯一效果是多一個離線會失敗的網路請求、零視覺
差異（中文照樣落到 fallback），不符合「本機版可能離線」的硬性限制。取而代之：
`Space Grotesk`（Google Fonts，帶 `swap` + 系統字 fallback）只吃得到英數字元
（"PTT"、天數字、時間戳、count 數字），中文字自動 fallback 到 JhengHei/
PingFang——用最低成本換到品牌感的英數排版，不冒風險。`JetBrains Mono` 是
outlier，只用在 `#log`（掃描日誌）與數字量測（`tabular-nums`）兩個角色，未逾
2 槽。

## Spacing / Radius / Motion

沿用既有已經在用的 4px 刻度（`--space-1..9`），只補上 `--space-9`；
`--radius:12px`／`--radius-sm:8px`／`--radius-pill:999px`；
`--ease-out: cubic-bezier(.16,1,.3,1)`（hallmark 標準 easing，取代原本泛用
`--ease`）；`--dur-fast/short/med`。

## Microinteractions / 狀態紀律

- 所有互動元素（按鈕/輸入框/連結/勾選框）都有 hover + `:focus-visible`
  （2px `--color-focus` outline，不 transition，鍵盤使用者立即可見）+ `:active`
  + `:disabled`（opacity + cursor + 原生 `disabled` 屬性三通道）。
- `prefers-reduced-motion: reduce` 全域降級為 0.01ms。
- 輸入框與按鈕統一 `min-height:44px`（觸控下限，也讓 `.ask` 一排的輸入框跟
  按鈕高度一致，符合 slop-test gate 39 的 input-state 檢核）。
- 沒有 bounce/overshoot easing、沒有 `transition: all`、沒有 hover-only 才能
  觸達的操作（所有卡片動作按鈕本來就是點擊觸發，不依賴 hover 顯形）。

## CTA voice

主要動作用 `button.primary`（accent 實色填底、白字、pill 感圓角）；次要/取消
用 `button.ghost`（外框、中性字色）。全站只有這兩級，未新增第三種按鈕語言。

## 各頁允許差異

- `web/index.html`：多白話輸入列、多兩個功能頁（作者下載/進階掃描）、多進度
  區塊與追蹤項列表——這些是功能差異，不是視覺系統差異，token/元件語言完全
  共用。
- `site/index.html`：唯讀，無掃描/下載/追蹤項；`.results-toolbar` 內容更精簡
  （少了 `.export-actions`），但視覺語言（面板、chip、segmented control）
  逐一對應 `web/` 版本。

## Exports（可攜格式參考）

兩檔各自內嵌 token block（見上），此處另存一份純參考（不被任何頁面引用，
避免引入外部 CSS 依賴）：

```css
:root {
  --color-bg: oklch(97.2% 0.006 166);
  --color-surface: oklch(99.3% 0.002 166);
  --color-ink: oklch(24% 0.014 166);
  --color-accent: oklch(41% 0.082 166);
  --font-display: "Space Grotesk", "Microsoft JhengHei", "PingFang TC", sans-serif;
  --font-body: "Microsoft JhengHei", "PingFang TC", "Segoe UI", sans-serif;
  --space-md: 16px;
  --radius: 12px;
  --ease-out: cubic-bezier(.16, 1, .3, 1);
}
```

## 之後要加新頁面/新功能時

1. 先讀這份 `design.md`，沿用既有 token，不要重新挑色/挑字。
2. 新控制項優先沿用既有語彙：可多選/分類 → outline pill（`.tab`）；互斥切換
   → 凹槽分段控制項（`.views` / `#day-filter` / `#sort-toggle` 那種語言）；
   不要發明第三種導覽語彙。
3. 新的控制項群組要放進畫面時，先問「這個放進 `.results-toolbar` 這類既有
   面板合理嗎，還是真的需要開一塊新區域」——預設收斂進既有面板，不要在頁面
   上新增一排孤立的控制列。
