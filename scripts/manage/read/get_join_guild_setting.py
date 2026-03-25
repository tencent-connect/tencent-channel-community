#!/usr/bin/env python3
"""获取频道的加入设置（验证方式、验证问题等）。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, ok, parse_positive_int, read_input  # noqa: E402


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    result = call_mcp("get_join_guild_setting", {"guild_id": guild_id})
    data = decode_bytes_fields(result.get("structuredContent", result))
    ok(data)


if __name__ == "__main__":
    main()
