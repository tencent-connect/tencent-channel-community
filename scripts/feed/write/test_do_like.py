"""
测试用例: do_like（帖子评论/回复点赞/取消点赞）
运行方式:
    配置 ~/.openclaw/.env 或 mcporter（与 manage 相同）后:
    python3 write/test_do_like.py

测试数据（线上真实帖子/评论）：
    GUILD_ID      = 609667373978642354
    CHANNEL_ID    = 634587030
    FEED_ID       = B_f14fa569bc5c0c001441152209068856060X60
    COMMENT_ID    = c_a9a9b2699a7f07001441152186794796080X60
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from write.do_like import run

FEED_ID          = "B_f14fa569bc5c0c001441152209068856060X60"
FEED_AUTHOR_ID   = "144115220906885606"
FEED_CREATE_TIME = 1772441585
GUILD_ID         = 609667373978642354
CHANNEL_ID       = 634587030
COMMENT_ID       = "c_a9a9b2699a7f07001441152186794796080X60"
COMMENT_AUTHOR   = "144115218679479608"


def test_like_comment():
    """点赞评论（like_type=3）应成功，retCode=0"""
    result = run({
        "like_type": 3,
        "feed_id": FEED_ID, "feed_author_id": FEED_AUTHOR_ID, "feed_create_time": FEED_CREATE_TIME,
        "guild_id": GUILD_ID, "channel_id": CHANNEL_ID,
        "comment_id": COMMENT_ID, "comment_author_id": COMMENT_AUTHOR,
    })
    assert result["success"] is True, f"期望 success=True，实际: {result}"
    ret_code = result["data"].get("_meta", {}).get("AdditionalFields", {}).get("retCode", -1)
    assert ret_code == 0, f"期望 retCode=0，实际: {ret_code}"
    print(f"[PASS] 点赞评论: retCode=0")


def test_unlike_comment():
    """取消点赞评论（like_type=4）应成功，retCode=0"""
    result = run({
        "like_type": 4,
        "feed_id": FEED_ID, "feed_author_id": FEED_AUTHOR_ID, "feed_create_time": FEED_CREATE_TIME,
        "guild_id": GUILD_ID, "channel_id": CHANNEL_ID,
        "comment_id": COMMENT_ID, "comment_author_id": COMMENT_AUTHOR,
    })
    assert result["success"] is True, f"期望 success=True，实际: {result}"
    ret_code = result["data"].get("_meta", {}).get("AdditionalFields", {}).get("retCode", -1)
    assert ret_code == 0, f"期望 retCode=0，实际: {ret_code}"
    print(f"[PASS] 取消点赞评论: retCode=0")


def test_missing_comment_id():
    """like_type=3/4 缺少 comment_id，应返回 success=False"""
    result = run({
        "like_type": 3,
        "feed_id": FEED_ID, "feed_author_id": FEED_AUTHOR_ID, "feed_create_time": FEED_CREATE_TIME,
    })
    assert result["success"] is False, f"期望 success=False，实际: {result}"
    assert "comment_id" in result["error"]
    print(f"[PASS] 缺少 comment_id：正确拦截，error={result['error']}")


def test_missing_reply_id():
    """like_type=5/6 缺少 reply_id，应返回 success=False"""
    result = run({
        "like_type": 5,
        "feed_id": FEED_ID, "feed_author_id": FEED_AUTHOR_ID, "feed_create_time": FEED_CREATE_TIME,
    })
    assert result["success"] is False, f"期望 success=False，实际: {result}"
    assert "reply_id" in result["error"]
    print(f"[PASS] 缺少 reply_id：正确拦截，error={result['error']}")


if __name__ == "__main__":
    test_like_comment()
    test_unlike_comment()
    test_missing_comment_id()
    test_missing_reply_id()
    print("\n所有测试通过。")
