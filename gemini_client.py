#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemini 呼叫層：金鑰、重試、備援模型、速率節流統一在這裡。

為什麼獨立成一支：咖啡情報（文字結構化）與圖片辨識都要打 Gemini，兩邊都要
「3.8-flash 撞尖峰就退到 2.5-flash」這套邏輯。複製一份出去改，遲早有一邊
的重試規則會腐爛。**要調重試/換模型/改節流一律改這裡，不要在呼叫端另寫一套。**

沒有金鑰、沒裝 google-genai、或兩個模型都不可用 → 一律回 None，
由呼叫端決定要略過還是沿用舊資料。這是每小時的排程，不能因為一次尖峰就整個爆掉。
"""
from __future__ import annotations

import os
import threading
import time

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.environ.get("GEMINI_MODEL_FALLBACK", "gemini-2.5-flash")
ATTEMPTS_PER_MODEL = 3

# 這些是「等一下再試就會好」的暫時性錯誤；其餘（金鑰錯、參數錯）重試沒有意義，
# 立刻放棄並把訊息傳回去，不要用重試把真正的設定錯誤蓋掉。
_RETRYABLE = ("503", "429", "500", "502", "504", "unavailable",
              "timeout", "deadline", "resource_exhausted", "rate limit", "quota")

# 兩次呼叫之間的最小間隔。2026-09-04 踩到：一輪連打 ~24 次圖片辨識，
# 有 9 次失敗且 imgur／mopix 都有（＝不是圖床問題）。免費層是每分鐘十幾次的量級，
# 爆量打不但會失敗，重試還會讓情況更糟。慢一點跑得完比快而失敗好。
MIN_INTERVAL_SECONDS = float(os.environ.get("GEMINI_MIN_INTERVAL", "4.0"))

# 單次呼叫的硬性上限。SDK 預設不設 timeout，一個卡住的請求可以拖到整個
# Actions job 被 30 分鐘上限砍掉。2026-09-04 本機實測單張圖要 ~90 秒，
# 所以給 120 秒——夠慢的圖跑完，又不會無限等下去。
REQUEST_TIMEOUT_MS = int(os.environ.get("GEMINI_TIMEOUT_MS", "120000"))
_throttle_lock = threading.Lock()
_last_call_at = 0.0


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


def _wait_turn(min_interval: float) -> None:
    global _last_call_at
    if min_interval <= 0:
        return
    with _throttle_lock:
        gap = time.monotonic() - _last_call_at
        if _last_call_at and gap < min_interval:
            time.sleep(min_interval - gap)
        _last_call_at = time.monotonic()


def generate_ex(contents, *, config=None, label: str = "Gemini",
                quiet: bool = False, min_interval: float | None = None,
                attempts: int | None = None):
    """打一次 Gemini。回 `(response, error_message)`——成功時 error 是 None。

    ⚠️ 需要知道「為什麼失敗」的呼叫端一定要用這支，不要用 generate()。
    2026-09-04 踩到：圖片辨識用 quiet=True 呼叫 generate()，失敗只能回報
    「Gemini 不可用」，log 上看不出是速率限制、金鑰錯還是圖片太大——
    等於加了錯誤輸出卻還是黑盒。
    """
    key = api_key()
    if not key:
        return None, "沒有 GEMINI_API_KEY"
    try:
        from google import genai
    except ImportError:
        return None, "沒裝 google-genai"

    if min_interval is None:
        min_interval = MIN_INTERVAL_SECONDS
    # 圖片辨識一輪要打二十幾次，每次都硬拚 3 次重試會把 job 時間吃光。
    # 這是每小時的排程，這輪讀不到下輪還會再讀，不值得在單張圖上耗。
    tries = ATTEMPTS_PER_MODEL if attempts is None else max(1, attempts)

    from google.genai import types as _types
    client = genai.Client(api_key=key,
                          http_options=_types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    last = None
    for model in (MODEL, FALLBACK_MODEL):
        for attempt in range(1, tries + 1):
            try:
                _wait_turn(min_interval)
                resp = client.models.generate_content(
                    model=model, contents=contents, config=config)
                if model != MODEL and not quiet:
                    print(f"{label}：{MODEL} 不可用，改用 {model} 成功")
                return resp, None
            except Exception as exc:                          # noqa: BLE001
                last = exc
                if not any(k in str(exc).lower() for k in _RETRYABLE):
                    return None, f"{type(exc).__name__}: {exc}"
                if attempt < tries:
                    time.sleep(2.0 * attempt)
    return None, f"兩個模型都不可用（{type(last).__name__}: {last}）"


def generate(contents, *, config=None, label: str = "Gemini",
             quiet: bool = False, min_interval: float | None = None,
             attempts: int | None = None):
    """generate_ex 的簡化版：只要結果、不要錯誤原因時用這支。"""
    resp, err = generate_ex(contents, config=config, label=label, quiet=quiet,
                            min_interval=min_interval, attempts=attempts)
    if err and not quiet:
        print(f"{label}：{err}")
    return resp
