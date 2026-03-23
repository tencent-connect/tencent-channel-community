#!/usr/bin/env python3
"""修改频道头像。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import b64encode_file, call_mcp, fail, fetch_guild_share_url, ok, parse_positive_int, read_input  # noqa: E402


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    image_path = str(params.get("image_path", "")).strip()
    if not image_path:
        fail("参数 image_path 不能为空")
    result = call_mcp("upload_guild_avatar", {"guild_id": guild_id, "img": b64encode_file(image_path)})
    data = result.get("structuredContent", result)
    if not isinstance(data, dict):
        data = {}
    share_url = fetch_guild_share_url(guild_id)
    if share_url:
        data["share_url"] = share_url
    ok(data)


if __name__ == "__main__":
    main()
