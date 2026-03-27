"""
Skill: do_like
描述: 给帖子的评论或回复点赞/取消点赞
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

like_type 枚举值（DoLikeType）：
    3 = 点赞评论（需填 comment_id 和 comment_author_id）
    4 = 取消点赞评论（需填 comment_id 和 comment_author_id）
    5 = 点赞回复（需填 reply_id 和 reply_author_id）
    6 = 取消点赞回复（需填 reply_id 和 reply_author_id）

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

TOOL_NAME = "do_like"

# like_type 枚举（DoLikeType）
LIKE_TYPE_LIKE_COMMENT   = 3
LIKE_TYPE_UNLIKE_COMMENT = 4
LIKE_TYPE_LIKE_REPLY     = 5
LIKE_TYPE_UNLIKE_REPLY   = 6

SKILL_MANIFEST = {
    "name": "do-like",
    "description": (
        "给帖子的评论或回复点赞/取消点赞。"
        "like_type=3/4 操作评论点赞（需填 comment_id 和 comment_author_id）；"
        "like_type=5/6 操作回复点赞（需填 reply_id 和 reply_author_id）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "like_type": {
                "type": "integer",
                "description": "点赞类型：3=点赞评论，4=取消点赞评论，5=点赞回复，6=取消点赞回复，必填",
                "enum": [3, 4, 5, 6]
            },
            "feed_id": {
                "type": "string",
                "description": "帖子ID，string，必填"
            },
            "feed_author_id": {
                "type": "string",
                "description": "帖子发表人用户ID，string，必填"
            },
            "feed_create_time": {
                "type": "string",
                "description": "帖子发表时间（秒级时间戳），uint64 字符串，必填"
            },
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，建议填写"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串，建议填写"
            },
            "comment_id": {
                "type": "string",
                "description": "评论ID（like_type=3/4 时必填；like_type=5/6 回复点赞时也必填，填回复所属评论的ID），string"
            },
            "comment_author_id": {
                "type": "string",
                "description": "评论人用户ID（like_type=3/4 时必填；like_type=5/6 回复点赞时也必填），string"
            },
            "reply_id": {
                "type": "string",
                "description": "回复ID（like_type=5/6 时必填），string"
            },
            "reply_author_id": {
                "type": "string",
                "description": "回复人用户ID（like_type=5/6 时必填），string"
            }
        },
        "required": ["like_type", "feed_id", "feed_author_id", "feed_create_time"]
    }
}


def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {"success": True, "data": {...}}
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err
    like_type = params["like_type"]

    # 枚举值校验：防止非法值进入后续逻辑触发 KeyError 或意外行为
    valid_like_types = (LIKE_TYPE_LIKE_COMMENT, LIKE_TYPE_UNLIKE_COMMENT,
                        LIKE_TYPE_LIKE_REPLY, LIKE_TYPE_UNLIKE_REPLY)
    if like_type not in valid_like_types:
        return {"success": False, "error": f"like_type 值无效：{like_type}，仅支持 3（点赞评论）/4（取消点赞评论）/5（点赞回复）/6（取消点赞回复）"}

    if like_type in (LIKE_TYPE_LIKE_COMMENT, LIKE_TYPE_UNLIKE_COMMENT):
        if not params.get("comment_id") or not params.get("comment_author_id"):
            return {"success": False, "error": "点赞/取消点赞评论时，必须提供评论ID和评论作者ID"}
    elif like_type in (LIKE_TYPE_LIKE_REPLY, LIKE_TYPE_UNLIKE_REPLY):
        if not params.get("reply_id") or not params.get("reply_author_id"):
            return {"success": False, "error": "点赞/取消点赞回复时，必须提供回复ID和回复作者ID"}
        if not params.get("comment_id") or not params.get("comment_author_id"):
            return {"success": False, "error": "点赞/取消点赞回复时，还需提供该回复所属的评论ID和评论作者ID"}

    # 对齐底层 StDoLikeReq 嵌套结构（透传至 feed=4/comment=6/reply=7）
    # feed=4（StFeed）
    feed = {
        "id":          params["feed_id"],                  # StFeed.id=1
        "poster": {                                         # StFeed.poster=4
            "id": str(params["feed_author_id"]),
        },
        "create_time": str(params["feed_create_time"]),    # StFeed.createTime=7
    }
    if "guild_id" in params or "channel_id" in params:
        feed["channel_info"] = {                            # StFeed.channelInfo=21
            "sign": {
                "guild_id":   str(params["guild_id"])   if "guild_id"   in params else "",
                "channel_id": str(params["channel_id"]) if "channel_id" in params else "",
            }
        }

    # like.id：评论点赞填 comment_id，回复点赞填 reply_id
    # 注意：like.id 和 like.status 用于告知服务端操作目标和方向
    like_target_id = (
        params["comment_id"] if like_type in (LIKE_TYPE_LIKE_COMMENT, LIKE_TYPE_UNLIKE_COMMENT)
        else params["reply_id"]
    )
    arguments = {
        "like_type": like_type,  # 对应底层 likeType=2
        "like": {                # 对应底层 like=3（StLike）
            "id":     like_target_id,
            "status": 1 if like_type in (LIKE_TYPE_LIKE_COMMENT, LIKE_TYPE_LIKE_REPLY) else 0,
        },
        "feed": feed,            # 对应底层 feed=4
    }

    # comment=6（StComment）：like_type=3/4 时必填，like_type=5/6 时也需填写（提供所属评论信息）
    if like_type in (LIKE_TYPE_LIKE_COMMENT, LIKE_TYPE_UNLIKE_COMMENT,
                     LIKE_TYPE_LIKE_REPLY,   LIKE_TYPE_UNLIKE_REPLY):
        arguments["comment"] = {                            # 对应底层 comment=6
            "id":        params["comment_id"],              # StComment.id=1
            "post_user": {                                  # StComment.postUser=2
                "id": str(params["comment_author_id"]),
            },
            "like_info": {                                  # StComment.likeInfo=8
                "id":     params["comment_id"],             # StLike.id=1，必填，填评论ID
                "status": 1 if like_type == LIKE_TYPE_LIKE_COMMENT else 0,
                "count":  params.get("comment_like_count", 0),
            },
        }

    # reply=7（StReply）：like_type=5/6 时填写
    if like_type in (LIKE_TYPE_LIKE_REPLY, LIKE_TYPE_UNLIKE_REPLY):
        arguments["reply"] = {                              # 对应底层 reply=7
            "id":        params["reply_id"],                # StReply.id=1
            "post_user": {                                  # StReply.postUser=2
                "id": str(params["reply_author_id"]),
            },
            "like_info": {                                  # StReply.likeInfo=7
                "id":     params["reply_id"],               # StLike.id=1，必填，填回复ID
                "status": 1 if like_type == LIKE_TYPE_LIKE_REPLY else 0,
                "count":  params.get("reply_like_count", 0),
            },
        }

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or {}
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"点赞操作失败（错误码 {ret_code}）：{ret_msg}"}
        action_map = {3: "点赞评论", 4: "取消点赞评论", 5: "点赞回复", 6: "取消点赞回复"}
        return {
            "success": True,
            "data": {
                "action": action_map.get(like_type, str(like_type)),
                "target_id": params.get("comment_id") if like_type in (3, 4) else params.get("reply_id"),
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)