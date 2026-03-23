#!/usr/bin/env python3
"""修改频道资料。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import b64encode_text, call_mcp, check_sec_rets, fail, fetch_guild_share_url, ok, optional_str, parse_positive_int, read_input, validate_guild_name, validate_guild_profile  # noqa: E402


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    guild_name = optional_str(params, "guild_name")
    guild_profile = optional_str(params, "guild_profile")

    if not guild_name and not guild_profile:
        fail("guild_name 和 guild_profile 至少需要提供一个")

    if guild_name:
        # get_guild_info 无社区类型字段，无法区分公开/私密；此处仅做长度等通用校验（公开频道「仅中英数」在创建时 enforced）
        validate_guild_name(guild_name)
    if guild_profile:
        validate_guild_profile(guild_profile)

    filter_block = {"uint32_guild_name": 1 if guild_name else 0, "uint32_profile": 1 if guild_profile else 0}
    guild_info = {}
    if guild_name:
        guild_info["name"] = b64encode_text(guild_name)
    if guild_profile:
        guild_info["profile"] = b64encode_text(guild_profile)

    result = call_mcp(
        "update_guild_info",
        {
            "uint64_guild_id": guild_id,
            "filter": {"filter": filter_block},
            "update_info": {"guild_info": guild_info},
        },
    )
    check_sec_rets(result)
    data = result.get("structuredContent", result)
    if not isinstance(data, dict):
        data = {}
    share_url = fetch_guild_share_url(guild_id)
    if share_url:
        data["share_url"] = share_url
    ok(data)


if __name__ == "__main__":
    main()
