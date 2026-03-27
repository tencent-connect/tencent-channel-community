"""
Skill: get_next_page_replies
描述: 获取指定评论的下一页回复列表。
     get_feed_comments 返回的每条评论已内含第一页回复预览（vec_reply）和翻页游标（attach_info）。
     当评论的 next_page_reply=true 时，将该评论的 attach_info 作为请求的 attach_info 传入，
     即可获取预览之后的下一页回复。后续翻页则填上一次本接口响应返回的 attach_info。
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

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
from _richtext import decode_richtext, decode_richtext_dict

# tool 名称（与 proto 中 mcp_rule.name 一致）
TOOL_NAME = "get_next_page_replies"

SKILL_MANIFEST = {
    "name": "get-next-page-replies",
    "description": (
        "获取指定评论下的下一页回复列表，支持继续翻页。\n"
        "调用时机：get_feed_comments 返回的评论中 has_more_replies=true 时，说明该评论有更多回复未展示。\n"
        "所需的 attach_info 就在 get_feed_comments 返回的该评论对象的 attach_info 字段中，直接取用即可，无需额外请求。\n"
        "首次调用将该评论的 attach_info 填入请求的 attach_info 字段；\n"
        "后续翻页填上一次本接口响应返回的 attach_info，直到响应 has_more=false 为止。\n"
        "返回回复内容、回复者信息、时间、点赞数及@的用户信息等。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "帖子ID，必填"
            },
            "comment_id": {
                "type": "string",
                "description": "评论ID，必填。来自 get_feed_comments 返回的评论的 id 字段"
            },
            "attach_info": {
                "type": "string",
                "description": (
                    "翻页游标，必填。\n"
                    "首次调用：填 get_feed_comments 返回的对应评论的 attach_info 字段（评论预览回复的结束位置）。\n"
                    "后续翻页：填上一次本接口响应返回的 attach_info，直到 has_more=false。"
                )
            },
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，必填（透传至 channel_sign.guild_id）"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串，必填（透传至 channel_sign.channel_id）"
            },
            "page_size": {
                "type": "integer",
                "description": "每页回复数量，默认20，最大50"
            }
        },
        "required": ["feed_id", "comment_id", "attach_info", "guild_id", "channel_id"]
    }
}


# =========================================================
# Skill 入口
# =========================================================

def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    调用时机：
        get_feed_comments 返回的评论中 next_page_reply=true，说明该评论有更多回复。
        首次调用时将评论的 attach_info（预览回复的翻页游标）填入请求，
        后续翻页填上一次响应返回的 attach_info，直到响应 has_more=false。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {
            "success": True,
            "data": {
                "replies": [
                    {
                        "id": str,           # 回复ID
                        "content": dict,     # 回复内容（已解码，含 text/images/sticker/at_users）
                        "at_users": [        # 被@的用户列表（有at时出现）
                            {"id": str, "nick": str}
                        ],
                        "postUser": {        # 回复者信息
                            "id": str,
                            "nick": str
                        },
                        "createTime": str,   # 秒级时间戳
                        "targetUser": dict,  # 被回复的用户信息
                        "likeInfo": dict     # 点赞信息
                    }
                ],
                "hasMore": bool,          # false 时表示已无更多回复，无需继续翻页
                "attachInfo": str,        # 下次翻页透传字段（hasMore=true 时填入下次请求）
                "totalReplyCount": int    # 该评论下回复总数
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
        "comment_id": params["comment_id"],
    }

    channel_sign: dict[str, str] = {
        "guild_id":   str(params["guild_id"]),
        "channel_id": str(params["channel_id"]),
    }
    arguments["channel_sign"] = channel_sign

    if "page_size" in params:
        arguments["page_size"] = int(params["page_size"])
    if "attach_info" in params:
        arguments["attach_info"] = params["attach_info"]
    arguments["render_sticker"] = True

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        # ── 规范化回复字段 ────────────────────────────────────────────
        replies = []
        for reply in structured.get("replies", []):
            # 优先用 richContents（含 sticker URL），回退到 content（base64 protobuf）
            rich = reply.get("richContents") or {}
            decoded = decode_richtext_dict(rich) if rich else decode_richtext(reply.get("content", ""))
            r = {
                "id":              reply.get("id", ""),
                "content":         decoded,
                "create_time":     format_timestamp(reply.get("createTime", "")),
                "create_time_raw": int(reply.get("createTime") or 0),    # 秒级，供后续写操作使用
                "author":          (reply.get("postUser") or reply.get("post_user") or {}).get("nick", ""),
                "author_id":       str((reply.get("postUser") or reply.get("post_user") or {}).get("id", "") or
                                       (reply.get("postUser") or reply.get("post_user") or {}).get("tinyId", "") or ""),
                "target_user_id":  str((reply.get("targetUser") or reply.get("target_user") or {}).get("id", "") or
                                       (reply.get("targetUser") or reply.get("target_user") or {}).get("tinyId", "") or ""),
                "target_user":     (reply.get("targetUser") or reply.get("target_user") or {}).get("nick", ""),
                "target_reply_id": reply.get("targetReplyId") or reply.get("targetReplyID") or reply.get("target_reply_id") or "",
                "like_count":      (reply.get("likeInfo") or {}).get("count") or 0,
            }
            at_users = decoded.get("at_users") or []
            if at_users:
                r["at_users"] = at_users
            if decoded.get("images"):
                r["images"] = [{"picUrl": url} for url in decoded["images"]]
            replies.append(r)
        data: dict = {
            "replies":           replies,
            "total_reply_count": structured.get("totalReplyCount", 0),
            "has_more":          bool(structured.get("hasMore", False)),
        }
        attach = structured.get("attachInfo") or structured.get("attach_info") or ""
        if attach:
            data["attach_info"] = attach   # 继续翻页时传回
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
