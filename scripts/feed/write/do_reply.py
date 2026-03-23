"""
Skill: do_reply
描述: 对帖子的评论发表回复，或对评论下的某条回复再次回复，也可删除已有回复
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

reply_type 枚举值：
    0 = 回复者自己删除回复（需填 reply.id）
    1 = 发表回复（需填 reply.content）
    2 = 帖子主人（Owner）删除他人回复（需填 reply.id）

回复某条回复时，额外填写 reply.target_reply_id 和 reply.target_user.id。

at 支持：
    发表回复时可通过 at_users 传入被@的用户列表，系统自动在内容最前面插入 at_content 节点。
    格式参考：[{"id": "144115219800577368", "nick": "用户昵称"}]

鉴权：get_token() → .env → mcporter（见 scripts/manage/common.py）。
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp

TOOL_NAME = "do_reply"

# reply_type 枚举（对应 DoReplyType）
REPLY_TYPE_DEL = 0        # 回复者自己删除回复
REPLY_TYPE_REPLY = 1      # 发表回复
REPLY_TYPE_DEL_OWNER = 2  # 帖子主人（Owner）删除他人回复

SKILL_MANIFEST = {
    "name": "do-reply",
    "description": (
        "对帖子的某条评论发表回复，或对评论下的某条回复再次回复，也可删除已有回复。"
        "reply_type=1 时发表回复（必填 content 和 replier_id）；"
        "reply_type=0 时回复者自己删除回复，reply_type=2 时帖子主人删除他人回复（均必填 reply_id）。"
        "回复某条回复时需额外填 target_reply_id 和 target_user_id。"
        "发表回复时支持通过 at_users 指定被@的用户（系统自动在内容前插入@节点）。"
        "成功发表后返回回复ID和回复时间。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "帖子ID，string，必填"
            },
            "feed_author_id": {
                "type": "string",
                "description": "帖子发表人用户ID，string，必填"
            },
            "feed_create_time": {
                "type": "integer",
                "description": "帖子发表时间（秒级时间戳），uint64，必填"
            },
            "comment_id": {
                "type": "string",
                "description": "所属评论ID，string，必填"
            },
            "comment_author_id": {
                "type": "string",
                "description": "评论发表人用户ID，string，必填"
            },
            "comment_create_time": {
                "type": "integer",
                "description": "评论发表时间（秒级时间戳），uint64，必填"
            },
            "reply_type": {
                "type": "integer",
                "description": "操作类型：0=回复者自己删除回复，1=发表回复，2=帖子主人（Owner）删除他人回复，必填",
                "enum": [0, 1, 2]
            },
            "replier_id": {
                "type": "string",
                "description": "回复人用户ID，string，必填"
            },
            "content": {
                "type": "string",
                "description": "回复内容（reply_type=1 时必填），string"
            },
            "at_users": {
                "type": "array",
                "description": (
                    "被@的用户列表（reply_type=1 时可选）。"
                    "系统会在回复内容最前面自动插入对应的 @用户 节点。"
                    "每项需包含 id（用户ID）和 nick（用户昵称）字段。"
                    "示例：[{\"id\": \"144115219800577368\", \"nick\": \"张三\"}]"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id":   {"type": "string", "description": "用户ID"},
                        "nick": {"type": "string", "description": "用户昵称"}
                    },
                    "required": ["id", "nick"]
                }
            },
            "images": {
                "type": "array",
                "description": "回复图片列表（reply_type=1 时可选），每项包含 picId、picUrl、imageMD5、width、height、orig_size、is_orig、is_gif 等字段",
                "items": {
                    "type": "object",
                    "properties": {
                        "picId":    {"type": "string"},
                        "picUrl":   {"type": "string"},
                        "imageMD5": {"type": "string"},
                        "width":    {"type": "integer"},
                        "height":   {"type": "integer"},
                        "orig_size":{"type": "integer"},
                        "is_orig":  {"type": "boolean"},
                        "is_gif":   {"type": "boolean"}
                    }
                }
            },
            "reply_id": {
                "type": "string",
                "description": "回复ID（删除回复时必填），string"
            },
            "target_reply_id": {
                "type": "string",
                "description": "被回复的回复ID（回复某条回复时填写），string，选填"
            },
            "target_user_id": {
                "type": "string",
                "description": "被回复人用户ID，string，选填"
            },
            "guild_id": {
                "type": "integer",
                "description": "频道ID，uint64，建议填写"
            },
            "channel_id": {
                "type": "integer",
                "description": "板块（子频道）ID，uint64，建议填写"
            }
        },
        "required": [
            "feed_id", "feed_author_id", "feed_create_time",
            "comment_id", "comment_author_id", "comment_create_time",
            "reply_type", "replier_id"
        ]
    }
}


def _build_json_reply_contents(content: str, at_users: list) -> list:
    """
    构造 jsonReply.contents 数组。
    - at_users 中每个用户生成一个 type=2（AT）节点，放在最前面
    - 若有文本内容则追加一个 type=1（TEXT）节点
    at_content 结构对应线上抓包（type=1 表示普通用户 AT）：
        {"type": 2, "at_content": {"user": {"id": "...", "icon": {"iconUrl": ""}, "nick": "..."}, "type": 1}}
    """
    contents = []
    for u in (at_users or []):
        contents.append({
            "type": 2,
            "at_content": {
                "user": {
                    "id":   str(u.get("id", "")),
                    "nick": u.get("nick", ""),
                },
                "type": 1,  # AT_TYPE_USER=1
            }
        })
    if content:
        # at 用户后跟一个空格再接正文（与客户端抓包一致）
        text = (" " + content) if contents else content
        contents.append({
            "text_content": {"text": text},
            "type": 1,
            "pattern_id": "",
        })
    return contents


def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {"success": True, "data": {"reply": {"id": ..., "create_time": ...}}}
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err
    reply_type = params["reply_type"]

    # 组装 reply（snake_case，交由 _to_camel_keys 转换）
    reply: dict = {
        "post_user": {"id": params["replier_id"]},
    }
    if reply_type == REPLY_TYPE_REPLY:
        if not params.get("content"):
            return {"success": False, "error": "发表回复时必须填写回复内容"}
        reply["create_time"] = str(int(time.time()))
        reply["content"] = params["content"]
        if params.get("target_reply_id"):
            # targetReplyID 在 proto 中全大写 ID，直接用 camelCase key 避免转换错误
            reply["targetReplyID"] = params["target_reply_id"]
        if params.get("target_user_id"):
            reply["target_user"] = {"id": params["target_user_id"]}
    else:
        if not params.get("reply_id"):
            return {"success": False, "error": "删除回复时必须填写回复ID"}
        reply["id"] = params["reply_id"]

    # 组装 comment
    comment: dict = {
        "id": params["comment_id"],
        "post_user": {"id": params["comment_author_id"]},
        "create_time": str(params["comment_create_time"]),
    }

    # 组装 feed
    feed: dict = {
        "id": params["feed_id"],
        "poster": {"id": params["feed_author_id"]},
        "create_time": str(params["feed_create_time"]),
    }
    channel_sign: dict = {}
    if "guild_id" in params:
        channel_sign["guild_id"] = str(params["guild_id"])
    if "channel_id" in params:
        channel_sign["channel_id"] = str(params["channel_id"])
    if channel_sign:
        feed["channel_info"] = {"sign": channel_sign}

    arguments: dict = {
        "reply_type": reply_type,
        "reply": reply,
        "comment": comment,
        "feed": feed,
    }

    if reply_type == REPLY_TYPE_REPLY:
        at_users = params.get("at_users") or []
        contents = _build_json_reply_contents(params["content"], at_users)
        json_reply_obj: dict = {"contents": contents}
        images = params.get("images") or []
        if images:
            json_reply_obj["images"] = images
        arguments["json_reply"] = json.dumps(json_reply_obj, ensure_ascii=False, separators=(",", ":"))
    else:
        arguments["json_reply"] = "{}"

    try:
        result = call_mcp(TOOL_NAME, arguments)
        if result.get("isError"):
            raw = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "")
            import re as _re
            m = _re.search(r":\s*(\d+)\s*$", raw)
            code = m.group(1) if m else ""
            err = f"回复操作失败（错误码 {code}）" if code else (raw or "回复操作失败")
            return {"success": False, "error": err}
        structured = result.get("structuredContent") or result
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"回复操作失败（错误码 {ret_code}）：{ret_msg}"}
        reply_info = structured.get("reply") or {}
        reply_id = reply_info.get("id") or reply_info.get("replyId") or ""
        create_time = reply_info.get("createTime") or reply_info.get("create_time") or ""
        data: dict = {"reply_id": reply_id, "create_time": create_time}
        if reply_type == REPLY_TYPE_REPLY:
            data["content"] = params.get("content", "")
            at_users = params.get("at_users") or []
            if at_users:
                data["at_users"] = at_users
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)

