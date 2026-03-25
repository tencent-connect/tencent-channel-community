#!/usr/bin/env python3
"""获取频道成员详细信息。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, ok, parse_positive_int, read_input  # noqa: E402


def main():
    params = read_input()
    guild_raw = str(params.get("guild_id", "")).strip()
    member_raw = str(params.get("member_tinyid", "")).strip()
    arguments = {
        "msg_filter": {
            "uint32_nick_name": 1,
            "uint32_gender": 1,
            "uint32_country": 1,
            "uint32_province": 1,
            "uint32_city": 1,
            "uint32_is_guild_author": 1,  # 频道创作者身份（有值=是创作者）
        },
    }

    # 规则（两参数独立）：
    # - 传 guild_id：在该频道上下文下取资料；不传：当前账号在频道体系下的全局资料。
    # - 不传 member_tinyid：查自己；传了：查指定成员。
    if guild_raw:
        arguments["guild_id"] = str(parse_positive_int(guild_raw, "参数 guild_id"))
    if member_raw:
        arguments["uint64_member_tinyid"] = str(
            parse_positive_int(member_raw, "参数 member_tinyid")
        )

    result = call_mcp(
        "get_user_info",
        arguments,
    )
    data = decode_bytes_fields(result.get("structuredContent", result))

    # 显式标注频道创作者身份（远端无值时 protobuf 省略该字段，这里补为 false）
    user_info = data.get("msgUserInfo")
    if isinstance(user_info, dict):
        user_info["isGuildAuthor"] = bool(user_info.get("isGuildAuthor"))

    ok(data)


if __name__ == "__main__":
    main()
