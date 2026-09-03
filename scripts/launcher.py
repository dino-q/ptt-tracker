#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PTT Assistant 主選單（中文 UI 放這裡，不放 .bat）。

為什麼選單要搬進 Python（2026-09-04）：
    cmd.exe 解析 .bat 用系統 OEM 碼頁（台灣機器＝cp950），但專案的 .bat 存成 UTF-8。
    UTF-8 的中文位元組被當成 cp950 雙位元組配對時會錯位，**行尾的換行字元會被吃成後綴
    位元組**，下一行整個黏上來、指令消失。實測 git 原版 PTT工具.bat 在 cp950 下有 13 行
    以上被吃掉（`'ython.exe" server.py'`、`'ho.'`…），啟動.bat 因此 call 失敗又沒有 pause，
    就是 Dino 看到的「雙擊後閃一下就關掉」。
    在 .bat 裡加 `chcp 65001` 只能救一部分，會不會壞取決於那行的位元組怎麼配對，不可靠。

    反方向（把 .bat 存成 cp950）也不行：server.py／ptt_tool.py 裡有 cp950 表示不出來的
    字元（♻ ⚠ ≈ é），主控台切到 cp950 會讓它們印出來時直接 UnicodeEncodeError。

    所以：**.bat 一律純 ASCII、只負責 chcp 65001 ＋ 叫這支**；中文全部留在 Python。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MENU = """
================================
       PTT Assistant
================================

  [1] 網頁介面（會自動開瀏覽器，建議）
  [2] 一句話 CLI（輸出 TXT）
  [3] 預覽線上版（site/，改 GitHub Pages 那頁時用這個）
"""


def run(*args: str) -> int:
    """在同一個主控台跑子程式，Ctrl+C 交給子程式自己處理。"""
    try:
        return subprocess.call([sys.executable, *args], cwd=str(ROOT))
    except KeyboardInterrupt:
        return 0


def main() -> int:
    print(MENU)
    try:
        mode = input("選擇模式後按 Enter（預設 1）：").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        mode = "1"

    if mode == "2":
        try:
            request = input("\n請輸入要求：").strip()
        except (EOFError, KeyboardInterrupt):
            request = ""
        if not request:
            print("沒有輸入內容。")
            return 1
        return run(str(ROOT / "ptt_tool.py"), request)

    if mode == "3":
        print("\n準備線上版預覽（site/ 的資料是產物，缺的話會自動抓線上 JSON 當樣本）...")
        print("註：這跟 [1] 是兩個不同的頁面，改 site/index.html 要用這個看。")
        return run(str(ROOT / "scripts" / "preview_site.py"))

    print("\n啟動網頁介面中...（關閉此視窗即結束服務）")
    return run(str(ROOT / "server.py"))


if __name__ == "__main__":
    code = main()
    if code:
        print(f"\n[ERROR] 結束代碼：{code}")
    sys.exit(code)
