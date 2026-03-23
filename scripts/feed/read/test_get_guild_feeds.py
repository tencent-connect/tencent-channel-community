"""
测试用例: get_guild_feeds（帖子广场）
运行方式:
    配置 ~/.openclaw/.env 或 mcporter 后:
    python3 read/test_get_guild_feeds.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from read.get_guild_feeds import run

GUILD_ID = 7023821632368227


def test_hot(verbose=False):
    """热门模式 (get_type=1)"""
    result = run({"guild_id": GUILD_ID, "get_type": 1, "count": 3})
    assert result["success"] is True, f"期望 success=True，实际: {result}"
    if verbose:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[PASS] 热门模式: success=True, feeds数量={len(result['data'].get('structuredContent', {}).get('feeds', []))}")


def test_latest_missing_sort_option():
    """最新模式缺少 sort_option 应返回错误"""
    result = run({"guild_id": GUILD_ID, "get_type": 2})
    assert result["success"] is False, f"期望 success=False，实际: {result}"
    assert "sort_option" in result["error"], f"错误信息应提示 sort_option，实际: {result['error']}"
    print(f"[PASS] 最新模式缺 sort_option: 正确拦截，error={result['error']}")


def test_latest_by_publish_time():
    """最新模式-发布时间序 (get_type=2, sort_option=1)"""
    result = run({"guild_id": GUILD_ID, "get_type": 2, "sort_option": 1, "count": 3})
    assert result["success"] is True, f"期望 success=True，实际: {result}"
    feeds = result["data"].get("structuredContent", {}).get("feeds", [])
    # 验证按发布时间降序
    times = [int(f["createTime"]) for f in feeds if "createTime" in f]
    assert times == sorted(times, reverse=True), f"应按发布时间降序，实际: {times}"
    print(f"[PASS] 最新-发布时间序: feeds数量={len(feeds)}, 时间降序验证通过")


def test_latest_by_comment_time():
    """最新模式-评论时间序 (get_type=2, sort_option=2)"""
    result = run({"guild_id": GUILD_ID, "get_type": 2, "sort_option": 2, "count": 3})
    assert result["success"] is True, f"期望 success=True，实际: {result}"
    feeds = result["data"].get("structuredContent", {}).get("feeds", [])
    print(f"[PASS] 最新-评论时间序: feeds数量={len(feeds)}")


if __name__ == "__main__":
    test_hot()
    test_latest_missing_sort_option()
    test_latest_by_publish_time()
    test_latest_by_comment_time()
    print("\n所有测试通过。")
