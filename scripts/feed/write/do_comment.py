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

⚠️  调用前必读：references/feed-reference.md
    包含内容长度限制、拆分规则、正确调用流程等关键说明。
    禁止仅凭此脚本推断用法。
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp, format_timestamp, build_json_contents, get_feed_share_url

TOOL_NAME = "do_comment"

# comment_type 枚举（对应 DoCommentType）
COMMENT_TYPE_DEL = 0        # 删除评论
COMMENT_TYPE_COMMENT = 1    # 发表评论
COMMENT_TYPE_DEL_OWNER = 2  # 帖子主人（Owner）删除评论

SKILL_MANIFEST = {
    "name": "do-comment",
    "description": (
        "对帖子发表顶层评论（最常用，comment_type=1）或删除评论。"
        "仅用于直接评论帖子本身（顶层评论）；若要回复某条已有评论，必须使用 do_reply 而非本工具。"
        "发表评论：comment_type=1，必填 content；"
        "删除评论：comment_type=0（评论者自己删）或 comment_type=2（帖子主人删他人评论），均必填 comment_id。"
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
                "type": "string",
                "description": "帖子发表时间（秒级时间戳），uint64 字符串，必填"
            },
            "comment_type": {
                "type": "integer",
                "description": "操作类型：1=发表评论（默认/最常用），0=评论者自己删除评论，2=帖子主人（Owner）删除他人评论，必填",
                "enum": [1, 0, 2]
            },
            "content": {
                "type": "string",
                "description": (
                    "评论内容（comment_type=1 时必填），string。"
                    "⚠️ 禁止在 content 中手动拼写 '@用户名' 文本来模拟 at——这只是纯文字，不会产生系统级 at 效果，且与系统自动插入的 at 节点重叠会导致内容异常。"
                    "需要 at 用户时，请使用 at_users 参数（系统自动在内容前插入 at 节点）。"
                )
            },
            "at_users": {
                "type": "array",
                "description": (
                    "被@的用户列表（comment_type=1 时可选）。"
                    "⚠️ 填写前必须先调用 guild_member_search 或 get_guild_member_list 查到目标用户的 tiny_id（字段 uint64Tinyid），"
                    "再将 tiny_id 填入 id 字段、昵称填入 nick 字段。"
                    "严禁使用 QQ 号、猜测值或任何非 tiny_id 的值；"
                    "严禁在 content 正文中手动拼写「@昵称」文本来模拟 at——那只是纯文字，不产生系统级 at 通知效果。"
                    "示例：[{\"id\": \"144115219800577368\", \"nick\": \"张三\"}]"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id":   {"type": "string", "description": "用户 tiny_id（uint64Tinyid），必须通过 guild_member_search 或 get_guild_member_list 查询获取，严禁填 QQ 号或猜测值"},
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
                "type": "string",
                "description": "频道ID，uint64 字符串，建议填写"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串，建议填写"
            }
        },
        "required": ["feed_id", "feed_create_time", "comment_type"]
    }
}


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

    # 枚举值校验：防止非法值（如 99）进入 else 分支错误构造删除请求
    valid_comment_types = (COMMENT_TYPE_DEL, COMMENT_TYPE_COMMENT, COMMENT_TYPE_DEL_OWNER)
    if comment_type not in valid_comment_types:
        return {"success": False, "error": f"comment_type 值无效：{comment_type}，仅支持 0（删除评论）/1（发表评论）/2（帖子主人删除评论）"}

    # 组装 comment（snake_case，交由 _to_camel_keys 转换）
    comment: dict = {
        "post_user": {"id": ""},
    }
    if comment_type == COMMENT_TYPE_COMMENT:
        if not params.get("content"):
            return {"success": False, "error": "发表评论时必须填写评论内容"}
        images = params.get("images") or []
        if len(images) > 1:
            return {"success": False, "error": f"评论图片数量超出限制：{len(images)} 张（上限 1 张）"}
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
        contents = build_json_contents(params["content"], at_users)
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
        structured = result.get("structuredContent") or result
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"评论操作失败（错误码 {ret_code}）：{ret_msg}"}
        comment_info = structured.get("comment") or {}
        comment_id = comment_info.get("id") or comment_info.get("commentId") or ""
        create_time = comment_info.get("createTime") or comment_info.get("create_time") or ""
        data: dict = {"评论时间": format_timestamp(create_time)}
        if comment_type == COMMENT_TYPE_COMMENT:
            if comment_id:
                data["comment_id"] = comment_id
            data["content"] = params.get("content", "")
            at_users = params.get("at_users") or []
            if at_users:
                data["at_users"] = at_users
            # 追加帖子分享链接（失败时静默忽略，不影响主流程）
            guild_id = str(params.get("guild_id", ""))
            channel_id = str(params.get("channel_id", ""))
            share_url = get_feed_share_url(guild_id, channel_id, params["feed_id"])
            if share_url:
                data["帖子链接"] = share_url
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)

