#!/usr/bin/env python3
"""获取我加入的频道列表。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, fetch_guild_share_url, ok, read_input  # noqa: E402

_MAX_AUTO_SHARE = 10


def _extract_guilds(data: dict) -> list:
    """从返回数据中提取频道列表。

    API 实际返回结构为 msgRspSortGuilds.rptMsgGuildInfos，需先进入外层。
    """
    for outer_key in ("msgRspSortGuilds", "msg_rsp_sort_guilds"):
        outer = data.get(outer_key)
        if isinstance(outer, list):
            return outer
        if isinstance(outer, dict):
            data = outer
            break
    for key in ("rptMsgGuildInfos", "rpt_msg_guild_infos", "guildInfos", "guild_infos"):
        items = data.get(key)
        if isinstance(items, list):
            return items
    return []


def main():
    read_input()
    result = call_mcp(
        "get_my_join_guild_info",
        {
            "filter": {
                "filter": {
                    "uint32_create_time": 1,
                    "uint32_member_num": 1,
                    "uint32_guild_name": 1,
                    "uint32_profile": 1,
                    "uint32_face_seq": 1,
                    "uint32_guild_number": 1,
                }
            },
            "bytes_cookie": "",
        },
    )
    data = decode_bytes_fields(result.get("structuredContent", result))

    guilds = _extract_guilds(data) if isinstance(data, dict) else []
    if guilds:
        for g in guilds[:_MAX_AUTO_SHARE]:
            inner = g
            for k in ("msgGuildInfo", "msg_guild_info", "guildInfo", "guild_info"):
                if isinstance(g.get(k), dict):
                    inner = g[k]
                    break
            gid = str(
                g.get("uint64GuildId")
                or g.get("uint64_guild_id")
                or inner.get("uint64GuildId")
                or inner.get("uint64_guild_id")
                or ""
            )
            if gid:
                url = fetch_guild_share_url(gid)
                if url:
                    inner["share_url"] = url

    ok(data)


if __name__ == "__main__":
    main()
