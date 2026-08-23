#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
線上版「立即更新」鈕驗收（純靜態 site/ ＋ mock GitHub API，不打真 GitHub）。
①路人看不到鈕、#admin 現身且取消設定零 API 呼叫
②成功流程：dispatch(帶token)→輪詢(帶token、workflow 專屬 runs)→資料換新→自動 reload
③dispatch 401→清 token 提示重設
④runs 輪詢被限流(403)→立即跳出、訊息正確、按鈕復原
⑤run conclusion 失敗→提示、不 reload
⑥資料 updated_at 沒變→絕不 reload，超時後如實提示
⑦money.json 載入失敗→note 顯示 fallback、按鈕（有 token 裝置）仍可見
"""
import datetime
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PORT = 8890
BASE = f"http://127.0.0.1:{PORT}"
FAST = "window.PTT_POLL_MS=400; window.PTT_DEADLINE_MS=6000;"
WITH_TOKEN = "localStorage.setItem('ptt_gh_token','test-token-abc');" + FAST
RUNS_MARK = "/actions/workflows/update.yml/runs"


def serve():
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE))
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gh_router(state, runs_status=200, conclusion="success"):
    """回傳 GitHub API mock route handler；state 記 dispatch 與各請求的 auth header。"""
    def handler(route):
        req = route.request
        if req.url.endswith("/dispatches") and req.method == "POST":
            state["dispatched"] = True
            state["dispatch_auth"] = req.headers.get("authorization")
            route.fulfill(status=204, body="")
        elif RUNS_MARK in req.url:
            state["runs_urls"] = state.get("runs_urls", []) + [req.url]
            state["runs_auth"] = req.headers.get("authorization")
            if runs_status != 200:
                route.fulfill(status=runs_status, body="{}")
                return
            route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"workflow_runs": [{"created_at": now_utc(), "status": "completed", "conclusion": conclusion}]}))
        else:
            route.abort()
    return handler


def main() -> None:
    srv = serve()
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ① 路人：無 token 鈕隱藏；#admin 現身；prompt 引導；取消零 API 呼叫
        ctx = browser.new_context()
        page = ctx.new_page()
        api_calls = []
        page.route("https://api.github.com/**", lambda route: (api_calls.append(route.request.url), route.abort()))
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append((d.type, d.message)), d.dismiss()))
        page.goto(BASE)
        page.wait_for_selector("#note-text")
        assert not page.locator("#refresh-btn").is_visible(), "路人不應看到立即更新鈕"
        page.goto(BASE + "#admin")
        page.wait_for_selector("#refresh-btn", state="visible")
        page.click("#refresh-btn")
        page.wait_for_timeout(400)
        assert dialogs and dialogs[0][0] == "prompt" and "personal-access-tokens" in dialogs[0][1], dialogs
        assert not api_calls, f"取消設定不應呼叫 API：{api_calls}"
        assert page.locator("#refresh-btn").inner_text() == "立即更新"
        print("PASS ① 路人隱藏鈕／#admin 現身／取消零 API")
        ctx.close()

        # ② 成功流程：dispatch→輪詢（帶 token、workflow 專屬端點）→資料換新→自動 reload
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(WITH_TOKEN)
        state = {"dispatched": False}
        page.route("https://api.github.com/**", gh_router(state))

        def money_route(route):
            if state["dispatched"]:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"updated_at": "2099-01-01 00:00", "note": "", "results": [], "categories": []}))
            else:
                route.fallback()

        page.route("**/data/money.json*", money_route)
        page.goto(BASE)
        page.click("#refresh-btn")
        page.wait_for_function(
            "document.getElementById('note-text') && document.getElementById('note-text').textContent.includes('2099-01-01')",
            timeout=30_000)
        assert state["dispatch_auth"] == "Bearer test-token-abc", state["dispatch_auth"]
        assert state["runs_auth"] == "Bearer test-token-abc", f"runs 輪詢必須帶 token：{state.get('runs_auth')}"
        assert all(RUNS_MARK in u for u in state["runs_urls"]), state["runs_urls"]
        assert page.locator("#refresh-btn").inner_text() == "立即更新"
        print("PASS ② 成功流程：帶 token 輪詢 workflow 專屬 runs→換新→reload")
        ctx.close()

        # ③ dispatch 401：清 token＋提示重設
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script("localStorage.setItem('ptt_gh_token','bad-token');" + FAST)
        page.route("https://api.github.com/**", lambda route: route.fulfill(status=401, body="{}"))
        alerts = []
        page.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
        page.goto(BASE)
        page.click("#refresh-btn")
        page.wait_for_timeout(1200)
        assert alerts and "token 無效" in alerts[0], alerts
        assert page.evaluate("localStorage.getItem('ptt_gh_token')") is None
        assert page.locator("#refresh-btn").is_visible(), "token 清除後按鈕必須留著（R1：sticky）"
        assert page.locator("#refresh-btn").is_enabled()
        print("PASS ③ 401：token 清除、按鈕留著可重新設定")
        ctx.close()

        # ④ runs 輪詢 403（限流）：立即跳出、訊息正確、按鈕復原（不空轉到 deadline）
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(WITH_TOKEN)
        state4 = {"dispatched": False}
        page.route("https://api.github.com/**", gh_router(state4, runs_status=403))
        alerts = []
        page.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
        page.goto(BASE)
        page.click("#refresh-btn")
        page.wait_for_function("document.getElementById('refresh-btn').textContent === '立即更新'", timeout=5_000)
        assert alerts and "限流" in alerts[0] and "403" in alerts[0], alerts
        assert page.locator("#refresh-btn").is_enabled()
        print("PASS ④ 輪詢 403：立即跳出、限流訊息、按鈕復原")
        ctx.close()

        # ⑤ run conclusion=failure：提示失敗、不 reload
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(WITH_TOKEN)
        page.route("https://api.github.com/**", gh_router({"dispatched": False}, conclusion="failure"))
        alerts = []
        page.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
        page.goto(BASE)
        page.click("#refresh-btn")
        page.wait_for_function("document.getElementById('refresh-btn').textContent === '立即更新'", timeout=5_000)
        assert alerts and "雲端更新失敗" in alerts[0] and "failure" in alerts[0], alerts
        print("PASS ⑤ run 失敗：如實提示、不 reload")
        ctx.close()

        # ⑥ 資料 updated_at 沒變：絕不 reload，deadline 後如實提示（B2 回歸）
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(WITH_TOKEN)
        page.route("https://api.github.com/**", gh_router({"dispatched": False}))
        alerts = []
        page.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
        page.goto(BASE)  # money.json 走真檔，輪詢時 updated_at 恆等於基準
        reloads = {"n": 0}
        page.on("framenavigated", lambda f: reloads.__setitem__("n", reloads["n"] + 1) if f == page.main_frame else None)
        page.click("#refresh-btn")
        page.wait_for_function("document.getElementById('refresh-btn').textContent === '立即更新'", timeout=15_000)
        assert alerts and "還沒看到新資料" in alerts[-1], alerts
        assert reloads["n"] == 0, f"資料沒變不得 reload（發生 {reloads['n']} 次導航）"
        print("PASS ⑥ 資料未變：不 reload、超時如實提示")
        ctx.close()

        # ⑦ money.json 載入失敗：note 顯示 fallback、按鈕（有 token）仍可見可按
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script("localStorage.setItem('ptt_gh_token','test-token-abc')")
        page.route("**/data/money.json*", lambda route: route.abort())
        page.goto(BASE)
        page.wait_for_selector("#refresh-btn", state="visible")
        assert "資料載入失敗" in page.locator("#note-text").inner_text()
        assert page.locator("#refresh-btn").is_enabled()
        print("PASS ⑦ 資料載入失敗：fallback 橫幅＋按鈕仍在")
        ctx.close()

        # ⑧ 無 token 裝置＋money.json 載入失敗：不叫人按看不到的鈕（R2）
        ctx = browser.new_context()
        page = ctx.new_page()
        page.route("**/data/money.json*", lambda route: route.abort())
        page.goto(BASE)
        page.wait_for_selector("#note-text")
        note = page.locator("#note-text").inner_text()
        assert "資料載入失敗" in note and "立即更新" not in note, note
        assert not page.locator("#refresh-btn").is_visible()
        print("PASS ⑧ 無 token＋載入失敗：文案不提按鈕、按鈕維持隱藏")
        ctx.close()

        # ⑨ runs 輪詢途中 401（token 被撤銷）：清 token、如實提示、按鈕留著（R3）
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(WITH_TOKEN)
        page.route("https://api.github.com/**", gh_router({"dispatched": False}, runs_status=401))
        alerts = []
        page.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
        page.goto(BASE)
        page.click("#refresh-btn")
        page.wait_for_function("document.getElementById('refresh-btn').textContent === '立即更新'", timeout=5_000)
        assert alerts and "token 已失效" in alerts[0], alerts
        assert page.evaluate("localStorage.getItem('ptt_gh_token')") is None
        assert page.locator("#refresh-btn").is_visible() and page.locator("#refresh-btn").is_enabled()
        print("PASS ⑨ 輪詢 401：清 token、如實提示、按鈕留著")
        ctx.close()

        browser.close()
    srv.shutdown()
    print("ALL PASS")


if __name__ == "__main__":
    main()
