"""
Skill: get_guild_feeds
描述: 获取频道主页feeds流，支持热门/最新模式及翻页
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
from _mcp_client import call_mcp, format_timestamp
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
        "翻页时必须与上一次请求使用完全相同的 get_type（和 sort_option），禁止在翻页时改变排序模式。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，与 guild_number 二选一必填"
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
                    "⚠️ 翻页时必须与首次请求保持相同的 get_type，禁止在翻页时切换。"
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
                "description": "翻页透传字段，首次请求不填，后续翻页填上一次响应返回的 feed_attach_info。⚠️ 翻页时必须同时保持与首次请求相同的 get_type（和 sort_option），游标与排序模式绑定，切换 get_type 会导致拉取混乱。"
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
        raw_feeds = structured.get("feeds") or []
        feeds = []
        for feed in raw_feeds:
            # title：RichText dict → 纯文本字符串
            title = feed.get("title")
            if isinstance(title, dict):
                title = decode_richtext_dict(title)["text"]

            # contents：RichText dict → 结构化结果（保留图片等）
            contents = feed.get("contents")
            if isinstance(contents, dict):
                contents = decode_richtext_dict(contents)

            # images：提取图片 URL 列表
            raw_images = feed.get("images")
            images = []
            if isinstance(raw_images, list):
                images = [img["picUrl"] for img in raw_images if isinstance(img, dict) and img.get("picUrl")]

            # cover：提取封面图 URL
            cover_url = None
            cover = feed.get("cover")
            if isinstance(cover, dict):
                cover_url = cover.get("picUrl") or None

            # 发布时间格式化
            create_time = format_timestamp(feed.get("createTime", ""))

            # videos：提取视频信息列表
            raw_videos = feed.get("videos")
            videos = []
            if isinstance(raw_videos, list):
                videos = [
                    {k: v for k, v in {
                        "playUrl":  vid.get("playUrl"),
                        "duration": vid.get("duration"),
                        "width":    vid.get("width"),
                        "height":   vid.get("height"),
                    }.items() if v}
                    for vid in raw_videos if isinstance(vid, dict)
                ]

            # 作者昵称（只保留 nick，不暴露 tinyId/id）
            poster = feed.get("poster") or {}
            author_nick = poster.get("nick", "")

            # channelInfo：只保留频道名称（不含内部 sign/guildId/channelId）
            channel_info = feed.get("channelInfo") or {}
            channel_name = channel_info.get("name", "")
            guild_name = channel_info.get("guildName", "")
            # "帖子广场" → 统一替换为 "频道主页"
            if channel_name == "帖子广场":
                channel_name = "频道主页"
            if channel_name == "帖子":
                channel_name = "频道主页"

            # 统计信息
            comment_count = feed.get("commentCount") or feed.get("comment_count") or 0
            prefer_count = 0
            total_prefer = feed.get("totalPrefer") or {}
            if isinstance(total_prefer, dict):
                prefer_count = total_prefer.get("count") or total_prefer.get("totalCount") or 0
            elif isinstance(total_prefer, int):
                prefer_count = total_prefer

            # 构建清洗后的帖子对象
            cleaned = {
                "feed_id":        feed.get("id", "") or feed.get("feedId", ""),
                "title":          title or "",
                "author":         author_nick,
                "author_id":      str((feed.get("poster") or {}).get("id", "") or
                                      (feed.get("poster") or {}).get("tinyId", "") or ""),
                "create_time":     create_time,
                "create_time_raw": int(feed.get("createTime") or 0),   # 秒级，供 do_comment 的 feed_create_time 使用
                "comment_count":   comment_count,
                "prefer_count":    prefer_count,
            }
            if contents:
                if isinstance(contents, dict) and contents.get("text"):
                    snippet = contents["text"]
                    cleaned["content_snippet"] = (snippet[:100] + "…") if len(snippet) > 100 else snippet
                elif isinstance(contents, str) and contents:
                    cleaned["content_snippet"] = (contents[:100] + "…") if len(contents) > 100 else contents
            if images:
                cleaned["images"] = images
            if cover_url:
                cleaned["cover"] = cover_url
            if videos:
                cleaned["videos"] = videos
            if guild_name:
                cleaned["guild_name"] = guild_name
            if channel_name:
                cleaned["channel_name"] = channel_name
            feeds.append(cleaned)

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