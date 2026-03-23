#!/usr/bin/env python3
"""获取频道资料。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, fetch_guild_share_url, ok, parse_positive_int, read_input  # noqa: E402


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    result = call_mcp(
        "get_guild_info",
        {
            "filter": {
                "info": {
                    "uint32_create_time": 1,
                    "uint32_member_num": 1,
                    "uint32_guild_name": 1,
                    "uint32_profile": 1,
                    "uint32_face_seq": 1,
                    "uint32_guild_number": 1,
                }
            },
            "req_guild_infos": [{"guild_id": guild_id}],
        },
    )
    data = decode_bytes_fields(result.get("structuredContent", result))
    _inject_avatar_url(data, guild_id)
    share_url = fetch_guild_share_url(guild_id)
    if share_url:
        data["share_url"] = share_url
    ok(data)


def _inject_avatar_url(data, guild_id: str):
    """将 faceSeq 转为完整头像 URL，并移除原始序号字段。"""
    if not isinstance(data, dict):
        return
    for info in data.get("guildInfos", data.get("guild_infos", [data])):
        if not isinstance(info, dict):
            continue
        inner = info.get("guildInfo", info.get("guild_info", info))
        if not isinstance(inner, dict):
            continue
        seq = inner.pop("faceSeq", inner.pop("face_seq", None))
        if seq:
            inner["avatarUrl"] = (
                f"https://groupprohead-76292.picgzc.qpic.cn/{guild_id}/100?t={seq}"
            )


if __name__ == "__main__":
    main()
