#!/usr/bin/env python3
"""禁言用户。

⚠️ 重要：time_stamp 参数是禁言到期的绝对时间戳（Unix秒级时间戳），不是禁言时长。
- 如需禁言 N 天，应传：当前时间戳 + N*24*3600
- 传 0 表示立即解除禁言
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, ok, parse_nonnegative_int, parse_positive_int, read_input  # noqa: E402


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    if "member_tinyid" in params and "tiny_id" not in params:
        params["tiny_id"] = params.pop("member_tinyid")
    if "tinyid" in params and "tiny_id" not in params:
        params["tiny_id"] = params.pop("tinyid")
    tiny_id = str(parse_positive_int(params.get("tiny_id"), "参数 tiny_id"))
    time_stamp = str(parse_nonnegative_int(params.get("time_stamp"), "参数 time_stamp"))
    result = call_mcp(
        "modify_member_shut_up",
        {
            "guild_id": guild_id,
            "modify_member_shut_up": {
                "tiny_id": tiny_id,
                "time_stamp": time_stamp,
            },
        },
    )
    ok(result.get("structuredContent", result))


if __name__ == "__main__":
    main()
