"""
Skill: do_feed_prefer
描述: 给帖子点赞或取消点赞
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

action 枚举值（PreferAction）：
    1 = 点赞
    3 = 取消点赞

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

TOOL_NAME = "do_feed_prefer"

# action 枚举（PreferAction）
PREFER_ACTION_PREFER = 1         # 点赞
PREFER_ACTION_CANCEL_PREFER = 3  # 取消点赞

SKILL_MANIFEST = {
    "name": "do-feed-prefer",
    "description": (
        "给帖子点赞或取消点赞。"
        "action=1 点赞，3 取消点赞。"
        "成功后返回当前点赞总数。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "帖子ID，string，必填"
            },
            "action": {
                "type": "integer",
                "description": "操作类型：1=点赞，3=取消点赞，必填",
                "enum": [1, 3]
            },
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，建议填写"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串，建议填写"
            }
        },
        "required": ["feed_id", "action"]
    }
}


def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {"success": True, "data": {"prefer_count": ...}}
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    # 枚举值校验：防止非法值进入后续逻辑触发意外行为（V3-001）
    valid_actions = (PREFER_ACTION_PREFER, PREFER_ACTION_CANCEL_PREFER)
    if params["action"] not in valid_actions:
        return {"success": False, "error": f"action 值无效：{params['action']}，仅支持 1（点赞）/3（取消点赞）"}

    arguments = {
        "feed_id": params["feed_id"],
        "action":  params["action"],
    }
    for opt in ("guild_id", "channel_id"):
        if opt in params:
            arguments[opt] = str(params[opt])  # 大整数转 string 避免 JSON 精度丢失

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"帖子点赞失败（错误码 {ret_code}）：{ret_msg}"}
        action_label = "点赞" if params["action"] == PREFER_ACTION_PREFER else "取消点赞"
        result_data: dict = {
            "action": action_label,
        }
        prefer_count = structured.get("preferCount")
        if prefer_count is not None:
            result_data["prefer_count"] = prefer_count
        return {"success": True, "data": result_data}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)