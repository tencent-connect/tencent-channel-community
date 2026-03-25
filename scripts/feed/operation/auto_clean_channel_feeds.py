"""
Skill: auto_clean_channel_feeds
描述: 扫描频道（或指定版块）的最新帖子，获取每篇帖子的完整标题和正文，
     返回帖子列表供 AI 自主判断是否违规（水帖、广告、外链、二维码、交友、风险等），
     AI 判断后可直接调用 del_feed 删除目标帖子。

MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）

工作流程：
    1. 按 scan_interval 确定时间窗口，分页拉取目标频道/版块的最新帖子
    2. 获取每篇帖子的完整标题和正文内容
    3. 返回帖子列表，由 AI 根据语义理解自主判断是否需要删除
    4. AI 可根据返回的 feed_id / author_id / create_time 调用 del_feed 执行删除
"""

import json
import sys
import os
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp

TOOL_NAME = "auto-clean-channel-feeds"

# 默认常量
DEFAULT_SCAN_INTERVAL = 60   # 分钟：扫描最近 N 分钟内发布的帖子
DEFAULT_MAX_FEEDS     = 50   # 单次最多扫描帖子数
DEFAULT_BATCH_SIZE    = 20   # 每页拉取数量

# ============================================================
# Skill Manifest
# ============================================================

SKILL_MANIFEST = {
    "name": TOOL_NAME,
    "description": (
        "扫描频道（或指定版块）最近发布的帖子，获取每篇帖子的标题和正文内容，"
        "返回帖子列表供 AI 自主判断是否违规（水帖、广告帖、外链帖、二维码帖、交友帖、风险帖等）。"
        "AI 根据返回内容判断后，可调用 del_feed 删除违规帖子。"
        "scan_interval 决定扫描最近多少分钟内发布的帖子；"
        "max_feeds 控制单次最多返回的帖子数。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，必填"
            },
            "channel_id": {
                "type": "string",
                "description": (
                    "版块（子频道）ID，uint64 字符串，可选。"
                    "填写则只扫描该版块；不填则扫描整个频道主页"
                )
            },
            "scan_interval": {
                "type": "integer",
                "description": (
                    f"扫描时间窗口（分钟），默认 {DEFAULT_SCAN_INTERVAL}。"
                    "只返回最近 N 分钟内发布的帖子。"
                    "设为 0 则不限制时间，返回最近 max_feeds 条"
                )
            },
            "max_feeds": {
                "type": "integer",
                "description": (
                    f"本次最多返回的帖子数，默认 {DEFAULT_MAX_FEEDS}，最大 200。"
                )
            },
        },
        "required": ["guild_id"]
    }
}


# ============================================================
# 工具函数
# ============================================================

def _extract_rich_text(rich_text: dict | str | None) -> str:
    """从 StRichText 结构中提取纯文本。"""
    if not rich_text:
        return ""
    if isinstance(rich_text, str):
        return rich_text
    contents = rich_text.get("contents", [])
    parts = []
    for item in contents:
        tc = item.get("textContent") or item.get("text_content")
        if tc and isinstance(tc, dict):
            parts.append(tc.get("text", ""))
        elif isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _parse_structured(raw: dict) -> dict:
    """从 call_mcp 返回值中提取 structuredContent，若无则回退到整体。"""
    return raw.get("structuredContent") or raw


def _check_mcp_error(raw: dict) -> None:
    """检查 MCP 返回的业务错误，有错误则抛出 RuntimeError。"""
    if raw.get("isError"):
        meta = raw.get("_meta", {}).get("AdditionalFields", {})
        code = meta.get("retCode", -1)
        msg  = meta.get("errMsg", "未知错误")
        raise RuntimeError(f"MCP 业务错误 code={code}: {msg}")
    meta     = (_parse_structured(raw)).get("_meta", {}).get("AdditionalFields", {})
    ret_code = meta.get("retCode")
    if ret_code is not None and ret_code != 0:
        msg = meta.get("errMsg", "") or meta.get("retMsg", "未知错误")
        raise RuntimeError(f"MCP 业务错误 code={ret_code}: {msg}")


def _fetch_feeds_page(
    guild_id: int,
    channel_id: int | None,
    count: int,
    attach_info: str | None,
) -> dict:
    """拉取一页帖子摘要，返回 {"feeds": [...], "is_finish": bool, "attach_info": str|None}。"""
    if channel_id:
        args: dict[str, Any] = {
            "channel_sign": {
                "guild_id":   str(guild_id),
                "channel_id": str(channel_id),
            },
            "from":           1,
            "render_sticker": True,
            "count":          count,
            "sort_option":    1,
        }
        if attach_info:
            args["feed_attch_info"] = attach_info
        raw  = call_mcp("get_channel_timeline_feeds", args)
        _check_mcp_error(raw)
        data = _parse_structured(raw)
        feeds        = data.get("feeds", [])
        next_attach  = data.get("feedAttchInfo") or None
        raw_finish   = data.get("isFinish")
        is_finish    = bool(int(raw_finish)) if raw_finish is not None else (not feeds or not next_attach)
    else:
        args = {
            "guild_id":    str(guild_id),
            "count":       count,
            "get_type":    2,
            "sort_option": 1,
        }
        if attach_info:
            args["feed_attach_info"] = attach_info
        raw  = call_mcp("get_guild_feeds", args)
        _check_mcp_error(raw)
        data = _parse_structured(raw)
        feeds       = data.get("feeds", [])
        next_attach = data.get("feedAttachInfo") or data.get("feed_attach_info") or None
        is_finish   = not feeds or not next_attach

    return {"feeds": feeds, "is_finish": is_finish, "attach_info": next_attach}


def _fetch_feed_detail(
    feed_id: str,
    guild_id: int,
    channel_id: int | None,
    author_id: str,
    create_time: int,
) -> dict:
    """获取单帖完整详情，返回 structuredContent.feed 子对象。"""
    args: dict[str, Any] = {
        "feed_id":     feed_id,
        "guild_id":    str(guild_id),
        "author_id":   str(author_id),
        "create_time": str(create_time),
    }
    if channel_id:
        args["channel_id"] = str(channel_id)
    raw  = call_mcp("get_feed_detail", args)
    _check_mcp_error(raw)
    data = _parse_structured(raw)
    return data.get("feed", {})


# ============================================================
# Skill 主入口
# ============================================================

def run(params: dict) -> dict:
    """
    扫描频道最新帖子，返回帖子列表（含标题和正文）供 AI 判断。

    返回格式：
    {
        "success": true,
        "data": {
            "summary": {
                "total_scanned":     50,
                "scan_interval":     60,
                "guild_id":          123456789,
                "channel_id":        987654321,
                "time_window_start": 1700000000,
                "duration_seconds":  3.2
            },
            "feeds": [
                {
                    "feed_id":     "B_xxx",
                    "title":       "帖子标题",
                    "content":     "帖子正文内容",
                    "author_id":   "123456",
                    "create_time": 1700000000
                },
                ...
            ],
            "errors": [
                {"feed_id": "...", "error": "获取详情失败：..."}
            ]
        }
    }
    """
    # ---------- 参数校验 ----------
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    # ---------- 参数解析 ----------
    guild_id      = int(params["guild_id"])
    channel_id    = int(params["channel_id"]) if params.get("channel_id") else None
    scan_interval = int(params.get("scan_interval", DEFAULT_SCAN_INTERVAL))
    max_feeds     = min(int(params.get("max_feeds", DEFAULT_MAX_FEEDS)), 200)

    # ---------- 计算时间窗口 ----------
    now               = int(time.time())
    time_window_start = (now - scan_interval * 60) if scan_interval > 0 else 0

    # ---------- 初始化 ----------
    task_start    = time.time()
    total_scanned = 0
    feeds_result: list[dict] = []
    errors:       list[dict] = []

    attach_info: str | None = None
    is_finish = False

    # ---------- 主循环：分页拉取 ----------
    while not is_finish and total_scanned < max_feeds:
        batch = min(DEFAULT_BATCH_SIZE, max_feeds - total_scanned)

        try:
            page_result = _fetch_feeds_page(guild_id, channel_id, batch, attach_info)
        except Exception as e:
            return {"success": False, "error": f"拉取帖子列表失败：{e}"}

        feeds_page: list[dict] = page_result.get("feeds", [])
        is_finish   = page_result.get("is_finish", True)
        attach_info = page_result.get("attach_info") or None

        if not feeds_page:
            break

        for feed_summary in feeds_page:
            if total_scanned >= max_feeds:
                is_finish = True
                break

            raw_time = (
                feed_summary.get("createTime")
                or feed_summary.get("create_time")
                or 0
            )
            feed_create_time = int(raw_time)

            # 时间窗口过滤
            if time_window_start > 0 and feed_create_time < time_window_start:
                is_finish = True
                break

            total_scanned += 1

            feed_id   = feed_summary.get("id") or feed_summary.get("feed_id", "")
            poster    = feed_summary.get("poster", {})
            author_id = poster.get("id", "") if isinstance(poster, dict) else str(poster)

            # 从摘要提取标题和正文
            title   = _extract_rich_text(feed_summary.get("title"))
            content = _extract_rich_text(feed_summary.get("contents"))

            # 摘要内容为空时拉取完整详情
            if not title and not content:
                try:
                    detail  = _fetch_feed_detail(feed_id, guild_id, channel_id, author_id, feed_create_time)
                    title   = _extract_rich_text(detail.get("title"))
                    content = _extract_rich_text(detail.get("contents"))
                    feed_create_time = int(
                        detail.get("createTime") or detail.get("create_time") or feed_create_time
                    )
                    if isinstance(detail.get("poster"), dict):
                        author_id = detail["poster"].get("id", author_id)
                except Exception as e:
                    errors.append({"feed_id": feed_id, "error": f"获取详情失败：{e}"})

            feeds_result.append({
                "title":       title,
                "content":     content,
                "create_time": feed_create_time,
            })

    # ---------- 构建返回 ----------
    duration = round(time.time() - task_start, 2)

    return {
        "success": True,
        "data": {
            "summary": {
                "total_scanned":     total_scanned,
                "scan_interval":     scan_interval,
                "guild_id":          guild_id,
                "channel_id":        channel_id,
                "time_window_start": time_window_start,
                "duration_seconds":  duration,
            },
            "feeds":  feeds_result,
            "errors": errors,
        },
    }


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
