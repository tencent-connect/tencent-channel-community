#!/usr/bin/env python3
"""预览创建主题频道需要使用的编码结果与请求骨架。"""

import os
import sys
from pathlib import Path

_MANAGE_DIR = str(Path(__file__).resolve().parent.parent)
if _MANAGE_DIR not in sys.path:
    sys.path.insert(0, _MANAGE_DIR)
from common import b64encode_file, b64encode_text, fail, ok, optional_str, read_input, require_str  # noqa: E402


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


def encode_image_meta(image_path: str) -> tuple[str, int]:
    full_path = os.path.abspath(image_path)
    if not os.path.isfile(full_path):
        fail(f"图片不存在: {full_path}")
    size = os.path.getsize(full_path)
    encoded = b64encode_file(full_path)
    return encoded, size


def main():
    params = read_input()
    image_path = require_str(params, "image_path")
    create_src = str(params.get("create_src", "pd-mcp")).strip() or "pd-mcp"
    community_type_value, community_type_name = resolve_community_type(params)
    guild_name, guild_profile, theme = resolve_guild_profile(params, community_type_name)

    guild_name_base64 = b64encode_text(guild_name)
    guild_profile_base64 = b64encode_text(guild_profile)
    image_base64, image_size = encode_image_meta(image_path)

    preview = {
        "theme": theme,
        "resolvedCommunityType": community_type_name,
        "resolvedCommunityTypeValue": community_type_value,
        "resolvedGuildName": guild_name,
        "resolvedGuildProfile": guild_profile,
        "guildNameBase64": guild_name_base64,
        "guildProfileBase64": guild_profile_base64,
        "imageBase64Length": len(image_base64),
        "imageSizeBytes": image_size,
        "preUploadPayloadPreview": {
            "name": "upload_guild_avatar_pre",
            "arguments": {
                "img": f"{image_base64[:24]}...({len(image_base64)} chars)",
            },
        },
        "createPayloadPreview": {
            "name": "create_guild",
            "arguments": {
                "guildName": guild_name_base64,
                "source": {"createSrc": create_src},
                "guildProfile": guild_profile_base64,
                "uint32GuildCommunityType": community_type_value,
                "avatarSeq": "<from pre-upload response>",
            },
        },
    }
    ok(preview)


if __name__ == "__main__":
    main()
