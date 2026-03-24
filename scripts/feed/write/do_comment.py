"""
Skill: do_comment
描述: 对帖子发表评论或删除评论
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

comment_type 枚举值：
    0 = 评论者自己删除评论（需填 comment_id）
    1 = 发表评论（需填 content）
    2 = 帖子主人（Owner）删除他人评论（需填 comment_id）

at 支持：
    发表评论时可通过 at_users 传入被@的用户列表，系统自动在内容最前面插入 at_content 节点。
    格式参考：[{"id": "144115219800577368", "nick": "用户昵称"}]

鉴权：get_token() → .env → mcporter（见 scripts/manage/common.py）。
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp

TOOL_NAME = "do_comment"

# comment_type 枚举（对应 DoCommentType）
COMMENT_TYPE_DEL = 0        # 删除评论
COMMENT_TYPE_COMMENT = 1    # 发表评论
COMMENT_TYPE_DEL_OWNER = 2  # 帖子主人（Owner）删除评论

SKILL_MANIFEST = {
    "name": "do-comment",
    "description": (
        "对帖子发表顶层评论或删除评论。"
        "仅用于直接评论帖子本身（顶层评论）；若要回复某条已有评论，必须使用 do_reply 而非本工具。"
        "comment_type=1 时发表评论（必填 content）；"
        "comment_type=0 时评论者自己删除评论；comment_type=2 时帖子主人（Owner）删除他人评论（均必填 comment_id）。"
        "发表评论时支持通过 at_users 指定被@的用户（系统自动在内容前插入@节点）。"
        "成功发表后返回评论ID和评论时间。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "帖子ID，string，必填"
            },
            "feed_create_time": {
                "type": "integer",
                "description": "帖子发表时间（秒级时间戳），uint64，必填"
            },
            "comment_type": {
                "type": "integer",
                "description": "操作类型：0=评论者自己删除评论，1=发表评论，2=帖子主人（Owner）删除他人评论，必填",
                "enum": [0, 1, 2]
            },
            "content": {
                "type": "string",
                "description": "评论内容（comment_type=1 时必填），string"
            },
            "at_users": {
                "type": "array",
                "description": (
                    "被@的用户列表（comment_type=1 时可选）。"
                    "系统会在评论内容最前面自动插入对应的 @用户 节点。"
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
                "description": "评论图片列表（comment_type=1 时可选），每项包含 picId、picUrl、imageMD5、width、height、orig_size、is_orig、is_gif 等字段",
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
            "comment_id": {
                "type": "string",
                "description": "评论ID（删除评论时必填），string"
            },
            "comment_author_id": {
                "type": "string",
                "description": "评论作者用户ID（删除评论时必填），string"
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
        "required": ["feed_id", "feed_create_time", "comment_type"]
    }
}


def _build_json_comment_contents(content: str, at_users: list) -> list:
    """
    构造 jsonComment.contents 数组。
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
        {"success": True, "data": {"comment": {"id": ..., "createTime": ...}}}
        或 {"success": False, "error": "..."}
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err
    comment_type = params["comment_type"]

    # 组装 comment（snake_case，交由 _to_camel_keys 转换）
    comment: dict = {
        "post_user": {"id": ""},
    }
    if comment_type == COMMENT_TYPE_COMMENT:
        if not params.get("content"):
            return {"success": False, "error": "发表评论时必须填写评论内容"}
        comment["create_time"] = str(int(time.time()))
        comment["content"] = params["content"]  # 网关 skill 层据此自动构造 jsonComment
    else:
        if not params.get("comment_id"):
            return {"success": False, "error": "删除评论时必须填写评论ID"}
        if not params.get("comment_author_id"):
            return {"success": False, "error": "删除评论时必须填写评论作者ID"}
        comment["id"] = params["comment_id"]
        comment["post_user"] = {"id": str(params["comment_author_id"])}

    # 组装 feed（snake_case，交由 _to_camel_keys 转换；sign 内部保持 snake_case 不变）
    feed: dict = {
        "id": params["feed_id"],
        "poster": {"id": ""},
        "create_time": str(params["feed_create_time"]),
    }
    channel_sign: dict = {}
    if "guild_id" in params:
        channel_sign["guild_id"] = str(params["guild_id"])
    if "channel_id" in params:
        channel_sign["channel_id"] = str(params["channel_id"])
    if channel_sign:
        # channel_info -> channelInfo by _to_camel_keys，sign 内部 guild_id/channel_id 保持 snake_case
        feed["channel_info"] = {"sign": channel_sign}

    arguments: dict = {
        "comment_type": comment_type,
        "comment": comment,
        "feed": feed,
    }

    if comment_type == COMMENT_TYPE_COMMENT:
        at_users = params.get("at_users") or []
        contents = _build_json_comment_contents(params["content"], at_users)
        json_comment_obj: dict = {"contents": contents}
        images = params.get("images") or []
        if images:
            json_comment_obj["images"] = images
        arguments["json_comment"] = json.dumps(json_comment_obj, ensure_ascii=False, separators=(",", ":"))
    else:
        # 删除评论时也需要构造 json_comment，只带 id
        json_comment_obj = {"id": params["comment_id"]}
        arguments["json_comment"] = json.dumps(json_comment_obj, ensure_ascii=False, separators=(",", ":"))

    try:
        result = call_mcp(TOOL_NAME, arguments)
        if result.get("isError"):
            raw = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "")
            # 服务端原始格式如：code(返回码...): 10000  →  转为可读提示
            import re as _re
            m = _re.search(r":\s*(\d+)\s*$", raw)
            code = m.group(1) if m else ""
            err = f"评论操作失败（错误码 {code}）" if code else (raw or "评论操作失败")
            return {"success": False, "error": err}
        structured = result.get("structuredContent") or result
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"评论操作失败（错误码 {ret_code}）：{ret_msg}"}
        comment_info = structured.get("comment") or {}
        comment_id = comment_info.get("id") or comment_info.get("commentId") or ""
        create_time = comment_info.get("createTime") or comment_info.get("create_time") or ""
        data: dict = {"comment_id": comment_id, "create_time": create_time}
        if comment_type == COMMENT_TYPE_COMMENT:
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

