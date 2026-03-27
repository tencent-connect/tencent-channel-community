"""
Skill: channel-qa-responder
描述: 频道问答自动回复——拉取频道帖子列表，逐一分析是否为求助帖；
     对每个求助帖提取关键词，调用搜索接口在频道内搜索相关帖子，
     整理成答案回复给该帖子；无相关内容时礼貌提示。

工作流程：
    1. 分页拉取频道/版块的帖子列表
    2. 逐一获取帖子详情，判断是否为求助帖（含提问意图）
    3. 对每个求助帖，提取核心关键词
    4. 调用 get_search_guild_feed 按关键词搜索频道内相关帖子
    5. 整理相关帖子内容，生成回复，以评论形式发布到该帖子
       无相关内容时发布礼貌提示评论
    6. 返回本次处理报告

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）
"""

import json
import re
import sys
import os
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp

TOOL_NAME = "channel-qa-responder"

# ---------- 内联发表评论 ----------

def _post_comment(
    feed_id: str,
    feed_create_time,
    commenter_id: str,
    content: str,
    guild_id: int,
    channel_id=None,
) -> dict:
    """内联发表评论，对齐 do_comment skill 的 MCP 参数结构。"""
    comment = {
        "post_user": {"id": ""},
        "create_time": str(int(time.time())),
        "content": content,
    }
    feed = {
        "id": feed_id,
        "poster": {"id": ""},
        "create_time": str(feed_create_time),
    }
    channel_sign: dict = {"guild_id": str(guild_id)}
    if channel_id:
        channel_sign["channel_id"] = str(channel_id)
    feed["channel_info"] = {"sign": channel_sign}

    json_comment_obj = {
        "contents": [{"text_content": {"text": content}, "type": 1, "pattern_id": ""}]
    }
    arguments = {
        "comment_type": 1,
        "comment": comment,
        "feed": feed,
        "json_comment": json.dumps(json_comment_obj, ensure_ascii=False, separators=(",", ":")),
    }
    result = call_mcp("do_comment", arguments)
    if result.get("isError"):
        err = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "unknown error")
        raise RuntimeError(err)
    structured = result.get("structuredContent") or result
    comment_info = structured.get("comment") or {}
    return comment_info

_QUESTION_WORDS_ZH = [
    "什么", "怎么", "怎样", "如何", "为什么", "为啥", "哪里", "哪儿",
    "哪个", "哪些", "谁", "几", "多少", "能否", "能不能", "是否",
    "可以吗", "对吗", "请问", "想问", "想请教", "有没有", "有人知道",
    "求助", "求解", "帮忙", "不明白", "不懂", "搞不清", "不知道",
    "吗", "呢",  # 句尾疑问语气词
]
_QUESTION_WORDS_EN = [
    "what", "how", "why", "where", "who", "which", "when",
    "can i", "can you", "is it", "are there", "does it", "do i",
    "anyone know", "help", "stuck", "not sure", "confused",
]

_STOP_WORDS = set(_QUESTION_WORDS_ZH + _QUESTION_WORDS_EN + [
    "啊", "嗯", "的", "了", "是", "在", "有", "我", "你", "他",
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "i", "you", "he", "she", "we", "they", "it", "this", "that",
])

_NO_MATCH_TEMPLATE = (
    "感谢提问！目前频道内暂时没有找到与「{keywords}」直接相关的帖子。\n\n"
    "你可以：\n"
    "- 在这里继续描述你的具体情况，社区成员会尽力帮忙 🙌\n"
    "- 尝试搜索关键词：{search_hint}"
)

DEFAULT_SCAN_COUNT = 20
DEFAULT_MAX_REFS   = 3

# ---------- Skill Manifest ----------

SKILL_MANIFEST = {
    "name": TOOL_NAME,
    "description": (
        "频道问答自动回复：拉取频道帖子列表，分析每个帖子是否为求助帖，"
        "对求助帖调用搜索接口找到频道内相关帖子并整理回复；无相关内容时礼貌提示。"
        "支持 dry_run 演习模式，仅输出分析结果，不发布任何评论。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，必填"
            },
            "bot_user_id": {
                "type": "string",
                "description": (
                    "Bot 用户ID（tiny_id），string，必填。"
                    "用于发起关键词搜索（uint64_member_tinyid）及发布回复评论"
                )
            },
            "channel_id": {
                "type": "string",
                "description": (
                    "版块（子频道）ID，uint64 字符串。"
                    "填写则只处理该版块帖子；不填则处理整个频道广场"
                )
            },
            "scan_count": {
                "type": "integer",
                "description": f"本次拉取并分析的帖子数量，默认 {DEFAULT_SCAN_COUNT}，最大 100"
            },
            "max_refs": {
                "type": "integer",
                "description": f"每条回复最多引用的参考帖子数，默认 {DEFAULT_MAX_REFS}，最大 5"
            },
            "dry_run": {
                "type": "boolean",
                "description": "演习模式，默认 false。true=仅分析和检索，输出报告，不发布任何评论"
            },
        },
        "required": ["guild_id", "bot_user_id"]
    }
}


# ============================================================
# 辅助：从帖子摘要结构中提取 feed_id 和 author_id
# ============================================================

def _parse_feed_summary(feed_summary: dict) -> tuple[str, str]:
    """从列表接口返回的帖子摘要中提取 feed_id 和 author_id。"""
    feed_id   = feed_summary.get("id") or feed_summary.get("feed_id", "")
    poster    = feed_summary.get("poster") or {}
    author_id = poster.get("id") or feed_summary.get("author_id", "")
    return feed_id, author_id


def _extract_text(rich_text) -> str:
    """从嵌套富文本结构中提取纯文本。
    支持格式：
      - str: 直接返回
      - {"contents": [{"textContent": {"text": "..."}}]}: 提取所有 text 片段
    """
    if not rich_text:
        return ""
    if isinstance(rich_text, str):
        return rich_text
    if isinstance(rich_text, dict):
        parts = []
        for item in rich_text.get("contents", []):
            tc = item.get("textContent", {})
            if tc.get("text"):
                parts.append(tc["text"])
        return " ".join(parts)
    return ""


# ============================================================
# Step 2：判断是否为求助帖
# ============================================================

def _is_question(text: str) -> bool:
    if not text or not text.strip():
        return False
    if "?" in text or "？" in text:
        return True
    text_lower = text.lower()
    for word in _QUESTION_WORDS_ZH:
        if word in text:
            return True
    for word in _QUESTION_WORDS_EN:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            return True
    return False


# ============================================================
# Step 3：提取关键词
# ============================================================

def _extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    cleaned = re.sub(r'[？?！!。，,、；;：:「」『』【】\[\]()（）\s]+', ' ', text)
    tokens: list[str] = []
    tokens += re.findall(r'[a-zA-Z][a-zA-Z0-9_\-\.]*[a-zA-Z0-9]|[a-zA-Z]', cleaned)
    tokens += re.findall(r'[\u4e00-\u9fff]{2,6}', cleaned)
    seen: set[str] = set()
    unique: list[str] = []
    for t in tokens:
        tl = t.lower()
        if tl not in _STOP_WORDS and len(t) >= 2 and tl not in seen:
            seen.add(tl)
            unique.append(t)
    return unique[:max_keywords]


# ============================================================
# Step 4：调用搜索接口查找相关帖子
# ============================================================

def _search_related_feeds(
    guild_id: int,
    bot_user_id: str,
    keywords: list[str],
    exclude_feed_id: str,
    max_refs: int,
) -> list[dict]:
    """调用 get_search_guild_feed 按关键词搜索，排除求助帖自身，返回 Top-N。"""
    query = " ".join(keywords)
    try:
        result = call_mcp("get_search_guild_feed", {
            "uint64_member_tinyid": bot_user_id,
            "guild_id":             str(guild_id),
            "query":                query,
            "search_type":          {"type": 2, "feed_type": 0},
        })
    except Exception:
        return []

    union_result = (result.get("structuredContent") or {}).get("unionResult") or \
                   result.get("union_result", {})
    guild_feeds: list[dict] = union_result.get("guildFeeds", union_result.get("guild_feeds", []))

    refs: list[dict] = []
    for feed in guild_feeds:
        feed_id = feed.get("feedId") or feed.get("feed_id", "")
        if feed_id == exclude_feed_id:
            continue
        refs.append({
            "feed_id": feed_id,
            "title":   feed.get("title", ""),
            "content": (feed.get("content") or feed.get("desc", ""))[:200],
        })
        if len(refs) >= max_refs:
            break
    return refs


# ============================================================
# Step 5：整理生成回复内容
# ============================================================

def _build_reply(question_text: str, refs: list[dict]) -> str:
    lines = [
        f"关于你的提问「{question_text[:40]}{'…' if len(question_text) > 40 else ''}」，"
        "频道内有以下相关讨论可供参考：",
        "",
    ]
    for i, ref in enumerate(refs, 1):
        title   = ref["title"] or f"帖子 {ref['feed_id']}"
        excerpt = ref["content"].strip()[:80].replace("\n", " ")
        lines.append(f"{i}. 《{title}》")
        if excerpt:
            lines.append(f"   {excerpt}{'…' if len(ref['content']) > 80 else ''}")
    lines += ["", "希望对你有帮助！如有更多疑问，欢迎继续提问 🙌"]
    return "\n".join(lines)


def _build_no_match_reply(keywords: list[str]) -> str:
    kw_str      = "、".join(keywords[:3]) if keywords else "相关内容"
    search_hint = " / ".join(f"「{kw}」" for kw in keywords[:3])
    return _NO_MATCH_TEMPLATE.format(keywords=kw_str, search_hint=search_hint)


# ============================================================
# Skill 主入口
# ============================================================

def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    返回格式：
    {
        "success": True,
        "data": {
            "summary": {
                "total_scanned":   20,
                "total_questions": 5,
                "total_replied":   5,
                "dry_run":         false,
                "duration_seconds": 18.4
            },
            "results": [
                {
                    "feed_id": "B_xxx",
                    "title": "帖子标题",
                    "keywords": ["关键词A"],
                    "search_query": "关键词A",
                    "refs_found": 2,
                    "reply_type": "cited" | "no_match",
                    "reply_content": "回复正文",
                    "reply_result": "success" | "failed" | "dry_run",
                    "reply_detail": "comment_id=c_xxx"
                }
            ],
            "errors": [{"feed_id": "...", "error": "..."}]
        }
    }
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    guild_id    = int(params["guild_id"])
    bot_user_id = str(params["bot_user_id"])
    channel_id  = int(params["channel_id"]) if params.get("channel_id") else None
    scan_count  = min(int(params.get("scan_count", DEFAULT_SCAN_COUNT)), 100)
    max_refs    = min(int(params.get("max_refs", DEFAULT_MAX_REFS)), 5)
    dry_run     = bool(params.get("dry_run", False))

    start_time = time.time()
    results: list[dict] = []
    errors:  list[dict] = []

    # ============================================================
    # Step 1：拉取帖子列表（guild_id 传字符串）
    # ============================================================
    try:
        if channel_id:
            page = call_mcp("get_channel_timeline_feeds", {
                "guild_id":    str(guild_id),
                "channel_id":  str(channel_id),
                "count":       scan_count,
                "sort_option": 1,
            })
        else:
            page = call_mcp("get_guild_feeds", {
                "guild_id":    str(guild_id),
                "count":       scan_count,
                "get_type":    2,
                "sort_option": 1,
            })
    except Exception as e:
        return {"success": False, "error": f"拉取帖子列表失败：{e}"}

    feeds_list: list[dict] = page.get("structuredContent", {}).get("feeds", [])
    if not feeds_list:
        return {
            "success": True,
            "data": {
                "summary": {
                    "total_scanned": 0, "total_questions": 0,
                    "total_replied": 0, "dry_run": dry_run,
                    "duration_seconds": round(time.time() - start_time, 2),
                },
                "results": [], "errors": [],
            }
        }

    # ============================================================
    # Step 2~5：逐帖处理
    # ============================================================
    for feed_summary in feeds_list:
        feed_id, author_id = _parse_feed_summary(feed_summary)
        if not feed_id:
            continue

        # --- 获取帖子详情（guild_id 传字符串）---
        try:
            detail_rsp  = call_mcp("get_feed_detail", {
                "feed_id":  feed_id,
                "guild_id": str(guild_id),
                **({"channel_id": str(channel_id)} if channel_id else {}),
                **({"author_id": str(author_id)} if author_id else {}),
            })
            feed_detail = detail_rsp.get("structuredContent", {}).get("feed", {})
        except Exception as e:
            errors.append({"feed_id": feed_id, "error": f"获取详情失败：{e}"})
            continue

        title       = _extract_text(feed_detail.get("title", ""))
        content     = _extract_text(feed_detail.get("contents", ""))
        create_time = feed_detail.get("createTime", 0)
        author_id   = (feed_detail.get("poster") or {}).get("id", author_id)
        # 从帖子详情中取实际 channel_id，优先于调用参数传入的
        feed_channel_id = (feed_detail.get("channelInfo") or {}).get("sign", {}).get("channelId") or channel_id
        full_text   = f"{title} {content}".strip()

        # --- Step 2：判断是否为求助帖 ---
        if not _is_question(full_text):
            continue

        # --- Step 3：提取关键词 ---
        keywords = _extract_keywords(full_text)
        if not keywords:
            errors.append({"feed_id": feed_id, "error": "无法提取有效关键词"})
            continue

        search_query = " ".join(keywords)

        # --- Step 4：搜索相关帖子 ---
        refs = _search_related_feeds(
            guild_id, bot_user_id, keywords,
            exclude_feed_id=feed_id,
            max_refs=max_refs,
        )

        # --- Step 5：生成回复内容 ---
        if refs:
            reply_content = _build_reply(title or content[:60], refs)
            reply_type    = "cited"
        else:
            reply_content = _build_no_match_reply(keywords)
            reply_type    = "no_match"

        base_record: dict[str, Any] = {
            "feed_id":       feed_id,
            "title":         title,
            "keywords":      keywords,
            "search_query":  search_query,
            "refs_found":    len(refs),
            "reply_type":    reply_type,
            "reply_content": reply_content,
        }

        if dry_run:
            results.append({**base_record, "reply_result": "dry_run", "reply_detail": "演习模式，未发布评论"})
            continue

        try:
            comment_info = _post_comment(
                feed_id=feed_id,
                feed_create_time=create_time,
                commenter_id=bot_user_id,
                content=reply_content,
                guild_id=guild_id,
                channel_id=feed_channel_id,
            )
            comment_id = comment_info.get("id") or comment_info.get("commentId") or ""
            results.append({**base_record, "reply_result": "success", "reply_detail": f"comment_id={comment_id}"})
        except Exception as e:
            results.append({**base_record, "reply_result": "failed", "reply_detail": str(e)})

    # ---------- 报告 ----------
    total_questions = len(results)
    total_replied   = sum(1 for r in results if r["reply_result"] in ("success", "dry_run"))
    duration        = round(time.time() - start_time, 2)

    return {
        "success": True,
        "data": {
            "summary": {
                "total_scanned":   len(feeds_list),
                "total_questions": total_questions,
                "total_replied":   total_replied,
                "dry_run":         dry_run,
                "guild_id":        guild_id,
                "channel_id":      channel_id,
                "duration_seconds": duration,
            },
            "results": results,
            "errors":  errors,
        }
    }


# ============================================================
# 本地测试入口
# ============================================================

if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
