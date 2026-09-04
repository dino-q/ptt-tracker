#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemini 呼叫層：金鑰、重試、備援模型統一在這裡。

為什麼獨立成一支：咖啡情報（文字結構化）與圖片辨識都要打 Gemini，兩邊都要
「3.8-flash 撞尖峰就退到 2.5-flash」這套邏輯。複製一份出去改，遲早有一邊
的重試規則會腐爛。**要調重試/換模型一律改這裡，不要在呼叫端另寫一套。**

沒有金鑰、沒裝 google-genai、或兩個模型都不可用 → 一律回 None，
由呼叫端決定要略過還是沿用舊資料。這是每小時的排程，不能因為一次尖峰就整個爆掉。
"""
from __future__ import annotations

import os
import time

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.environ.get("GEMINI_MODEL_FALLBACK", "gemini-2.5-flash")
ATTEMPTS_PER_MODEL = 3

# 這些是「等一下再試就會好」的暫時性錯誤；其餘（金鑰錯、參數錯）重試沒有意義，
# 立刻放棄並把訊息印出來，不要用重試把真正的設定錯誤蓋掉。
_RETRYABLE = ("503", "429", "500", "502", "504", "unavailable",
              "timeout", "deadline", "resource_exhausted")


def api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY") or "").strip()


def available() -> bool:
    """有金鑰且裝得起 SDK 才算可用。呼叫端拿它來決定要不要進入整段流程。"""
    if not api_key():
        return False
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def parts():
    """回傳 google.genai.types，讓呼叫端組 Part 而不必各自處理 ImportError。"""
    from google.genai import types
    return types


def generate(contents, *, config=None, label: str = "Gemini", quiet: bool = False):
    """打一次 Gemini，內建重試與備援模型。失敗回 None（不丟例外）。

    label 只影響訊息前綴，讓 build log 看得出是哪個功能在講話。
    quiet=True 用在「一輪要打很多次」的場景（例如逐張圖片辨識），
    避免同一個錯誤在 log 裡刷幾十行。
    """
    key = api_key()
    if not key:
        if not quiet:
            print(f"{label}：沒有 GEMINI_API_KEY，略過")
        return None
    try:
        from google import genai
    except ImportError:
        if not quiet:
            print(f"{label}：沒裝 google-genai，略過")
        return None

    client = genai.Client(api_key=key)
    last = None
    for model in (MODEL, FALLBACK_MODEL):
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                resp = client.models.generate_content(
                    model=model, contents=contents, config=config)
                if model != MODEL and not quiet:
                    print(f"{label}：{MODEL} 不可用，改用 {model} 成功")
                return resp
            except Exception as exc:                          # noqa: BLE001
                last = exc
                if not any(k in str(exc).lower() for k in _RETRYABLE):
                    if not quiet:
                        print(f"{label}：失敗（{type(exc).__name__}: {exc}）")
                    return None
                if attempt < ATTEMPTS_PER_MODEL:
                    time.sleep(2.0 * attempt)
    if not quiet:
        print(f"{label}：兩個模型都不可用（{type(last).__name__}: {last}）")
    return None
