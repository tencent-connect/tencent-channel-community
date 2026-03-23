#!/usr/bin/env python3
"""加入频道，成功后自动补取分享短链。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, ok, parse_positive_int, read_input  # noqa: E402


def _fetch_share_url(guild_id: str) -> str:
    try:
        result = call_mcp("get_share_url", {"guildId": guild_id, "isShortLink": True})
        sc = result.get("structuredContent", result)
        if isinstance(sc, dict):
            for key in ("url", "shareUrl"):
                val = sc.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return ""
    except (SystemExit, Exception):
        return ""


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    result = call_mcp("join_guild", {"uint64_guild_id": guild_id})
    data = result.get("structuredContent", result)
    if not isinstance(data, dict):
        data = {}

    share_url = _fetch_share_url(guild_id)
    if share_url:
        data["share_url"] = share_url

    ok(data)


if __name__ == "__main__":
    main()
