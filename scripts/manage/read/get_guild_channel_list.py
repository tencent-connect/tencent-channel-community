#!/usr/bin/env python3
"""获取子频道列表。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, ok, parse_positive_int, read_input  # noqa: E402


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    result = call_mcp("get_guild_channel_list", {"guild_ids": [guild_id]})
    ok(decode_bytes_fields(result.get("structuredContent", result)))


if __name__ == "__main__":
    main()
