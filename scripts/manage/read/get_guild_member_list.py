#!/usr/bin/env python3
"""获取频道成员列表，支持分页。

AI 通过 get_num（提示每页大小，最大50）和 next_page_token 翻页。
底层游标由脚本编解码，AI 只需原样传回 next_page_token 即可翻到下一页。
每次调用直接透传至远端 MCP 接口，返回接口原生分页结果。
"""

import base64
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, call_mcp_ex, decode_bytes_fields, fail, humanize_timestamps, ok, optional_str, parse_positive_int, read_input  # noqa: E402

PAGE_SIZE_MAX = 50
PAGE_SIZE_DEFAULT = 20
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
    "levelRoleId", "level_role_id",
    "isInReqRoleId", "is_in_req_role_id",
    "uint32AvatarFlag", "uint32_avatar_flag",
    "uint32IsInBlacklist", "uint32_is_in_blacklist",
    "uint32IsInPrivateChannel", "uint32_is_in_private_channel",
    "uint32MemberNameFlag", "uint32_member_name_flag",
    "uint64Uin", "uint64_uin",
}

# MemberRole 枚举 → 可读角色名
# ROLE_NORMAL=0（默认值，接口可能省略该字段）、ROLE_ADMIN=1、ROLE_OWNER=2
_ROLE_MAP = {
    "ROLE_NORMAL": "成员",
    "ROLE_NORMAL_MEMBER": "成员",
    "ROLE_ADMIN": "管理员",
    "ROLE_OWNER": "频道主",
    "0": "成员",
    "1": "管理员",
    "2": "频道主",
}

# 用于从响应列表字段名推断角色的兜底映射
_LIST_ROLE_FALLBACK = {
    "rptMsgOwnerList": "频道主",
    "rpt_msg_owner_list": "频道主",
    "rptMsgAdminList": "管理员",
    "rpt_msg_admin_list": "管理员",
    "rptMsgNormalMemberList": "成员",
    "rpt_msg_normal_member_list": "成员",
}

# 响应中包含成员的列表字段（按 频道主→管理员→成员 顺序）
_MEMBER_LIST_KEYS = [
    ("rptMsgOwnerList", "rpt_msg_owner_list"),
    ("rptMsgAdminList", "rpt_msg_admin_list"),
    ("rptMsgNormalMemberList", "rpt_msg_normal_member_list"),
]


def _resolve_role(member: dict, list_key_fallback: str) -> str:
    """从成员的 uint32Role 字段解析可读角色名；无法识别时用列表字段名兜底。"""
    raw_role = member.get("uint32Role", member.get("uint32_role", ""))
    if raw_role and str(raw_role) in _ROLE_MAP:
        return _ROLE_MAP[str(raw_role)]
    return _LIST_ROLE_FALLBACK.get(list_key_fallback, "成员")


def _clean_member(m: dict) -> dict:
    """移除会误导 AI 的内部字段。"""
    return {k: v for k, v in m.items() if k not in _STRIP_FIELDS}


def _collect_members(data: dict) -> list:
    """从 MCP 响应中提取所有成员，基于 uint32Role 标注可读角色。

    覆盖两种响应格式：
    - rptMsgOwnerList / rptMsgAdminList / rptMsgNormalMemberList（GET_ALL）
    - rptMsgAllMemberList（GET_ROBOT）
    """
    result = []
    # 1. 标准三列表（GET_ALL）
    for camel_key, snake_key in _MEMBER_LIST_KEYS:
        members = data.get(camel_key, data.get(snake_key, []))
        if not isinstance(members, list):
            continue
        fallback_key = camel_key if camel_key in data else snake_key
        for m in members:
            cleaned = _clean_member(m)
            cleaned["role"] = _resolve_role(m, fallback_key)
            result.append(cleaned)

    # 2. rptMsgAllMemberList（GET_ROBOT）
    for m in data.get("rptMsgAllMemberList", data.get("rpt_msg_all_member_list", [])):
        cleaned = _clean_member(m)
        cleaned["role"] = _resolve_role(m, "")
        result.append(cleaned)

    return result


def _collect_role_members(data: dict) -> list:
    """从 roleMemberList 响应中提取成员（带 roleIdIndex 时的响应格式）。"""
    result = []
    for group in data.get("roleMemberList", data.get("role_member_list", [])):
        if not isinstance(group, dict):
            continue
        members = group.get("rptMemberList", group.get("rpt_member_list", []))
        if not isinstance(members, list):
            continue
        for m in members:
            cleaned = _clean_member(m)
            cleaned["role"] = _resolve_role(m, "")
            result.append(cleaned)
    return result


def _fetch_role_members_page(guild_id: str, role_pag: dict | None = None) -> tuple[list, dict]:
    """补充拉取 roleMemberList 中的成员（如 AI 成员），单次单页。

    GET_ALL 标准模式不返回 AI 成员等仅存在于角色分组中的成员，
    需要额外带 role_id_index 请求来获取。失败时静默返回空列表。

    返回 (members, next_role_pag)，next_role_pag 为空 dict 表示已拉完。
    """
    try:
        args = {
            "uint64_guild_id": guild_id,
            "uint32_get_type": "GET_ALL",
            "uint32_get_num": PAGE_SIZE_MAX,
            "role_id_index": "2",
            "msg_member_info_filter": _MEMBER_INFO_FILTER,
        }
        if role_pag:
            if role_pag.get("start_index"):
                args["uint64_start_index"] = role_pag["start_index"]
            if role_pag.get("trans_buf"):
                args["bytes_trans_buf"] = role_pag["trans_buf"]

        raw = call_mcp_ex("get_guild_member_list", args)
        raw_content = raw.get("structuredContent", raw)
        next_pag = _extract_pagination(raw_content)
        decoded = decode_bytes_fields(raw_content)
        members = _collect_role_members(decoded)

        # 防死循环：游标必须前进
        if next_pag and role_pag:
            try:
                if int(next_pag.get("start_index", 0)) <= int(role_pag.get("start_index", 0)):
                    next_pag = {}
            except (TypeError, ValueError):
                pass

        return members, next_pag
    except Exception:
        return [], {}


def _extract_pagination(raw_data: dict) -> dict:
    """从 **未 decode** 的 MCP 原始响应中提取翻页游标。

    trans_buf 需要保留原始 base64 形式，否则回传时后端无法解析。
    注意：仅有 trans_buf 而无 start_index 时视为到底（API 会从头返回导致死循环）。
    """
    pag = {}
    for key in ("uint64NextIndex", "uint64_next_index", "nextIndex", "next_index"):
        val = raw_data.get(key)
        # 0 / "0" / None / "" 都表示没有下一页
        if val and str(val) != "0":
            pag["start_index"] = str(val)
            break
    # 没有 start_index 说明已到最后一页，直接返回空 dict
    if "start_index" not in pag:
        return {}
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
    """按 tinyid 去重，保持顺序。无 tinyid 时用全部字段拼接做兜底去重。"""
    seen = set()
    result = []
    for m in members:
        tid = m.get("uint64Tinyid", m.get("uint64_tinyid", ""))
        dedup_key = str(tid) if tid else "|".join(f"{k}={v}" for k, v in sorted(m.items()))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        result.append(m)
    return result


def _encode_page_token(pag: dict) -> str:
    """将底层翻页游标编码为对 AI 不透明的 token。"""
    return base64.urlsafe_b64encode(json.dumps(pag, separators=(",", ":")).encode()).decode()


def _decode_page_token(token: str) -> dict:
    """将 AI 传回的 token 解码为底层翻页游标。"""
    try:
        return json.loads(base64.urlsafe_b64decode(token))
    except Exception:
        fail("next_page_token 无效，请使用上一次返回的 next_page_token 原样传入")


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))
    get_type = optional_str(params, "get_type", "GET_ALL") or "GET_ALL"
    if get_type not in ("GET_ALL", "GET_ROBOT"):
        fail("get_type 仅支持 GET_ALL（默认）和 GET_ROBOT（查机器人）")
    sort_type = optional_str(params, "sort_type", "ROLE_AND_JOIN_TIME") or "ROLE_AND_JOIN_TIME"

    page_size = min(int(params.get("get_num", PAGE_SIZE_DEFAULT)), PAGE_SIZE_MAX)
    if page_size <= 0:
        fail("参数 get_num 必须大于 0")

    # 解析翻页 token（不传 = 第一页）
    token = optional_str(params, "next_page_token", "")
    pag = _decode_page_token(token) if token else None

    # 从 token 中分离 role 成员翻页状态
    # role_pag: None → 已拉完/不需要, {} → 首次拉取, {start_index:...} → 继续拉取
    # main_done: True → 主列表已拉完，仅继续拉 role 成员
    if pag is not None:
        role_pag = pag.pop("role_pag", None)
        main_done = pag.pop("main_done", False)
    else:
        role_pag = {}  # 首页：需要开始拉取 role 成员
        main_done = False

    # 拉取主成员列表（单页）
    all_members = []
    next_pag = {}
    if not main_done:
        data = _fetch_one_page(guild_id, get_type, sort_type, page_size, pag if pag else None)
        next_pag = data.pop("_pagination_raw", {})
        all_members = _collect_members(data)

    # GET_ALL：补充拉取 roleMemberList（单页），role_pag 非 None 表示仍需拉取
    next_role_pag = None
    if get_type == "GET_ALL" and role_pag is not None:
        role_members, next_role_pag = _fetch_role_members_page(
            guild_id, role_pag if role_pag else None,
        )
        all_members.extend(role_members)
        if not next_role_pag:
            next_role_pag = None  # 空 dict → None，表示拉完

    all_members = _dedup_members(all_members)

    # 防御：主游标必须前进，否则视为到底（防止外循环死循环）
    if next_pag and pag:
        try:
            if int(next_pag.get("start_index", 0)) <= int(pag.get("start_index", 0)):
                next_pag = {}
        except (TypeError, ValueError):
            pass

    # 按角色拆分
    owners = [m for m in all_members if m.get("role") == "频道主"]
    admins = [m for m in all_members if m.get("role") == "管理员"]
    normals = [m for m in all_members if m.get("role") not in ("频道主", "管理员")]

    output = {
        "owners": owners,
        "admins": admins,
        "members": normals,
        "total_fetched": len(all_members),
        "total_fetched_note": "本页返回的成员数,非频道总人数。频道总人数请使用 get_guild_info 获取",
    }

    has_more_main = bool(next_pag)
    has_more_role = next_role_pag is not None

    if has_more_main or has_more_role:
        token_data = dict(next_pag) if next_pag else {}
        if not has_more_main:
            token_data["main_done"] = True
        if has_more_role:
            token_data["role_pag"] = next_role_pag
        output["next_page_token"] = _encode_page_token(token_data)
        output["next_page_token_hint"] = "下一页请传入 next_page_token 参数，值为上面的 next_page_token 原样传回"
        output["has_more"] = True
    else:
        output["has_more"] = False

    ok(humanize_timestamps(output))


if __name__ == "__main__":
    main()
