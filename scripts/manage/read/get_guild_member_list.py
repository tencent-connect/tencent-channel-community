#!/usr/bin/env python3
"""获取频道成员列表，支持分页。

采用与客户端一致的拉取方式: GET_ALL + role_id_index，单次请求同时返回:
- roleMemberList:        按身份组分组的成员（含 AI 成员）
- rptMsgRobotList:       系统机器人
- rptMsgNormalMemberList: 无身份组的普通成员

内部实现:
- 每次调用至少凑满 MIN_OUTPUT_SIZE 条去重成员后才返回（不足时自动续拉）
- 同一成员可隶属多个身份组，按 tinyid 增量去重，跨页可能仍有少量重复
- 空身份组自动跳过
- 翻页游标封装为不透明的 next_page_token
"""

import base64
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, decode_bytes_fields, fail, humanize_timestamps, ok, optional_str, parse_positive_int, read_input  # noqa: E402

PAGE_SIZE_MAX = 50
MIN_OUTPUT_SIZE = 50  # 每次调用至少返回的去重成员数
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

# 从输出中移除的内部字段
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
_ROLE_MAP = {
    "ROLE_NORMAL": "成员",
    "ROLE_NORMAL_MEMBER": "成员",
    "ROLE_ADMIN": "管理员",
    "ROLE_OWNER": "频道主",
    "0": "成员",
    "1": "管理员",
    "2": "频道主",
}


def _resolve_role(member: dict) -> str:
    """从成员的 uint32Role 字段解析可读角色名。"""
    raw_role = member.get("uint32Role", member.get("uint32_role", ""))
    if raw_role and str(raw_role) in _ROLE_MAP:
        return _ROLE_MAP[str(raw_role)]
    return "成员"


def _clean_member(m: dict) -> dict:
    """移除内部字段。"""
    return {k: v for k, v in m.items() if k not in _STRIP_FIELDS}


def _is_system_robot(m: dict) -> bool:
    """系统机器人: uint32Type=1。"""
    t = m.get("uint32Type", m.get("uint32_type"))
    return t is not None and str(t) == "1"


def _is_ai_member(m: dict) -> bool:
    """AI 成员: isAi=true 或 uint32Type=2。"""
    if m.get("isAi") or m.get("is_ai"):
        return True
    t = m.get("uint32Type", m.get("uint32_type"))
    return t is not None and str(t) == "2"


_GENDER_MAP = {"1": "男", "2": "女"}


def _format_member(m: dict) -> dict:
    """将内部成员字典转为固定的对外输出格式。"""
    out = {}
    name = m.get("bytesMemberName", m.get("bytes_member_name", ""))
    if name:
        out["昵称"] = name
    gender = str(m.get("uint32Gender", m.get("uint32_gender", "")))
    if gender in _GENDER_MAP:
        out["性别"] = _GENDER_MAP[gender]
    join_human = m.get("uint64JoinTime_human", "")
    if join_human:
        out["加入时间"] = join_human
    tid = m.get("uint64Tinyid", m.get("uint64_tinyid", ""))
    if tid:
        out["tinyid"] = str(tid)
    if m.get("isAi") or m.get("is_ai"):
        out["is_ai"] = True
    return out


def _extract_pagination(raw_data: dict) -> dict:
    """从 **未 decode** 的 MCP 原始响应中提取翻页游标。

    role_id_index 模式下有两个独立的翻页轴：
    - uint64NextIndex + bytesTransBuf: 普通成员偏移量
    - nextRoleIdIndex (编码在 bytesTransBuf 内部): 身份组进度

    当普通成员翻完 (uint64NextIndex 为空) 但身份组未翻完
    (nextRoleIdIndex 不为 "1") 时，仍需继续翻页，
    只需传回 bytesTransBuf 即可，服务端据此恢复两个轴的状态。
    """
    pag = {}
    for key in ("uint64NextIndex", "uint64_next_index", "nextIndex", "next_index"):
        val = raw_data.get(key)
        if val and str(val) != "0":
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

    # 判断是否还有下一页
    has_more_members = "start_index" in pag
    has_more_roles = False
    for key in ("nextRoleIdIndex", "next_role_id_index"):
        val = raw_data.get(key)
        if val and str(val) not in ("", "0", "1"):
            has_more_roles = True
            break

    if not has_more_members and not has_more_roles:
        return {}
    # 只要还有更多（无论哪个轴），必须带 trans_buf
    if "trans_buf" not in pag:
        return {}
    return pag


def _collect_members(decoded: dict) -> list:
    """从 GET_ALL + role_id_index 响应中收集所有成员。

    三个来源:
    - roleMemberList:        按身份组分组（含 AI 成员，带 isAi / uint32Type 标记）
    - rptMsgRobotList:       系统机器人（uint32Type=1）
    - rptMsgNormalMemberList: 无身份组的普通成员
    """
    result = []

    # 1. roleMemberList — 按身份组分组
    for group in decoded.get("roleMemberList", decoded.get("role_member_list", [])):
        if not isinstance(group, dict):
            continue
        members = group.get("rptMemberList", group.get("rpt_member_list", []))
        if not isinstance(members, list):
            continue
        for m in members:
            cleaned = _clean_member(m)
            cleaned["role"] = _resolve_role(m)
            result.append(cleaned)

    # 2. rptMsgRobotList — 系统机器人
    for m in decoded.get("rptMsgRobotList", decoded.get("rpt_msg_robot_list", [])):
        if not isinstance(m, dict):
            continue
        cleaned = _clean_member(m)
        cleaned["role"] = _resolve_role(m)
        result.append(cleaned)

    # 3. rptMsgNormalMemberList — 无身份组的普通成员
    for m in decoded.get("rptMsgNormalMemberList", decoded.get("rpt_msg_normal_member_list", [])):
        if not isinstance(m, dict):
            continue
        cleaned = _clean_member(m)
        cleaned["role"] = _resolve_role(m)
        result.append(cleaned)

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

    # 解析翻页 token（不传 = 第一页）
    token = optional_str(params, "next_page_token", "")
    pag = _decode_page_token(token) if token else None

    # 循环拉取，直到去重后 >= MIN_OUTPUT_SIZE 或无更多数据。
    # 内部始终以 PAGE_SIZE_MAX 请求，最大化每次 MCP 调用的收益。
    # 跨页按 tinyid 增量去重，对调用方完全隐藏身份组遍历细节。
    all_members = []
    seen = set()
    next_pag = None
    _MAX_ROUNDS = 20  # 安全上限，防止极端情况死循环

    for _ in range(_MAX_ROUNDS):
        args = {
            "uint64_guild_id": guild_id,
            "uint32_get_type": "GET_ALL",
            "uint32_get_num": PAGE_SIZE_MAX,
            "role_id_index": "2",
            "msg_member_info_filter": _MEMBER_INFO_FILTER,
        }
        if pag:
            if pag.get("start_index"):
                args["uint64_start_index"] = pag["start_index"]
            if pag.get("trans_buf"):
                args["bytes_trans_buf"] = pag["trans_buf"]

        raw = call_mcp("get_guild_member_list", args)
        raw_content = raw.get("structuredContent", raw)

        # 提取翻页游标（必须在 decode_bytes_fields 之前，保留原始 base64）
        next_pag = _extract_pagination(raw_content)

        decoded = decode_bytes_fields(raw_content)

        # 从三个来源收集，增量去重
        for m in _collect_members(decoded):
            tid = m.get("uint64Tinyid", m.get("uint64_tinyid", ""))
            key = str(tid) if tid else "|".join(f"{k}={v}" for k, v in sorted(m.items()))
            if key not in seen:
                seen.add(key)
                all_members.append(m)

        # 防死循环: 游标必须前进（start_index 递增或 trans_buf 变化）
        if next_pag and pag:
            if next_pag.get("start_index") and pag.get("start_index"):
                try:
                    if int(next_pag["start_index"]) <= int(pag["start_index"]):
                        next_pag = {}
                except (TypeError, ValueError):
                    pass
            elif next_pag.get("trans_buf") and next_pag.get("trans_buf") == pag.get("trans_buf"):
                next_pag = {}  # trans_buf 未变化，说明没前进

        # 已够数量或已无更多数据 → 结束
        if len(all_members) >= MIN_OUTPUT_SIZE or not next_pag:
            break

        # 不足 MIN_OUTPUT_SIZE 且还有下一页 → 继续拉取
        pag = next_pag

    # 时间戳可读化（为 _format_member 准备 _human 字段）
    all_members = [humanize_timestamps(m) for m in all_members]

    # 分类优先级: 系统机器人 → 角色（频道主/管理员） → AI 成员 → 普通成员
    # 系统机器人（uint32Type=1）始终归入 robots，不随角色走
    # AI 成员若同时是管理员则归入 admins 并标记 is_ai
    owners = []
    admins = []
    ai_members = []
    robots = []
    normals = []

    for m in all_members:
        if _is_system_robot(m):
            robots.append(_format_member(m))
        elif m.get("role") == "频道主":
            owners.append(_format_member(m))
        elif m.get("role") == "管理员":
            admins.append(_format_member(m))
        elif _is_ai_member(m):
            ai_members.append(_format_member(m))
        else:
            normals.append(_format_member(m))

    output = {
        "owners": owners,
        "admins": admins,
        "ai_members": ai_members,
        "robots": robots,
        "members": normals,
        "total_fetched": len(all_members),
        "total_fetched_note": "本页返回的去重成员数,非频道总人数。频道总人数以频道资料的为准",
    }

    if next_pag:
        output["next_page_token"] = _encode_page_token(next_pag)
        output["next_page_token_hint"] = "下一页请传入 next_page_token 参数，值为上面的 next_page_token 原样传回"
        output["has_more"] = True
    else:
        output["has_more"] = False

    ok(output)


if __name__ == "__main__":
    main()
