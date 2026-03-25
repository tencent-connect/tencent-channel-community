"""
Skill: get_interact_notice
描述: 获取用户的互动消息列表，支持翻页查找更多互动消息
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）
"""

import json
import sys
import os
from typing import Any

# 将 skills 根目录加入模块搜索路径，以便导入 _mcp_client
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp, format_timestamp

# tool 名称（与 proto 中 mcp_rule.name 一致）
TOOL_NAME = "get_interact_notice"

# NoticeType 枚举值 → 中文描述
_NOTICE_TYPE_MAP = {
    0: "未知",
    1: "顶/表态我的帖子",
    2: "点赞我的评论",
    3: "点赞我的回复",
    4: "帖子收到评论",
    5: "评论收到回复",
    6: "在帖子评论区被@",
}

# NoticeType 枚举字符串 → 数值
_NOTICE_TYPE_STR_MAP = {
    "NOTICE_TYPE_PSV_DOPOLYLIKE_FEED": 1,
    "NOTICE_TYPE_PSV_DOLIKE_COMMENT": 2,
    "NOTICE_TYPE_PSV_DOLIKE_REPLY": 3,
    "NOTICE_TYPE_PSV_DOCOMMENT": 4,
    "NOTICE_TYPE_PSV_DOREPLY": 5,
    "NOTICE_TYPE_AT_ME": 6,
}

SKILL_MANIFEST = {
    "name": "get-notices",
    "description": (
        "获取用户的互动消息列表，支持翻页查找更多互动消息。"
        "返回被动 feed（互动内容）、原贴 feed、通知样式文案等信息。"
        "通知类型包括：帖子被顶/表态、评论被点赞、回复被点赞、"
        "帖子收到评论、评论收到回复、被@。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "page_num": {
                "type": "integer",
                "description": "请求数量，表示期望返回的通知条数，默认20"
            },
            "attach_info": {
                "type": "string",
                "description": (
                    "翻页透传字段，首次请求不填，"
                    "后续翻页填上一次响应返回的 attach_info"
                )
            },
            "guild_id": {
                "type": "string",
                "description": "频道ID，用于获取某个频道内的消息通知，传0表示查询全局消息"
            }
        },
        "required": []
    }
}


def _extract_richtext(rich_text: dict) -> str:
    """_extract_richtext 从 StRichText 对象中提取可读文本。"""
    if not rich_text or not isinstance(rich_text, dict):
        return ""
    contents = rich_text.get("contents") or []
    parts = []
    for item in contents:
        if not isinstance(item, dict):
            continue
        text_content = (
            item.get("textContent") or item.get("text_content") or {}
        )
        if isinstance(text_content, dict) and text_content.get("text"):
            parts.append(text_content["text"])
            continue
        at_content = (
            item.get("atContent") or item.get("at_content") or {}
        )
        if isinstance(at_content, dict):
            at_text = at_content.get("text") or ""
            user = at_content.get("user") or {}
            nick = user.get("nick") or ""
            if at_text:
                parts.append(at_text)
            elif nick:
                parts.append(f"@{nick}")
            continue
        emoji_content = (
            item.get("emojiContent") or item.get("emoji_content") or {}
        )
        if isinstance(emoji_content, dict) and emoji_content.get("id"):
            parts.append(f"[表情:{emoji_content.get('id')}]")
            continue
    return "".join(parts)


def _extract_images(rich_text: dict) -> list:
    """_extract_images 从 StRichText 的 images 字段提取图片 URL。"""
    if not rich_text or not isinstance(rich_text, dict):
        return []
    images = rich_text.get("images") or []
    return [
        img.get("picUrl") or img.get("pic_url") or img.get("url") or ""
        for img in images
        if isinstance(img, dict)
        and (img.get("picUrl") or img.get("pic_url") or img.get("url"))
    ]


def _format_poster(poster: dict) -> dict:
    """_format_poster 格式化 StUser/Poster 信息。"""
    if not poster or not isinstance(poster, dict):
        return {}
    result = {}
    # StUser 用 id，Poster 用 tinyid
    uid = (
        poster.get("id") or poster.get("tinyid")
        or poster.get("tinyId") or ""
    )
    if uid:
        result["id"] = str(uid)
    nick = poster.get("nick") or ""
    if nick:
        result["nick"] = nick
    icon = poster.get("icon") or poster.get("avatar") or ""
    if icon:
        result["icon"] = icon
    return result


def _format_feed(feed: dict) -> dict:
    """_format_feed 从 StFeed 中提取关键信息。"""
    if not feed or not isinstance(feed, dict):
        return {}
    result: dict[str, Any] = {}

    feed_id = feed.get("id") or ""
    if feed_id:
        result["feed_id"] = feed_id

    poster = feed.get("poster") or {}
    formatted_poster = _format_poster(poster)
    if formatted_poster:
        result["poster"] = formatted_poster

    title = feed.get("title") or {}
    title_text = _extract_richtext(title) if isinstance(title, dict) else ""
    if title_text:
        result["title"] = title_text

    contents = feed.get("contents") or {}
    content_text = (
        _extract_richtext(contents) if isinstance(contents, dict) else ""
    )
    if content_text:
        result["content"] = content_text

    create_time = feed.get("createTime") or feed.get("create_time") or ""
    if create_time:
        result["create_time"] = format_timestamp(create_time)
        result["create_time_raw"] = int(create_time)   # 秒级，供 do_comment/del_feed 链式使用

    images = feed.get("images") or []
    if isinstance(images, list) and images:
        img_urls = [
            img.get("picUrl") or img.get("pic_url") or img.get("url") or ""
            for img in images
            if isinstance(img, dict)
            and (
                img.get("picUrl") or img.get("pic_url") or img.get("url")
            )
        ]
        if img_urls:
            result["images"] = img_urls

    comment_count = feed.get("commentCount") or feed.get("comment_count")
    if comment_count:
        result["comment_count"] = int(comment_count)

    channel_info = feed.get("channelInfo") or feed.get("channel_info") or {}
    if isinstance(channel_info, dict):
        ch_name = channel_info.get("name") or ""
        if ch_name:
            result["channel_name"] = ch_name

    return result


def _format_patton_info(patton: dict) -> dict:
    """_format_patton_info 从 StNoticePattonInfo 中提取样式文案。"""
    if not patton or not isinstance(patton, dict):
        return {}
    result: dict[str, Any] = {}

    patton_type = patton.get("pattonType") or patton.get("patton_type") or 0
    if patton_type:
        result["patton_type"] = patton_type

    plain_txt = patton.get("plainTxt") or patton.get("plain_txt") or {}
    if not isinstance(plain_txt, dict):
        return result

    txt_info = plain_txt.get("txtInfo") or plain_txt.get("txt_info") or {}
    if isinstance(txt_info, dict):
        content = txt_info.get("content") or {}
        text = _extract_richtext(content) if isinstance(content, dict) else ""
        if text:
            result["text"] = text

        ref = (
            txt_info.get("contentOfReference")
            or txt_info.get("content_of_reference") or {}
        )
        ref_text = _extract_richtext(ref) if isinstance(ref, dict) else ""
        if ref_text:
            result["reference_text"] = ref_text

        ref_images = (
            _extract_images(ref) if isinstance(ref, dict) else []
        )
        if ref_images:
            result["reference_images"] = ref_images

    operation = plain_txt.get("operation") or {}
    if isinstance(operation, dict):
        schema = operation.get("schema") or ""
        if schema:
            result["schema"] = schema

    return result


def _resolve_notice_type(raw_type) -> str:
    """_resolve_notice_type 将通知类型枚举值/字符串转为中文描述。"""
    if isinstance(raw_type, str):
        raw_type = _NOTICE_TYPE_STR_MAP.get(raw_type, 0)
    return _NOTICE_TYPE_MAP.get(int(raw_type or 0), f"未知({raw_type})")


# =========================================================
# Skill 入口
# =========================================================

def run(params: dict) -> dict:
    """
    run Skill 主入口，供 agent 框架调用。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {
            "success": True,
            "data": {
                "notices": [
                    {
                        "type": str,
                        "status": str,
                        "psv_feed": {...},
                        "origine_feed": {...},
                        "patton_info": {...}
                    }
                ],
                "total_num": int,
                "is_finish": bool,
                "attach_info": str
            }
        }
        或 {"success": False, "error": "..."}
    """
    arguments: dict[str, Any] = {}

    if "page_num" in params:
        arguments["page_num"] = int(params["page_num"])

    if "attach_info" in params:
        arguments["attach_info"] = params["attach_info"]

    if "guild_id" in params:
        arguments["guild_id"] = params["guild_id"]

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}

        # ── 解析通知列表 ─────────────────────────────────
        notices = []
        for notice in structured.get("notices") or []:
            n: dict[str, Any] = {}

            # 通知类型
            n["type"] = _resolve_notice_type(notice.get("type") or 0)

            # 通知状态
            status = notice.get("status") or 0
            if status:
                n["status"] = str(status)

            # 被动 feed（互动内容）
            psv_feed = (
                notice.get("psvFeed") or notice.get("psv_feed") or {}
            )
            formatted_psv = _format_feed(psv_feed)
            if formatted_psv:
                n["psv_feed"] = formatted_psv

            # 原贴 feed
            origine_feed = (
                notice.get("origineFeed")
                or notice.get("origine_feed") or {}
            )
            formatted_orig = _format_feed(origine_feed)
            if formatted_orig:
                n["origine_feed"] = formatted_orig

            # 样式信息
            patton = (
                notice.get("pattonInfo")
                or notice.get("patton_info") or {}
            )
            formatted_patton = _format_patton_info(patton)
            if formatted_patton:
                n["patton_info"] = formatted_patton

            notices.append(n)

        # ── 整理分页字段 ─────────────────────────────────
        is_finish = bool(
            structured.get("isFinish")
            or structured.get("is_finish")
            or False
        )
        total_num = int(
            structured.get("totalNum")
            or structured.get("total_num")
            or 0
        )
        data: dict[str, Any] = {
            "notices": notices,
            "total_num": total_num,
            "is_finish": is_finish,
        }
        attach_info = (
            structured.get("attachInfo")
            or structured.get("attach_info")
            or ""
        )
        if not is_finish and attach_info:
            data["attach_info"] = attach_info
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# 本地测试入口
# =========================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
