"""
测试用例: do_feed_prefer（帖子点赞/取消点赞）
运行方式:
    配置 ~/.openclaw/.env 或 mcporter 后:
    python3 write/test_do_feed_prefer.py

测试数据（线上真实帖子）：
    GUILD_ID   = 609667373978642354
    CHANNEL_ID = 634587030
    FEED_ID    = B_f14fa569bc5c0c001441152209068856060X60
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from write.do_feed_prefer import run

GUILD_ID   = 609667373978642354
CHANNEL_ID = 634587030
FEED_ID    = "B_f14fa569bc5c0c001441152209068856060X60"


def test_cancel_prefer():
    """取消点赞（action=3）应成功，返回 success=True，retCode=0，并返回 prefer_count"""
    result = run({"feed_id": FEED_ID, "action": 3, "guild_id": GUILD_ID, "channel_id": CHANNEL_ID})
    assert result["success"] is True, f"期望 success=True，实际: {result}"
    ret_code = result["data"].get("_meta", {}).get("AdditionalFields", {}).get("retCode", -1)
    assert ret_code == 0, f"期望 retCode=0，实际: {ret_code}，响应: {result}"
    prefer_count = result["data"].get("structuredContent", {}).get("preferCount")
    print(f"[PASS] 取消点赞: success=True, retCode=0, preferCount={prefer_count}")


def test_prefer_reaches_backend():
    """点赞（action=1）请求能到达后端（retCode 非网络/协议错误）"""
    result = run({"feed_id": FEED_ID, "action": 1, "guild_id": GUILD_ID, "channel_id": CHANNEL_ID})
    assert result["success"] is True, f"MCP 调用本身应成功，实际: {result}"
    ret_code = result["data"].get("_meta", {}).get("AdditionalFields", {}).get("retCode", -1)
    # retCode=0（成功）或业务错误码（如权限不足 890500）均表示协议通路正确
    assert ret_code != -1, f"未获取到 retCode，响应: {result}"
    print(f"[PASS] 点赞请求到达后端: retCode={ret_code}")


def test_missing_feed_id():
    """缺少必填参数 feed_id，应抛出 KeyError"""
    try:
        run({"action": 1, "guild_id": GUILD_ID})
        assert False, "期望抛出 KeyError"
    except KeyError:
        print("[PASS] 缺少 feed_id：正确抛出 KeyError")


def test_missing_action():
    """缺少必填参数 action，应抛出 KeyError"""
    try:
        run({"feed_id": FEED_ID, "guild_id": GUILD_ID})
        assert False, "期望抛出 KeyError"
    except KeyError:
        print("[PASS] 缺少 action：正确抛出 KeyError")


if __name__ == "__main__":
    test_cancel_prefer()
    test_prefer_reaches_backend()
    test_missing_feed_id()
    test_missing_action()
    print("\n所有测试通过。")
