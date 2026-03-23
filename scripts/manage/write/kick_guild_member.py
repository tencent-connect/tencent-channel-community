#!/usr/bin/env python3
"""踢出频道成员。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, ok, parse_positive_int, read_input  # noqa: E402


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    member_tinyids = params.get("member_tinyids")
    if member_tinyids is None:
        member_tinyids = [params.get("member_tinyid") or params.get("tiny_id") or params.get("tinyid")]
    if not isinstance(member_tinyids, list):
        member_tinyids = [member_tinyids]
    member_tinyids = [str(parse_positive_int(item, "参数 member_tinyid")) for item in member_tinyids]

    result = call_mcp(
        "kick_guild_member",
        {
            "uint64_guild_id": guild_id,
            "rpt_member_tinyid": member_tinyids,
        },
    )
    ok(result.get("structuredContent", result))


if __name__ == "__main__":
    main()
