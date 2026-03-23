"""
Skill: get_channel_timeline_feeds
描述: 获取频道指定板块（子频道）的帖子时间序feeds流，支持翻页
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
TOOL_NAME = "get_channel_timeline_feeds"

SKILL_MANIFEST = {
    "name": "get-channel-timeline-feeds",
    "description": (
        "获取频道指定板块（子频道）的帖子列表，按最新回复时间排序。"
        "可指定排序方式（发布时间序或评论时间序），支持翻页。"
        "返回帖子ID、标题、作者、发布时间、评论数、点赞数等摘要信息。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "integer",
                "description": "频道ID，uint64，必填"
            },
            "channel_id": {
                "type": "integer",
                "description": "板块（子频道）ID，uint64，必填"
            },
            "count": {
                "type": "integer",
                "description": "拉取帖子个数，默认20，最大50"
            },
            "sort_option": {
                "type": "integer",
                "description": "排序：1=发布时间序（默认），2=评论时间序"
            },
            "feed_attch_info": {
                "type": "string",
                "description": "翻页透传字段，首次请求不填，后续翻页填上一次响应返回的 feed_attch_info"
            }
        },
        "required": ["guild_id", "channel_id"]
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
                "feeds": [...],          # 帖子摘要列表
                "is_finish": bool,       # 是否拉取完毕
                "feed_attch_info": str  # 下次翻页透传字段
            }
        }
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err
    arguments: dict[str, Any] = {
        "channel_sign": {
            "guild_id":   str(params["guild_id"]),   # 大整数转 string 避免 JSON 精度丢失
            "channel_id": str(params["channel_id"]),
        },
        "from": 1,           # REQ_FROM_TYPE NATIVE_APP=1，固定填充
        "render_sticker": True,  # field 14，固定填true
    }

    if "count" in params:
        arguments["count"] = int(params["count"])
    if "sort_option" in params:
        arguments["sort_option"] = int(params["sort_option"])
    else:
        arguments["sort_option"] = 1
    if "feed_attch_info" in params:
        arguments["feed_attch_info"] = params["feed_attch_info"]

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        # 解码每条 feed 中的 RichText 字段（含图片）
        for feed in structured.get("feeds") or []:
            if isinstance(feed.get("title"), dict):
                feed["title"] = decode_richtext_dict(feed["title"])
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
        feeds = structured.get("feeds") or []
        # ── 整理分页字段 ──────────────────────────────────────────────
        data: dict = {}
        if feeds:
            data["feeds"] = feeds
        raw_attach = structured.get("feedAttchInfo") or structured.get("feed_attch_info") or ""
        if raw_attach:
            data["feed_attch_info"] = raw_attach   # 翻页时原样传回
        data["is_finish"] = bool(structured.get("isFinish", False))
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
