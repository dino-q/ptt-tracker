#!/usr/bin/env bash
# 把 Gemini 金鑰設成 GitHub repo secret，給 Actions 的咖啡情報用。
#
# 為什麼要有這支：金鑰不可以打進對話、也不該複製貼上到終端機
# （長字串在終端機會軟換行、貼進去可能夾到空白）。這支直接從本機 .env 讀，
# 從頭到尾不把值印出來。
#
# 用法（在 Claude Code 輸入框）：
#     ! bash "C:/Users/AG_Di/Desktop/automation/Claude_code/side_project/PTT_Assistant/scripts/set_gemini_secret.sh"
#
# 換金鑰之後重跑同一行即可覆蓋。
set -u

REPO="dino-q/ptt-tracker"
ENV_FILE="${1:-C:/Users/AG_Di/Desktop/automation/Claude_code/tools/Gemini_ReadPic/.env}"
NAME="GEMINI_API_KEY"

if ! command -v gh >/dev/null 2>&1; then
  echo "[錯誤] 找不到 gh CLI。"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "[錯誤] 找不到 .env：$ENV_FILE"
  echo "       金鑰在別的地方的話，把路徑當第一個參數傳進來。"
  exit 1
fi

KEY="$(grep -E "^${NAME}=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//; s/["'\'']$//')"

if [ -z "$KEY" ]; then
  echo "[錯誤] $ENV_FILE 裡沒有 ${NAME}= 或值是空的"
  exit 1
fi

echo "來源：$ENV_FILE"
echo "金鑰：已讀到 ${#KEY} 個字元（不顯示內容）"
echo "目標：$REPO"
echo

# 用 stdin 傳值，不放進指令列——指令列會進 shell history 與行程清單。
# ⚠️ 不可以寫 `--body -`：gh 的 --body 是「值本身」，給 - 就會把 secret 設成字面的「-」，
#    Actions 拿到的是無效金鑰、而且 set 指令還會成功，看不出錯（2026-09-04 實際踩到）。
#    正確做法是**完全不給 --body**，gh 就會從 stdin 讀。
if printf '%s' "$KEY" | gh secret set "$NAME" --repo "$REPO" ; then
  echo
  echo "[完成] 已設定。目前這個 repo 的 secrets："
  gh secret list --repo "$REPO"
  echo
  echo "下一步：到 Actions 手動觸發一次 update-site，或等下一輪排程，"
  echo "        跑完看 build log 有沒有出現「coffee.json：N 個通路」。"
else
  echo "[失敗] gh secret set 沒有成功，看上面的錯誤訊息。"
  exit 1
fi
