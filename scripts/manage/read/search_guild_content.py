#!/usr/bin/env python3
"""搜索频道内容，默认搜索频道。

当 scope=channel 时，自动对每个结果补取频道资料和分享短链（最多 10 个）。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, fail, humanize_timestamps, ok, optional_str, read_input  # noqa: E402

TAB_MASK_MAP = {
    "all": "1",
    "channel": "3",
    "feed": "4",
    "author": "5",
    "全部": "1",
    "频道": "3",
    "帖子": "4",
    "作者": "5",
}

MAX_ENRICH = 10


def _fetch_guild_info(guild_id: str) -> dict:
    try:
        result = call_mcp(
            "get_guild_info",
            {
                "filter": {
                    "info": {
                        "uint32_create_time": 1,
                        "uint32_member_num": 1,
                        "uint32_guild_name": 1,
                        "uint32_profile": 1,
                        "uint32_guild_number": 1,
                        "uint32_face_seq": 1,
                    }
                },
                "req_guild_infos": [{"guild_id": guild_id}],
            },
        )
        data = decode_bytes_fields(result.get("structuredContent", result))
        for key in ("rspGuildInfo", "rsp_guild_info", "guildInfos", "guild_infos"):
            infos = data.get(key)
            if isinstance(infos, list) and infos:
                inner = infos[0]
                for k in ("msgGuildInfo", "msg_guild_info", "guildInfo", "guild_info"):
                    if isinstance(inner.get(k), dict):
                        return inner[k]
                return inner
        return {}
    except (SystemExit, Exception):
        return {}


def _fetch_share_url(guild_id: str) -> str:
    try:
        result = call_mcp(
            "get_share_url",
            {"guildId": guild_id, "isShortLink": True},
        )
        sc = result.get("structuredContent", result)
        if isinstance(sc, dict):
            for key in ("url", "shareUrl"):
                val = sc.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        content = result.get("content")
        if isinstance(content, list):
            import re
            for item in content:
                text = item.get("text", "") if isinstance(item, dict) else ""
                match = re.search(r'"(?:url|shareUrl)"\s*:\s*"([^"]+)"', text)
                if match:
                    return match.group(1)
        return ""
    except (SystemExit, Exception):
        return ""


def _enrich_channel_results(items: list) -> list:
    """对频道搜索结果补取资料和分享短链。"""
    enriched = []
    for item in items[:MAX_ENRICH]:
        guild_id = str(item.get("id", ""))
        if not guild_id:
            enriched.append(item)
            continue

        info = _fetch_guild_info(guild_id)
        share_url = _fetch_share_url(guild_id)

        entry = {"guild_id": guild_id}
        if info:
            for key in ("bytesGuildName", "bytes_guild_name"):
                if info.get(key):
                    entry["name"] = info[key]
                    break
            for key in ("bytesProfile", "bytes_profile"):
                if info.get(key):
                    entry["profile"] = info[key]
                    break
            for key in ("bytesGuildNumber", "bytes_guild_number"):
                if info.get(key):
                    entry["guild_number"] = info[key]
                    break
            for key in ("uint32MemberNum", "uint32_member_num"):
                if info.get(key):
                    entry["member_count"] = info[key]
                    break
        if share_url:
            entry["share_url"] = share_url

        enriched.append(entry)
    return enriched


def main():
    params = read_input()
    keyword = optional_str(params, "keyword") or optional_str(params, "key_word")
    if not keyword:
        fail("参数 keyword 不能为空")

    scope = optional_str(params, "scope", "channel").lower()
    tab_mask = TAB_MASK_MAP.get(scope, scope if scope in {"1", "3", "4", "5"} else "3")

    rank_type = optional_str(params, "rank_type", "CHANNEL_RANK_TYPE_SMART") or "CHANNEL_RANK_TYPE_SMART"
    result = call_mcp(
        "search_guild_content",
        {
            "key_word": keyword,
            "tab": {"tab_mask": tab_mask},
            "session_info": optional_str(params, "session_info", ""),
            "channel_condition_filter": {"rank_type": rank_type},
            "disable_correction_query": bool(params.get("disable_correction_query", False)),
        },
    )
    data = decode_bytes_fields(result.get("structuredContent", result))

    is_channel_scope = tab_mask == "3"
    if is_channel_scope and isinstance(data, dict):
        tab_result = data.get("tabContentResult", data.get("tab_content_result", {}))
        items = tab_result.get("resultItems", tab_result.get("result_items", []))
        if items:
            if len(items) <= MAX_ENRICH:
                data["channels"] = _enrich_channel_results(items)
                data["enriched"] = True
            else:
                data["channels"] = [{"guild_id": str(it.get("id", ""))} for it in items]
                data["share_url_hint"] = f"频道数量较多（{len(items)}个），如需查看某个频道的分享链接，请告诉我具体是哪个"

    ok(humanize_timestamps(data))


if __name__ == "__main__":
    main()
