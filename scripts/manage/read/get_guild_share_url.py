#!/usr/bin/env python3
"""获取频道分享链接。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import ok, parse_positive_int, read_input, call_mcp, parse_share_url_from_mcp_result  # noqa: E402


def main():
    params = read_input()
    guild_id = parse_positive_int(params.get("guild_id"), "参数 guild_id")
    result = call_mcp(
        "get_share_url",
        {"guild_id": str(guild_id), "is_short_link": True},
    )
    url, share_info = parse_share_url_from_mcp_result(result)
    data = {
        "url": url,
        "shareInfo": share_info,
        "retCode": 0,
        "raw": result,
        "shareType": "channel",
    }
    ok(data)


if __name__ == "__main__":
    main()
