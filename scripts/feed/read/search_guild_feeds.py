"""
Skill: search_guild_feeds
描述: 按关键词搜索频道内帖子
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）
"""

import json
import sys
import os
from typing import Any

# 将 skills 根目录加入模块搜索路径，以便导入 _mcp_client
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp

# tool 名称（与 proto 中 mcp_rule.name 一致）
TOOL_NAME = "get_search_guild_feed"

SKILL_MANIFEST = {
    "name": "get-search-guild-feed",
    "description": (
        "按关键词搜索指定频道内的帖子，匹配帖子标题和正文内容，支持翻页。"
        "返回帖子ID、标题、内容摘要、作者、发布时间、评论数、点赞数等信息。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "integer",
                "description": "频道ID，uint64，必填"
            },
            "query": {
                "type": "string",
                "description": "搜索关键词，必填，会匹配帖子标题和正文内容"
            },
            "cookie": {
                "type": "string",
                "description": "翻页透传字段（base64编码），首次请求不填，后续翻页填上一次响应返回的 feed_cookie"
            },
            "search_type": {
                "type": "object",
                "description": "搜索类型配置，选填。type: 搜索内容类型（0=all,1=消息,2=帖子），feed_type: 帖子排序（0=默认,1=最新）",
                "properties": {
                    "type": {
                        "type": "integer",
                        "description": "搜索类型：0=all，1=消息，2=帖子（搜帖子时填2）"
                    },
                    "feed_type": {
                        "type": "integer",
                        "description": "帖子排序：0=默认，1=最新"
                    }
                }
            }
        },
        "required": ["guild_id", "query"]
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
                "guild_feeds": [...],    # 帖子搜索结果列表，每项含 feed_id/title/content/guild_id/channel_id 等
                "feed_total": int,       # 搜索到的帖子总数
                "feed_is_end": bool,     # 是否已是最后一页
                "feed_cookie": str,      # 下次翻页透传字段（base64编码）
                "highlight_words": [...] # 高亮关键词列表
            }
        }
        或 {"success": False, "error": "..."}
    """
    if "keyword" in params and "query" not in params:
        params["query"] = params.pop("keyword")

    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err
    arguments: dict[str, Any] = {
        "guild_id": str(params["guild_id"]),
        "query": params["query"],
    }

    if "cookie" in params and params["cookie"]:
        arguments["cookie"] = params["cookie"]

    if "search_type" in params:
        arguments["search_type"] = params["search_type"]
    else:
        # 默认只搜索帖子
        arguments["search_type"] = {"type": 2, "feed_type": 0}

    try:
        result = call_mcp(TOOL_NAME, arguments)
        # 从 structuredContent.unionResult 中提取帖子相关字段，方便调用方使用
        structured = result.get("structuredContent") or {}
        union_result = structured.get("unionResult") or structured.get("union_result") or {}
        guild_feeds = union_result.get("guildFeeds", union_result.get("guild_feeds", []))
        feed_is_end = union_result.get("feedIsEnd", union_result.get("feed_is_end", True))
        data = {
            "guild_feeds":      guild_feeds,
            "feed_total":       union_result.get("feedTotal", union_result.get("feed_total", 0)),
            "feed_is_end":      feed_is_end,
            "highlight_words":  structured.get("highlightWords", structured.get("highlight_words", [])),
        }
        if not feed_is_end:
            cookie = union_result.get("feedCookie", union_result.get("feed_cookie", ""))
            if cookie:
                data["next_page_cookie"] = cookie
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
