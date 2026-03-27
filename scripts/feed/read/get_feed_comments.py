"""
Skill: get_feed_comments
描述: 获取指定帖子的评论列表，支持排序和翻页，每条评论含首页回复预览
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
from _richtext import decode_richtext, decode_richtext_dict

# tool 名称（与 proto 中 mcp_rule.name 一致）
TOOL_NAME = "get_feed_comments"

SKILL_MANIFEST = {
    "name": "get-feed-comments",
    "description": (
        "获取指定帖子的评论列表，支持按时间正序或倒序排列，支持翻页。"
        "返回每条评论的内容、作者昵称、时间、点赞数，以及每条评论的前几条回复预览。"
        "当评论的 has_more_replies=true 时，该评论对象里的 attach_info 字段即为调用 get_next_page_replies 所需的翻页游标，"
        "直接将其传入 get_next_page_replies 的 attach_info 参数即可，无需额外请求。"
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
                "description": "频道ID，uint64 字符串，建议填写"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串，建议填写"
            },
            "page_size": {
                "type": "integer",
                "description": "每页评论数量，默认20，最大20"
            },
            "rank_type": {
                "type": "integer",
                "description": "评论排序：1=时间正序，2=时间倒序；默认0"
            },
            "reply_list_num": {
                "type": "integer",
                "description": "每条评论预加载的回复数量，默认1，最大10。适当增大可减少后续调用 get_next_page_replies 的次数"
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


def _clean_user(user: dict) -> dict:
    """过滤用户对象，只保留昵称等公开字段，移除内部 id/tinyId 等字段。"""
    if not user:
        return {}
    cleaned = {}
    if user.get("nick"):
        cleaned["nick"] = user["nick"]
    if user.get("icon"):
        icon = user["icon"]
        if isinstance(icon, dict) and icon.get("iconUrl"):
            cleaned["icon_url"] = icon["iconUrl"]
    return cleaned


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
                "comments": [
                    {
                        "comment_index": int,    # 评论序号（用于 get_next_page_replies 的 comment_id）
                        "author": str,           # 评论者昵称
                        "create_time": str,      # 评论时间（可读格式）
                        "content": str,          # 评论内容
                        "reply_count": int,      # 回复总数
                        "like_count": int,       # 点赞数
                        "replies_preview": [...],# 首页回复预览
                        "has_more_replies": bool # true 时可调用 get_next_page_replies
                    }
                ],
                "is_finish": bool,   # 是否拉取完毕
                "attach_info": str   # 下次翻页透传字段
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

    # channel_sign 必须始终发送（服务端校验 channel_sign != nil），值为 "0" 时也要传
    try:
        channel_sign: dict = {
            "guild_id":   str(int(params["guild_id"]))   if "guild_id"   in params else "0",
            "channel_id": str(int(params["channel_id"])) if "channel_id" in params else "0",
        }
    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"guild_id 或 channel_id 格式无效，应为整数字符串：{e}"}
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
        for idx, comment in enumerate(structured.get("vecComment", [])):
            # 优先用 richContents（含 sticker URL），回退到 content（base64 protobuf）
            rich = comment.get("richContents") or {}
            decoded = decode_richtext_dict(rich) if rich else decode_richtext(comment.get("content", ""))
            # 获取评论者信息（只保留昵称，过滤 id/tinyId 等内部字段）
            raw_post_user = comment.get("postUser") or comment.get("post_user") or {}
            author_nick = raw_post_user.get("nick", "")
            author_id = str(raw_post_user.get("id", "") or raw_post_user.get("tinyId", "") or "")
            raw_create_time = comment.get("createTime", 0)

            # 规范化评论字段名（移除 id/post_user.id 等内部字段）
            c = {
                "comment_index": idx + 1,        # 用于后续操作的序号，不暴露内部 ID
                "comment_id":    comment.get("id", ""),          # 供 do_reply / do_comment 使用
                "author_id":     author_id,                       # 供 do_reply 的 comment_author_id 使用
                "content":      decoded,
                "create_time":  format_timestamp(raw_create_time),
                "create_time_raw": int(raw_create_time or 0),    # 秒级时间戳，供 do_reply 的 comment_create_time 使用
                "author":       author_nick,
                "reply_count":  comment.get("replyCount") or comment.get("reply_count") or 0,
                "like_count":   (comment.get("likeInfo") or {}).get("count") or 0,
            }
            # 保留 attach_info 用于翻页（不是内部 ID）
            attach_info = comment.get("attachInfo") or comment.get("attach_info") or ""
            if attach_info:
                c["attach_info"] = attach_info

            # at_users：只保留昵称
            at_users = decoded.get("at_users") or []
            if at_users:
                c["at_users"] = [u.get("nick", "") for u in at_users if u.get("nick")]
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
                    raw_reply_user = reply.get("postUser") or reply.get("post_user") or {}
                    raw_target_user = reply.get("targetUser") or reply.get("target_user") or {}
                    r = {
                        "reply_id":       reply.get("id", ""),                                      # 供删除回复使用
                        "author_id":      str(raw_reply_user.get("id", "") or raw_reply_user.get("tinyId", "") or ""),
                        "content":        reply_decoded,
                        "create_time":    format_timestamp(reply.get("createTime", "")),
                        "create_time_raw": int(reply.get("createTime") or 0),
                        "author":         raw_reply_user.get("nick", ""),
                        "target_reply_id": reply.get("targetReplyId") or reply.get("targetReplyID") or reply.get("target_reply_id") or "",  # 供回复某条回复时传入 do_reply
                        "target_user_id":  str((raw_target_user.get("id") or raw_target_user.get("tinyId") or "")),  # 供 do_reply 的 target_user_id 使用
                    }
                    if raw_target_user.get("nick"):
                        r["target_user"] = raw_target_user.get("nick", "")
                    reply_at_users = reply_decoded.get("at_users") or []
                    if reply_at_users:
                        r["at_users"] = [u.get("nick", "") for u in reply_at_users if u.get("nick")]
                    if reply_decoded.get("images"):
                        r["images"] = [{"picUrl": url} for url in reply_decoded["images"]]
                    replies.append(r)
                c["replies_preview"] = replies
            if c["reply_count"] > len(vec_reply):
                c["has_more_replies"] = True
            comments.append(c)
        # ── 整理分页字段 ──────────────────────────────────────────────
        is_finish = bool(structured.get("isFinish") or False)
        data: dict = {"comments": comments, "is_finish": is_finish}
        if not is_finish:
            raw_attach = structured.get("attchInfo") or structured.get("attach_info") or ""
            if raw_attach:
                data["attach_info"] = raw_attach   # 翻页时原样传回
        # 回传 guild_id / channel_id，供链式调用 get_next_page_replies 时透传
        if "guild_id" in params:
            data["guild_id"] = str(params["guild_id"])
        if "channel_id" in params:
            data["channel_id"] = str(params["channel_id"])
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)