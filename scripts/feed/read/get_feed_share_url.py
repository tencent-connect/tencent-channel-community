"""
Skill: get_feed_share_url
描述: 获取指定帖子的分享短链
MCP 服务: trpc.group_pro.open_platform_agent_mcp.FeedReaderMcpSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）

⚠️  调用前必读：references/feed-reference.md
    包含翻页规则、字段说明、正确调用流程等关键说明。
    禁止仅凭此脚本推断用法。
"""

import json
import sys
import os
from typing import Any

# 将 skills 根目录加入模块搜索路径，以便导入 _mcp_client
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import get_feed_share_url

SKILL_MANIFEST = {
    "name": "get-feed-share-url",
    "description": (
        "获取指定帖子的分享短链。需要提供帖子ID和频道ID，"
        "返回可直接分享的帖子短链 URL。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "帖子ID，必填"
            },
            "guild_id": {
                "type": "string",
                "description": "频道ID，必填"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，选填"
            }
        },
        "required": ["feed_id", "guild_id"]
    }
}


# =========================================================
# Skill 入口
# =========================================================

def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {
            "success": True,
            "data": {
                "feed_id": str,
                "share_url": str
            }
        }
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    feed_id = params["feed_id"]
    guild_id = str(params["guild_id"])
    channel_id = str(params.get("channel_id", "")) or ""

    try:
        url = get_feed_share_url(guild_id, channel_id, feed_id)
        if not url:
            return {"success": False, "error": f"获取帖子分享链接失败，feed_id={feed_id}"}
        return {
            "success": True,
            "data": {
                "share_url": url,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)