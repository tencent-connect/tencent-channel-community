"""
Skill: get_feed_detail
描述: 获取指定帖子的完整详情，包括标题、正文、作者、所属频道及版块信息
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
from _mcp_client import call_mcp, get_feed_share_url, format_timestamp
from _richtext import decode_richtext_dict

# tool 名称（与 proto 中 mcp_rule.name 一致）
TOOL_NAME = "get_feed_detail"

SKILL_MANIFEST = {
    "name": "get-feed-detail",
    "description": (
        "获取指定帖子的完整详情，包括帖子标题、正文内容、作者信息、发布时间、"
        "评论数、点赞数、所属频道及版块信息、分享链接等。"
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
                "description": "频道ID，uint64 字符串，建议填写以加速查询"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串，建议填写以加速查询"
            },
            "author_id": {
                "type": "string",
                "description": "帖子作者ID（发表者用户ID），建议填写以加速查询"
            },
            "create_time": {
                "type": "string",
                "description": "帖子发表时间（秒级时间戳），uint64 字符串，建议填写以加速查询"
            }
        },
        "required": ["feed_id"]
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
                "feed": {
                    "feed_id": str,
                    "title": {                # 帖子标题（已解码）
                        "text": str,
                        "at_users": [{"id": str, "nick": str}],  # 标题中被@的用户（有时出现）
                        "images": [...],
                    },
                    "contents": {             # 帖子正文（已解码）
                        "text": str,
                        "at_users": [{"id": str, "nick": str}],  # 正文中被@的用户（有时出现）
                        "images": [...],
                    },
                    "author_name": str,
                    "author_id": str,
                    "create_time": int,   # 秒级时间戳
                    "comment_count": int,
                    "like_count": int,
                    "guild_id": int,
                    "channel_id": int,
                    "channel_name": str,
                    "share_url": str    # 帖子分享短链
                }
            }
        }
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err
    arguments: dict[str, Any] = {
        "feed_id": params["feed_id"],
    }

    if "guild_id" in params:
        arguments["guild_id"] = str(params["guild_id"])
    if "channel_id" in params:
        arguments["channel_id"] = str(params["channel_id"])
    if "author_id" in params:
        arguments["author_id"] = str(params["author_id"])
    if "create_time" in params:
        arguments["create_time"] = str(params["create_time"])

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        feed = structured.get("feed") or {}
        # 服务端对不存在的帖子返回空 feed，而非错误码
        if not feed or not feed.get("id"):
            return {"success": False, "error": f"帖子不存在或已删除：{params['feed_id']}"}
        # 解码 title / contents 中的 RichText（含图片）
        if isinstance(feed.get("title"), dict):
            feed["title"] = decode_richtext_dict(feed["title"])
        if isinstance(feed.get("contents"), dict):
            feed["contents"] = decode_richtext_dict(feed["contents"])

        # images：StFeed.images（field 13）→ 保留完整结构（含 picId/width/height/picUrl）
        # picId 用于 alter_feed 时 patternInfo 图片节点 taskId/fileId 及 images[].picId
        raw_images = feed.get("images")
        if isinstance(raw_images, list):
            feed["images"] = [
                {k: v for k, v in {
                    "picId":  img.get("picId"),
                    "picUrl": img.get("picUrl"),
                    "width":  img.get("width"),
                    "height": img.get("height"),
                }.items() if v}
                for img in raw_images if isinstance(img, dict) and img.get("picUrl")
            ]
        # cover：StFeed.cover（field 37）→ 提取封面图 URL
        cover = feed.get("cover")
        if isinstance(cover, dict):
            feed["cover"] = cover.get("picUrl") or None
        # videos：StFeed.videos（field 5）→ 提取帖子视频信息列表（含封面）
        raw_videos = feed.get("videos")
        if isinstance(raw_videos, list):
            feed["videos"] = [
                {k: v for k, v in {
                    "fileId":   vid.get("fileId"),
                    "playUrl":  vid.get("playUrl"),
                    "duration": vid.get("duration"),
                    "width":    vid.get("width"),
                    "height":   vid.get("height"),
                    "cover":    {ck: cv for ck, cv in {
                        "picId":  (vid.get("cover") or {}).get("picId"),
                        "picUrl": (vid.get("cover") or {}).get("picUrl"),
                        "width":  (vid.get("cover") or {}).get("width"),
                        "height": (vid.get("cover") or {}).get("height"),
                    }.items() if cv} if vid.get("cover") else None,
                }.items() if v}
                for vid in raw_videos if isinstance(vid, dict)
            ]
        # 获取帖子分享短链
        guild_id = str(feed.get("guildId") or feed.get("guild_id") or params.get("guild_id") or "")
        channel_id = str(feed.get("channelId") or feed.get("channel_id") or params.get("channel_id") or "")
        feed_id = feed.get("id") or params["feed_id"]
        share_url = get_feed_share_url(guild_id, channel_id, feed_id)
        if share_url:
            feed["share_url"] = share_url
        # 发布时间格式化（先保留原始值，再格式化，避免 create_time_raw 拿到字符串）
        raw_create_time = feed.get("createTime") or 0
        human_create_time = format_timestamp(raw_create_time) if raw_create_time else ""

        # 清洗内部字段：构建白名单输出，过滤 id/author_id/channelInfo 等内部字段
        poster = feed.get("poster") or {}
        author_nick = poster.get("nick", "") if isinstance(poster, dict) else ""
        channel_info = feed.get("channelInfo") or {}
        channel_name = channel_info.get("name", "") if isinstance(channel_info, dict) else ""
        guild_name = channel_info.get("guildName", "") if isinstance(channel_info, dict) else ""
        if channel_name == "帖子广场":
            channel_name = "频道主页"
        if channel_name == "帖子":
            channel_name = "频道主页"

        comment_count = feed.get("commentCount") or feed.get("comment_count") or 0
        prefer_count = 0
        total_prefer = feed.get("totalPrefer") or {}
        if isinstance(total_prefer, dict):
            prefer_count = total_prefer.get("count") or total_prefer.get("totalCount") or 0
        elif isinstance(total_prefer, int):
            prefer_count = total_prefer

        cleaned_feed: dict = {
            "feed_id":       feed_id,
            "title":         feed.get("title") or "",
            "contents":      feed.get("contents") or "",
            "author":        author_nick,
            "author_id":     str(poster.get("id", "") or poster.get("tinyId", "") or ""),
            "create_time":   human_create_time,
            "create_time_raw": int(raw_create_time),   # 秒级时间戳，供 do_comment/do_reply 使用
            "comment_count": comment_count,
            "prefer_count":  prefer_count,
        }
        if feed.get("images"):
            cleaned_feed["images"] = feed["images"]
        if feed.get("cover"):
            cleaned_feed["cover"] = feed["cover"]
        if feed.get("videos"):
            cleaned_feed["videos"] = feed["videos"]
        if share_url:
            cleaned_feed["share_url"] = share_url
        if channel_name:
            cleaned_feed["channel_name"] = channel_name
        if guild_name:
            cleaned_feed["guild_name"] = guild_name

        return {"success": True, "data": {"feed": cleaned_feed}}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
