#!/usr/bin/env python3
"""创建带头像、名称和简介的主题频道。"""

import json
import os
import sys
from pathlib import Path

_MANAGE_DIR = str(Path(__file__).resolve().parent.parent)
if _MANAGE_DIR not in sys.path:
    sys.path.insert(0, _MANAGE_DIR)
from common import (  # noqa: E402
    b64encode_file,
    b64encode_text,
    call_mcp,
    check_sec_rets,
    fail,
    fetch_guild_share_url,
    ok,
    optional_str,
    read_input,
    require_str,
    validate_guild_name,
    validate_guild_profile,
)


def resolve_community_type(params: dict) -> tuple[int, str]:
    value = params.get("community_type")
    if value is None or (isinstance(value, str) and not str(value).strip()):
        value = params.get("visibility")
    if value is None or (isinstance(value, str) and not str(value).strip()):
        value = "public"
    if isinstance(value, bool):
        fail("参数 community_type/visibility 必须是公开或私密")

    text = str(value).strip().lower()
    mapping = {
        "1": (1, "public"),
        "2": (2, "private"),
        "public": (1, "public"),
        "private": (2, "private"),
        "公开": (1, "public"),
        "私密": (2, "private"),
    }
    if text not in mapping:
        fail("参数 community_type/visibility 只支持 public/private/公开/私密/1/2")
    return mapping[text]


def stable_index(text: str, size: int) -> int:
    return sum(ord(ch) for ch in text) % size


def shorten_name(text: str, limit: int = 15) -> str:
    return text if len(text) <= limit else text[:limit]


def generate_guild_name(theme: str) -> str:
    suffixes = ["同好会", "研究所", "俱乐部", "小宇宙", "实验室", "星球"]
    theme = theme.strip()
    if len(theme) <= 8:
        return shorten_name(f"{theme}{suffixes[stable_index(theme, len(suffixes))]}")
    return shorten_name(theme)


def generate_guild_profile(theme: str, community_type_name: str) -> str:
    channel_label = "公开频道" if community_type_name == "public" else "私密频道"
    templates = [
        "一个围绕{theme}展开交流、分享与结识同好的{channel_label}。",
        "欢迎来到{theme}主题{channel_label}，这里适合讨论、记录和分享灵感。",
        "专注于{theme}的{channel_label}，适合同好聊天、沉淀经验与发起活动。",
        "以{theme}为核心的{channel_label}，欢迎一起交流见解、分享内容和认识新朋友。",
    ]
    return templates[stable_index(theme, len(templates))].format(
        theme=theme.strip(), channel_label=channel_label
    )


def resolve_guild_profile(params: dict, community_type_name: str) -> tuple[str, str, str]:
    guild_name = optional_str(params, "guild_name")
    guild_profile = optional_str(params, "guild_profile")
    theme = optional_str(params, "theme")

    if guild_name and guild_profile:
        return guild_name, guild_profile, theme

    if not theme:
        fail("参数 theme 不能为空；若不提供 theme，则必须同时提供 guild_name 和 guild_profile")

    if not guild_name:
        guild_name = generate_guild_name(theme)
    if not guild_profile:
        guild_profile = generate_guild_profile(theme, community_type_name)
    return guild_name, guild_profile, theme


def try_fetch_guild_share(guild_id: str) -> dict:
    url = fetch_guild_share_url(guild_id)
    if url:
        return {"url": url, "shareInfo": "", "retCode": 0}
    return {"shareWarning": "频道已创建成功，但分享链接解析为空"}


def extract_seq(rpc_result: dict) -> str:
    structured = rpc_result.get("structuredContent", {})
    if isinstance(structured, dict):
        seq = structured.get("seq")
        if isinstance(seq, (str, int)) and str(seq).strip():
            return str(seq)

    content = rpc_result.get("content", [])
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and "\"seq\"" in text:
                try:
                    parsed = json.loads(text.split(": ", 1)[-1])
                except Exception:
                    continue
                seq = parsed.get("seq") if isinstance(parsed, dict) else None
                if isinstance(seq, (str, int)) and str(seq).strip():
                    return str(seq)

    fail(f"未从预上传结果中解析到 seq: {json.dumps(rpc_result, ensure_ascii=False)}", code=200)


def extract_guild_id(rpc_result: dict) -> str:
    structured = rpc_result.get("structuredContent", {})
    if isinstance(structured, dict):
        guild_id = structured.get("guildId")
        if isinstance(guild_id, (str, int)) and str(guild_id).strip():
            return str(guild_id)

    content = rpc_result.get("content", [])
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and "\"guildId\"" in text:
                try:
                    parsed = json.loads(text.split(": ", 1)[-1])
                except Exception:
                    continue
                guild_id = parsed.get("guildId") if isinstance(parsed, dict) else None
                if isinstance(guild_id, (str, int)) and str(guild_id).strip():
                    return str(guild_id)

    meta = rpc_result.get("_meta", {})
    additional = meta.get("AdditionalFields", {}) if isinstance(meta, dict) else {}
    ret_code = additional.get("retCode")
    structured = rpc_result.get("structuredContent")
    hint = ""
    if ret_code in (None, 0) and (not isinstance(structured, dict) or not structured):
        hint = (
            " 可能原因：内容安全/频控导致未下发频道ID，或接口返回体为空；"
            "若错误信息中含 secRets 请以安全字段为准；也可稍后重试。"
        )
    fail(
        f"创建频道未拿到 guildId:{hint} 原始响应: {json.dumps(rpc_result, ensure_ascii=False)}",
        code=200,
    )


def main():
    params = read_input()
    image_path = require_str(params, "image_path")
    create_src = str(params.get("create_src", "pd-mcp")).strip() or "pd-mcp"
    community_type_value, community_type_name = resolve_community_type(params)
    guild_name, guild_profile, theme = resolve_guild_profile(params, community_type_name)

    validate_guild_name(guild_name, community_type_name == "public")
    validate_guild_profile(guild_profile)

    guild_name_base64 = b64encode_text(guild_name)
    guild_profile_base64 = b64encode_text(guild_profile)
    image_base64 = b64encode_file(os.path.abspath(image_path))

    pre_upload_result = call_mcp("upload_guild_avatar_pre", {"img": image_base64})
    avatar_seq = extract_seq(pre_upload_result)

    create_result = call_mcp(
        "create_guild",
        {
            "guild_name": guild_name_base64,
            "source": {"create_src": create_src},
            "guild_profile": guild_profile_base64,
            "uint32_guild_community_type": community_type_value,
            "avatar_seq": avatar_seq,
        },
    )
    check_sec_rets(create_result)
    guild_id = extract_guild_id(create_result)
    share_result = try_fetch_guild_share(guild_id)

    response = {
        "guildId": guild_id,
        "avatarSeq": avatar_seq,
        "theme": theme,
        "resolvedCommunityType": community_type_name,
        "resolvedCommunityTypeValue": community_type_value,
        "resolvedGuildName": guild_name,
        "resolvedGuildProfile": guild_profile,
        "raw": create_result,
    }
    if isinstance(share_result, dict):
        response["share"] = share_result

    ok(response)


if __name__ == "__main__":
    main()
