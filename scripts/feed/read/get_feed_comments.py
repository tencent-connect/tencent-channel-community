"""
Skill: get_feed_comments
描述: 获取指定帖子的评论列表，支持排序和翻页，每条评论含首页回复预览
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
from _richtext import decode_richtext, decode_richtext_dict

# tool 名称（与 proto 中 mcp_rule.name 一致）
TOOL_NAME = "get_feed_comments"

SKILL_MANIFEST = {
    "name": "get-feed-comments",
    "description": (
        "获取指定帖子的评论列表，支持按时间正序或倒序排列，支持翻页。"
        "返回每条评论的内容、作者、时间、点赞数，以及每条评论的前几条回复预览。"
        "当评论的 has_more_replies=true 时，可调用 get_next_page_replies 加载更多回复。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "帖子ID，必填"
            },
            "guild_id": {
                "type": "integer",
                "description": "频道ID，uint64，选填"
            },
            "channel_id": {
                "type": "integer",
                "description": "板块（子频道）ID，uint64，选填"
            },
            "page_size": {
                "type": "integer",
                "description": "每页评论数量，默认20，最大20"
            },
            "rank_type": {
                "type": "integer",
                "description": "评论排序：1=时间正序，2=时间倒序；默认0"
            },
            "attach_info": {
                "type": "string",
                "description": "翻页透传字段，首次请求不填，后续翻页填上一次响应返回的 attach_info"
            },
            "ext_info": {
                "type": "object",
                "description": "公共扩展透传字段，翻页时将上一次响应返回的 ext_info 原样填入"
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
                "ext_info": dict,    # 公共扩展字段，下次翻页时原样填入请求的 ext_info
                "vec_comment": [
                    {
                        "id": str,               # 评论ID，用于 get_next_page_replies
                        "post_user": {           # 评论者信息
                            "id": str,
                            "nick": str
                        },
                        "create_time": int,      # 评论时间（秒级时间戳）
                        "content": str,          # 评论内容
                        "at_users": [            # 被@的用户列表（有at时出现）
                            {"id": str, "nick": str}
                        ],
                        "reply_count": int,      # 回复总数
                        "vec_reply": [...],      # 首页回复预览
                        "like_info": {           # 点赞信息
                            "count": int,
                            "status": int
                        },
                        "next_page_reply": bool, # true 时可调用 get_next_page_replies
                        "attach_info": str       # 拉下一页回复时透传
                    }
                ],
                "is_finish": int,    # 是否拉取完毕，0否1是
                "attch_info": str    # 下次翻页透传字段
            }
        }
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err
    arguments: dict[str, Any] = {
        "feedId": params["feed_id"],
    }

    if "ext_info" in params:
        arguments["ext_info"] = params["ext_info"]

    channel_sign: dict[str, str] = {}
    if "guild_id" in params:
        channel_sign["guild_id"] = str(params["guild_id"])
    if "channel_id" in params:
        channel_sign["channel_id"] = str(params["channel_id"])
    if channel_sign:
        arguments["channelSign"] = channel_sign

    if "page_size" in params:
        arguments["listNum"] = int(params["page_size"])
    if "rank_type" in params:
        arguments["rankingType"] = int(params["rank_type"])
    if "attach_info" in params:
        arguments["attach_info"] = params["attach_info"]
    arguments["replyListNum"] = int(params.get("reply_list_num", 1))
    arguments["render_sticker"] = True

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        # ── 解码 RichText，规范化评论和回复字段 ──────────────────────
        comments = []
        for comment in structured.get("vecComment", []):
            # 优先用 richContents（含 sticker URL），回退到 content（base64 protobuf）
            rich = comment.get("richContents") or {}
            decoded = decode_richtext_dict(rich) if rich else decode_richtext(comment.get("content", ""))
            # 规范化评论字段名（camelCase → snake_case）
            c = {
                "id":           comment.get("id", ""),
                "content":      decoded,
                "create_time":  comment.get("createTime", ""),
                "post_user":    comment.get("postUser") or comment.get("post_user") or {},
                "reply_count":  comment.get("replyCount") or comment.get("reply_count") or 0,
                "like_count":   (comment.get("likeInfo") or {}).get("count") or 0,
                "attach_info":  comment.get("attachInfo") or comment.get("attach_info") or "",
            }
            # at_users
            at_users = decoded.get("at_users") or []
            if at_users:
                c["at_users"] = at_users
            # 评论图片：从 richContents.images 提取（已在 decode_richtext_dict 中处理）
            if decoded.get("images"):
                c["images"] = [{"picUrl": url} for url in decoded["images"]]
            # 首页回复预览
            vec_reply = comment.get("vecReply", [])
            if vec_reply:
                replies = []
                for reply in vec_reply:
                    reply_rich = reply.get("richContents") or {}
                    reply_decoded = decode_richtext_dict(reply_rich) if reply_rich else decode_richtext(reply.get("content", ""))
                    r = {
                        "id":          reply.get("id", ""),
                        "content":     reply_decoded,
                        "create_time": reply.get("createTime", ""),
                        "post_user":   reply.get("postUser") or reply.get("post_user") or {},
                    }
                    reply_at_users = reply_decoded.get("at_users") or []
                    if reply_at_users:
                        r["at_users"] = reply_at_users
                    if reply_decoded.get("images"):
                        r["images"] = [{"picUrl": url} for url in reply_decoded["images"]]
                    replies.append(r)
                c["replies_preview"] = replies
            if c["reply_count"] > len(vec_reply):
                c["has_more_replies"] = True
            comments.append(c)
        # ── 整理分页字段 ──────────────────────────────────────────────
        is_finish = bool(structured.get("isFinish", True))
        data: dict = {"comments": comments, "is_finish": is_finish}
        if not is_finish:
            raw_attach = structured.get("attchInfo") or structured.get("attach_info") or ""
            if raw_attach:
                data["attach_info"] = raw_attach   # 翻页时原样传回
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
