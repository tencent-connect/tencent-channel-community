#!/usr/bin/env python3
"""获取我加入的频道列表，并按角色分为三类：我创建的、我管理的、我加入的。

接口通过 filter.userFilter.uint32Role=1 请求返回角色信息，
角色值位于 guildUserInfo.uint32Role：0=普通成员，1=管理员，2=频道主。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import (  # noqa: E402
    call_mcp,
    decode_bytes_fields,
    fetch_guild_share_url,
    humanize_timestamps,
    ok,
    read_input,
)

_MAX_AUTO_SHARE = 10

# guildUserInfo.uint32Role 值 → 角色标签（中文）
_ROLE_VALUE_MAP = {
    2: "频道主",
    1: "管理员",
    0: "成员",
}


def _extract_guilds(data: dict) -> list:
    """从返回数据中提取频道列表。"""
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


def _get_guild_id(guild: dict) -> str:
    """从频道对象中提取 guild_id。"""
    inner = guild
    for k in ("msgGuildInfo", "msg_guild_info", "guildInfo", "guild_info"):
        if isinstance(guild.get(k), dict):
            inner = guild[k]
            break
    return str(
        guild.get("uint64GuildId")
        or guild.get("uint64_guild_id")
        or inner.get("uint64GuildId")
        or inner.get("uint64_guild_id")
        or ""
    )


def _get_inner(guild: dict) -> dict:
    """获取频道对象内层信息字典（msgGuildInfo）。"""
    for k in ("msgGuildInfo", "msg_guild_info", "guildInfo", "guild_info"):
        if isinstance(guild.get(k), dict):
            return guild[k]
    return guild


def _get_role(guild: dict) -> str:
    """从 guildUserInfo.uint32Role 中读取角色。

    返回 "频道主" / "管理员" / "成员"。
    """
    user_info = guild.get("guildUserInfo") or guild.get("guild_user_info") or {}
    if isinstance(user_info, dict):
        role_val = user_info.get("uint32Role", user_info.get("uint32_role"))
        if role_val is not None:
            return _ROLE_VALUE_MAP.get(int(role_val), "成员")
    return "成员"


def _classify_guilds(guilds: list) -> dict:
    """将频道列表按角色分为三类。"""
    created = []  # 频道主
    managed = []  # 管理员
    joined = []   # 成员

    for g in guilds:
        role = _get_role(g)
        _get_inner(g)["role"] = role
        if role == "频道主":
            created.append(g)
        elif role == "管理员":
            managed.append(g)
        else:
            joined.append(g)

    return {"created_guilds": created, "managed_guilds": managed, "joined_guilds": joined}


def main():
    read_input()
    result = call_mcp(
        "get_my_join_guild_info",
        {
            "filter": {
                "filter": {
                    "uint32CreateTime": 1,
                    "uint32MemberNum": 1,
                    "uint32GuildName": 1,
                    "uint32Profile": 1,
                    "uint32FaceSeq": 1,
                    "uint32GuildNumber": 1,
                },
                "userFilter": {
                    "uint32Role": 1,
                },
            },
            "bytesCookie": "",
        },
    )
    data = decode_bytes_fields(result.get("structuredContent", result))

    guilds = _extract_guilds(data) if isinstance(data, dict) else []

    # 为前 N 个频道补取分享短链
    if guilds:
        for g in guilds[:_MAX_AUTO_SHARE]:
            gid = _get_guild_id(g)
            if gid:
                url = fetch_guild_share_url(gid)
                if url:
                    _get_inner(g)["share_url"] = url

    # 按角色分类
    classified = _classify_guilds(guilds)

    output = {
        "created_guilds": classified["created_guilds"],
        "created_guilds_count": len(classified["created_guilds"]),
        "managed_guilds": classified["managed_guilds"],
        "managed_guilds_count": len(classified["managed_guilds"]),
        "joined_guilds": classified["joined_guilds"],
        "joined_guilds_count": len(classified["joined_guilds"]),
        "total_count": len(guilds),
    }

    ok(humanize_timestamps(output))


if __name__ == "__main__":
    main()
