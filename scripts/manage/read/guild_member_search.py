#!/usr/bin/env python3
"""频道内成员搜索，根据关键词搜索频道内成员昵称。

支持分页：首次请求不传 pos，翻页时传上一次返回的 next_pos。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import (  # noqa: E402
    call_mcp,
    fail,
    humanize_timestamps,
    ok,
    optional_str,
    parse_positive_int,
    read_input,
)

NUM_MAX = 50
NUM_DEFAULT = 20

# 不应暴露给用户的字段
_STRIP_FIELDS = {"uin", "avatarMeta", "nicknameType"}


def _clean_member(m: dict) -> dict:
    return {k: v for k, v in m.items() if k not in _STRIP_FIELDS}


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))

    keyword = optional_str(params, "keyword", "")
    if not keyword:
        fail("参数 keyword 不能为空")

    num = min(int(params.get("num", NUM_DEFAULT)), NUM_MAX)
    if num <= 0:
        fail("参数 num 必须大于 0")

    pos = optional_str(params, "pos", "0") or "0"

    result = call_mcp(
        "guild_member_search",
        {
            "guild_id": guild_id,
            "keyword": keyword,
            "num": num,
            "pos": pos,
            "source_id": "ALL_MEMBER_LIST",
            "fill_option": {"avatar": False},
        },
    )

    sc = result.get("structuredContent", result)
    members_raw = sc.get("rptMemberList", [])
    members = [_clean_member(m) for m in members_raw]
    member_num = sc.get("memberNum", len(members))
    next_pos = sc.get("nextPos", "0")

    output = {
        "members": humanize_timestamps(members),
        "match_count": member_num,
    }

    if next_pos and next_pos != "0" and len(members_raw) >= num:
        output["next_pos"] = next_pos
        output["has_more"] = True
    else:
        output["has_more"] = False

    ok(output)


if __name__ == "__main__":
    main()
