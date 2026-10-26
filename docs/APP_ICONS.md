# Dino PTT App 圖示

日期：2026-10-26
選定款：D2 終端機論壇。Dino 已在本次對話確認。
製作：內建 image_gen；依選定比較圖獨立輸出，保留圖案、移除白邊／編號、四角滿版。
技術輸出：以 Windows System.Drawing 等比例縮至 32、180、192、512px，不改圖案內容。母圖 1254×1254px。

## 檔案

- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/site/app-icon-d2.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/site/app-icon-d2-32.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/site/app-icon-d2-180.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/site/app-icon-d2-192.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/site/app-icon-d2-512.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/site/app.webmanifest`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/web/app-icon-d2.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/web/app-icon-d2-32.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/web/app-icon-d2-180.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/web/app-icon-d2-192.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/web/app-icon-d2-512.png`
- `C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/web/app.webmanifest`

## 套用

site/index.html 與 web/index.html 使用同一款圖示。♻️ 沿用 Handler._file 提供本機 manifest 與四個固定 PNG 路由；僅允許明確列出的檔名，不開放任意檔案。線上與本機 manifest 內容相同，採相對路徑，支援 /ptt-tracker/ 子路徑。未改排程、爬蟲或資料。

## 最終圖片編修提示原文

Edit target: attached two-icon comparison board. Deliver ONLY the RIGHT D2 design as a SINGLE production square app icon. Faithfully preserve the selected D2 terminal speech bubble mark: near-black navy backdrop, luminous mint terminal window/speech bubble border, three red yellow green status lights at upper left, large mint pixel lettering exactly 'Dino' on upper line, large warm ivory pixel lettering exactly 'PTT' on lower line, amber block cursor after PTT. Keep relative typography, framing, colors and subtle dimensional finish faithful to selected D2. REMOVE presentation board, D1, headings and D2 label. FULL BLEED square canvas filled to edges with the same navy background, NO white margins, NO external rounded corner mask, NO outer shadow. Operating system supplies its own mask. Place the terminal outline and all text inside center 78% width and height with generous navy breathing space so circular masks do not crop the mark. All four corners fully opaque dark navy. No extra lettering, no redesign, no added imagery. Crisp legible finished high resolution square app artwork.

## 驗證結果

RPG Vite production build：成功。
已用已安裝的 Chrome 實際載入 RPG 打包版、PTT site 與 PTT Handler 本機版，並檢視整頁截圖與 64px 圖示。

RPG build: PASS (links, MIME types, dimensions, relative paths, browser load)
PTT site: PASS (links, MIME types, dimensions, relative paths, browser load)
PTT local: PASS (links, MIME types, dimensions, relative paths, browser load)
Allowlist / query string: PASS
PTT site/web SHA-256 sync: PASS
37 assertions PASS

2026-10-26 Dino 明確授權「都可以套用上線了」。本機驗證完成，依既有 GIT_PUBLISH.md 發布；正式網址與發布方式沿用專案資訊.md。
