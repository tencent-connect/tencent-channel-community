"""
Skill: get_guild_feeds
描述: 获取频道主页feeds流，支持热门/最新模式及翻页
MCP 服务: trpc.group_pro.open_platform_agent_mcp.FeedReaderMcpSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）
"""

import json
import sys
import os
from typing import Any

# 将 skills 根目录加入模块搜索路径，以便导入 _mcp_client
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp
from _richtext import decode_richtext_dict

# tool 名称（与 proto 中 mcp_rule.name 一致）
TOOL_NAME = "get_guild_feeds"

SKILL_MANIFEST = {
    "name": "get-guild-feeds",
    "description": (
        "获取频道主页的帖子列表，支持热门、最新等多种模式，支持翻页。"
        "返回帖子ID、标题、作者、发布时间、评论数、点赞数等摘要信息。"
        "用户说「全部」「所有帖子」「最新」「按时间」时必须传 get_type=2；"
        "只有用户明确说「热门」时才传 get_type=1。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "integer",
                "description": "频道ID，uint64，与 guild_number 二选一必填"
            },
            "guild_number": {
                "type": "string",
                "description": "频道号（字符串），没有频道ID时可用，与 guild_id 二选一必填"
            },
            "count": {
                "type": "integer",
                "description": "拉取帖子个数，默认20，最大50"
            },
            "get_type": {
                "type": "integer",
                "description": (
                    "获取类型（必填，禁止省略）："
                    "1=热门（仅用户明确说「热门」时使用）；"
                    "2=最新/全部（用户说「全部」「所有帖子」「最新」「按时间」或未明确指定排序时使用，默认值）；"
                    "3=最相关。"
                    "不确定时默认传 2。"
                ),
                "enum": [1, 2, 3]
            },
            "sort_option": {
                "type": "integer",
                "description": "排序方式，get_type=2时传入：1=发布时间序（默认），2=评论时间序；不填自动使用1",
                "enum": [1, 2]
            },
            "feed_attach_info": {
                "type": "string",
                "description": "翻页透传字段，首次请求不填，后续翻页填上一次响应返回的 feed_attach_info"
            }
        },
        "required": ["get_type"]
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
                "feeds": [...],       # 帖子摘要列表
                "is_finish": bool,    # 是否拉取完毕
                "feed_attach_info": str   # 下次翻页透传字段
            }
        }
        或 {"success": False, "error": "..."}
    """
    arguments: dict[str, Any] = {}

    # guild_id 和 guild_number 二选一必填
    if not params.get("guild_id") and not params.get("guild_number"):
        return {"success": False, "error": "guild_id 和 guild_number 必须填写其中一个"}

    get_type = int(params.get("get_type", 2))
    arguments["get_type"] = get_type

    if get_type == 2 and "sort_option" not in params:
        params["sort_option"] = 1  # 默认发布时间序

    if "guild_id" in params:
        arguments["guild_id"] = str(params["guild_id"])
    if "guild_number" in params:
        arguments["guild_number"] = params["guild_number"]
    arguments["count"] = int(params.get("count", 20))
    if "sort_option" in params:
        arguments["sort_option"] = int(params["sort_option"])
    if "feed_attach_info" in params:
        arguments["feed_attach_info"] = params["feed_attach_info"]

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        # ── 解码每条 feed 中的 RichText 字段 ──────────────────────────
        feeds = structured.get("feeds") or []
        for feed in feeds:
            # title：RichText dict → 纯文本字符串
            if isinstance(feed.get("title"), dict):
                feed["title"] = decode_richtext_dict(feed["title"])["text"]
            # contents：RichText dict → 结构化结果（保留图片等）
            if isinstance(feed.get("contents"), dict):
                feed["contents"] = decode_richtext_dict(feed["contents"])
                
            # images：StFeed.images（field 13）→ 提取帖子图片 URL 列表
            raw_images = feed.get("images")
            if isinstance(raw_images, list):
                feed["images"] = [img["picUrl"] for img in raw_images if isinstance(img, dict) and img.get("picUrl")]
            # cover：StFeed.cover（field 37）→ 提取封面图 URL
            cover = feed.get("cover")
            if isinstance(cover, dict):
                feed["cover"] = cover.get("picUrl") or None
            # videos：StFeed.videos（field 5）→ 提取帖子视频信息列表
            raw_videos = feed.get("videos")
            if isinstance(raw_videos, list):
                feed["videos"] = [
                    {k: v for k, v in {
                        "fileId":   vid.get("fileId"),
                        "playUrl":  vid.get("playUrl"),
                        "duration": vid.get("duration"),
                        "width":    vid.get("width"),
                        "height":   vid.get("height"),
                    }.items() if v}
                    for vid in raw_videos if isinstance(vid, dict)
                ]

        # ── 整理分页字段，去掉 URL 编码噪音 ──────────────────────────
        data: dict = {}
        if feeds:
            data["feeds"] = feeds
        raw_attach = structured.get("feedAttachInfo") or structured.get("feed_attach_info") or ""
        if raw_attach:
            data["feed_attach_info"] = raw_attach   # 翻页时原样传回
        data["is_finish"] = bool(structured.get("isFinish", False))
        if "totalFeedsCount" in structured:
            data["total"] = structured["totalFeedsCount"]
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
