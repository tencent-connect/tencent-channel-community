"""
Skill: del_feed
描述: 删除指定帖子
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）

⚠️  调用前必读：references/feed-reference.md
    包含内容长度限制、拆分规则、正确调用流程等关键说明。
    禁止仅凭此脚本推断用法。
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp

TOOL_NAME = "del_feed"

SKILL_MANIFEST = {
    "name": "del-feed",
    "description": "删除腾讯频道（QQ Channel）指定帖子，需提供帖子ID、帖子发表时间、频道ID和版块ID。",
    "parameters": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "帖子ID，string，必填"
            },
            "create_time": {
                "type": "string",
                "description": "帖子发表时间（秒级时间戳），uint64 字符串，必填"
            },
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，必填"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串，必填"
            }
        },
        "required": ["feed_id", "create_time", "guild_id", "channel_id"]
    }
}


def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {"success": True, "data": {}}
        或 {"success": False, "error": "..."}

    底层透传说明（对齐底层 StDelFeedReq）：
      feed=2（StFeed）嵌套结构，字段序号严格对齐：
        id=1, poster=4, create_time=7, channel_info=21
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    guild_id    = params["guild_id"]
    channel_id  = params["channel_id"]
    feed_id     = params["feed_id"]
    create_time = params["create_time"]

    # feed=2（DelFeedItem/StFeed）：对齐底层 StDelFeedReq.feed=2
    arguments = {
        "feed": {
            "id":          feed_id,             # StFeed.id=1
            "poster": {                          # StFeed.poster=4
                "id": "",
            },
            "create_time": str(create_time),     # StFeed.createTime=7
            "channel_info": {                    # StFeed.channelInfo=21
                "sign": {
                    "guild_id":   str(guild_id),     # StChannelSign.guild_id=1
                    "channel_id": str(channel_id),   # StChannelSign.channel_id=2
                }
            },
        }
    }

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"删帖失败（错误码 {ret_code}）：{ret_msg}"}
        return {"success": True, "data": {"deleted": True, "message": "帖子删除成功"}}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)