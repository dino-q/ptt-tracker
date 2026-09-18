# GIT_PUBLISH — PTT_Assistant 推送設定（2026-08-22 Dino 拍板）

- **Repo**：https://github.com/dino-q/ptt-tracker（owner：dino-q）
- **可見性**：公開（GitHub Pages 免費方案必需；內容為 PTT 公開資料）
- **agdino 協作**：否
- **線上版**：GitHub Pages（Actions 部署）https://dino-q.github.io/ptt-tracker/
  - 只上線「省錢優惠」「熱門文章」兩個瀏覽頁（`site/`）；不含掃描/下載功能
  - **⚠️ 2026-09-18 Dino 拍板改本機抓**：PTT 自 2026-09-16 18:50 UTC 起對 GitHub Actions 的機房 IP 回 403（同時段本機是 200），`update-site` 連續 7 次全掛。封鎖認來源 IP 段，改程式繞不過（Cloudflare 機房實測也是 403）。
    - 現在的資料流：本機排程 `PTT_Assistant_DailyCache`（每日 08:30，錯過補跑）→ `scripts/publish_local.py` 爬 PTT、產 `site/data/*.json` → commit + push → `.github/workflows/update.yml` 收到 push **只做 Pages 部署**（不再爬 PTT，也不再有 schedule）
    - 因此 **`site/data/` 開始進 git 歷史**（原本 gitignore、走 artifact）。內容是 PTT 公開資料的整理結果，不含個人資料
    - 頻率從「每小時」降為「每天一次」（2026-09-18 Dino 同意；省錢優惠不需每小時更新，也降低被列入封鎖名單的機會）
    - 代價：**電腦沒開機那天線上資料不會更新**
  - 「立即更新」鈕（2026-08-23 加）**2026-09-18 起一律隱藏**：雲端已抓不到資料，按了只會重新部署同一份舊資料。程式碼與 `tests/verify_refresh.py` 保留，PTT 解封可直接復活。PAT 機制（存瀏覽器 localStorage，**絕不寫進 repo**）不變
  - 作者下載／批次下載／進階掃描為本機限定功能，不上線

## 絕不上 git 的範圍（.gitignore 已擋，push 前再確認）

- `output/`（使用者匯出的文章內容，含個人閱讀偏好）
- `data/`（本機快取與 refresh.log）
- `tracks.json`（使用者自訂追蹤項）
- `config.json`（本機設定）
- `.venv/`、`tests/screenshots/`（產物）
- ⚠️ `site/data/`（線上版 JSON）**2026-09-18 起改為要進 git**——見上面「改本機抓」。它是唯一從這份清單移出的項目，其餘照舊
