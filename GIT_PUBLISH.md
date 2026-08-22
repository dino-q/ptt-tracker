# GIT_PUBLISH — PTT_Assistant 推送設定（2026-08-22 Dino 拍板）

- **Repo**：https://github.com/dino-q/ptt-tracker（owner：dino-q）
- **可見性**：公開（GitHub Pages 免費方案必需；內容為 PTT 公開資料）
- **agdino 協作**：否
- **線上版**：GitHub Pages（Actions 部署）https://dino-q.github.io/ptt-tracker/
  - 只上線「省錢優惠」「熱門文章」兩個唯讀頁（`site/`）
  - `.github/workflows/update.yml` 每 6 小時排程爬 PTT → 產 JSON → 部署（資料走 artifact，不進 git 歷史）
  - 作者下載／批次下載／進階掃描為本機限定功能，不上線

## 絕不上 git 的範圍（.gitignore 已擋，push 前再確認）

- `output/`（使用者匯出的文章內容，含個人閱讀偏好）
- `data/`（本機快取與 refresh.log）
- `tracks.json`（使用者自訂追蹤項）
- `config.json`（本機設定）
- `.venv/`、`tests/screenshots/`、`site/data/`（產物）
