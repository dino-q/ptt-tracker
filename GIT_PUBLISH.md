# GIT_PUBLISH — PTT_Assistant 推送設定（2026-08-22 Dino 拍板）

- **Repo**：https://github.com/dino-q/ptt-tracker（owner：dino-q）
- **可見性**：公開（GitHub Pages 免費方案必需；內容為 PTT 公開資料）
- **agdino 協作**：否
- **線上版**：GitHub Pages（Actions 部署）https://dino-q.github.io/ptt-tracker/
  - 只上線「省錢優惠」「熱門文章」兩個瀏覽頁（`site/`）；不含掃描/下載功能，唯一的寫入面是「立即更新」鈕（2026-08-23 加）＝用瀏覽者自己的 GitHub PAT 觸發 workflow_dispatch，PAT 只存使用者瀏覽器 localStorage，**絕不寫進 repo**
  - `.github/workflows/update.yml` 排程爬 PTT → 產 JSON → 部署（資料走 artifact，不進 git 歷史）
  - 頻率：台灣時間 08:07～23:07 每小時、深夜停跑（2026-08-22 Dino 拍板；cron 為 UTC `7 0-15 * * *`）
  - 作者下載／批次下載／進階掃描為本機限定功能，不上線

## 絕不上 git 的範圍（.gitignore 已擋，push 前再確認）

- `output/`（使用者匯出的文章內容，含個人閱讀偏好）
- `data/`（本機快取與 refresh.log）
- `tracks.json`（使用者自訂追蹤項）
- `config.json`（本機設定）
- `.venv/`、`tests/screenshots/`、`site/data/`（產物）
