#!/usr/bin/env python3
"""获取频道成员列表，支持自动多页拉取。

当单页返回不足 get_num 且仍有翻页游标时，脚本自动循环翻页直到拿满或拉完，
AI 无需手动处理 trans_buf 等翻页参数。
"""

import base64
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, fail, ok, optional_str, parse_positive_int, read_input  # noqa: E402

MAX_AUTO_PAGES = 50
_MEMBER_INFO_FILTER = {
    "uint32_need_member_name": 1,
    "uint32_need_nick_name": 1,
    "uint32_need_join_time": 1,
    "uint32_need_role": 1,
    "uint32_need_type": 1,
    "uint32_need_gender": 1,
    "uint32_need_shutup_expire_time": 1,
    "uint32_need_location": 1,
}


_STRIP_FIELDS = {
    "uint32Role", "levelRoleId", "level_role_id",
    "isInReqRoleId", "is_in_req_role_id",
    "uint32AvatarFlag", "uint32_avatar_flag",
    "uint32IsInBlacklist", "uint32_is_in_blacklist",
    "uint32IsInPrivateChannel", "uint32_is_in_private_channel",
    "uint32MemberNameFlag", "uint32_member_name_flag",
}


def _clean_member(m: dict, role: str) -> dict:
    """移除会误导 AI 的内部字段，补上可读的 role 标签。"""
    out = {k: v for k, v in m.items() if k not in _STRIP_FIELDS}
    out["role"] = role
    return out


def _collect_members(data: dict) -> list:
    """从 MCP 响应中提取管理员 + 普通成员，按来源标注角色后合并。"""
    admins = data.get("rptMsgAdminList", data.get("rpt_msg_admin_list", []))
    normals = data.get("rptMsgNormalMemberList", data.get("rpt_msg_normal_member_list", []))
    if not isinstance(admins, list):
        admins = []
    if not isinstance(normals, list):
        normals = []
    result = [_clean_member(m, "管理员") for m in admins]
    result += [_clean_member(m, "成员") for m in normals]
    return result


def _extract_pagination(raw_data: dict) -> dict:
    """从 **未 decode** 的 MCP 原始响应中提取翻页游标。

    trans_buf 需要保留原始 base64 形式，否则回传时后端无法解析。
    """
    pag = {}
    for key in ("uint64NextIndex", "uint64_next_index", "nextIndex", "next_index"):
        val = raw_data.get(key)
        if val:
            pag["start_index"] = str(val)
            break
    for key in ("bytesTransBuf", "bytes_trans_buf"):
        val = raw_data.get(key)
        if val:
            raw = str(val)
            try:
                base64.b64decode(raw)
                pag["trans_buf"] = raw
            except Exception:
                pag["trans_buf"] = base64.b64encode(raw.encode()).decode()
            break
    return pag


def _fetch_one_page(guild_id, get_type, sort_type, page_size, pag=None):
    args = {
        "uint64_guild_id": guild_id,
        "uint32_get_type": get_type,
        "uint32_sort_type": sort_type,
        "uint32_get_num": page_size,
    }
    if pag:
        if pag.get("start_index"):
            args["uint64_start_index"] = pag["start_index"]
        if pag.get("trans_buf"):
            args["bytes_trans_buf"] = pag["trans_buf"]

    raw = call_mcp("get_guild_member_list", args)
    raw_content = raw.get("structuredContent", raw)
    pag_info = _extract_pagination(raw_content)
    decoded = decode_bytes_fields(raw_content)
    decoded["_pagination_raw"] = pag_info
    return decoded


def _dedup_members(members: list) -> list:
    """按 tinyid 去重，保持顺序。"""
    seen = set()
    result = []
    for m in members:
        tid = m.get("uint64Tinyid", m.get("uint64_tinyid", ""))
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
        result.append(m)
    return result


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    get_type = optional_str(params, "get_type", "GET_ALL") or "GET_ALL"
    sort_type = optional_str(params, "sort_type", "ROLE_AND_JOIN_TIME") or "ROLE_AND_JOIN_TIME"
    want = int(params.get("get_num", 20))
    if want <= 0:
        fail("参数 get_num 必须大于 0")

    initial_pag = {}
    start_index = optional_str(params, "start_index")
    if start_index:
        initial_pag["start_index"] = start_index
    trans_buf = optional_str(params, "trans_buf")
    if trans_buf:
        initial_pag["trans_buf"] = trans_buf

    all_members = []
    pag = initial_pag or None
    pages = 0
    last_data = {}

    while len(all_members) < want and pages < MAX_AUTO_PAGES:
        remaining = want - len(all_members)
        data = _fetch_one_page(guild_id, get_type, sort_type, remaining, pag)
        last_data = data
        pages += 1

        members = _collect_members(data)
        if not members:
            break
        all_members.extend(members)

        next_pag = data.pop("_pagination_raw", {})
        if not next_pag:
            break
        pag = next_pag

    all_members = _dedup_members(all_members)[:want]

    output = {
        "members": all_members,
        "total_fetched": len(all_members),
        "total_fetched_note": "本次拉取的成员数,非频道总人数。频道总人数请使用 get_guild_info 获取",
        "pages_used": pages,
    }

    final_pag = last_data.pop("_pagination_raw", {})
    if final_pag and len(all_members) >= want:
        final_pag["has_more"] = True
        final_pag["hint"] = "传入 start_index / trans_buf 可继续拉取下一页"
        output["_pagination"] = final_pag

    ok(output)


if __name__ == "__main__":
    main()
