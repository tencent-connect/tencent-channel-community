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

TOOL_NAME = "do_reply"

# reply_type 枚举（对应 DoReplyType）
REPLY_TYPE_DEL = 0        # 回复者自己删除回复
REPLY_TYPE_REPLY = 1      # 发表回复
REPLY_TYPE_DEL_OWNER = 2  # 帖子主人（Owner）删除他人回复

SKILL_MANIFEST = {
    "name": "do-reply",
    "description": (
        "回复帖子下某条已有评论，或回复评论下的某条回复，也可删除已有回复。"
        "只要目标是某条具体的评论或回复（而非帖子本身），就必须使用本工具，不能用 do_comment。"
        "reply_type=1 时发表回复（必填 content 和 replier_id，以及 comment_id/comment_author_id/comment_create_time）；"
        "reply_type=0 时回复者自己删除回复，reply_type=2 时帖子主人删除他人回复（均必填 reply_id）。"
        "回复某条回复时需额外填 target_reply_id、target_user_id 和 target_user_nick（被回复人昵称），"
        "skill 会自动在内容前插入 @昵称 节点，使回复显示「回复 @xxx」。"
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
                "type": "string",
                "description": "帖子发表时间（秒级时间戳），uint64 字符串，必填"
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
                "type": "string",
                "description": "评论发表时间（秒级时间戳），uint64 字符串，必填"
            },
            "reply_type": {
                "type": "integer",
                "description": "操作类型：1=发表回复（默认/最常用），0=回复者自己删除回复，2=帖子主人（Owner）删除他人回复，必填",
                "enum": [1, 0, 2]
            },
            "replier_id": {
                "type": "string",
                "description": "回复人用户ID，string，必填"
            },
            "content": {
                "type": "string",
                "description": (
                    "回复内容（reply_type=1 时必填），string。"
                    "⚠️ 禁止在 content 中手动拼写 '@用户名' 文本来模拟 at——这只是纯文字，不会产生系统级 at 效果，且与系统自动插入的 at 节点重叠会导致内容异常。"
                    "需要 at 用户时，请使用 at_users 参数（系统自动在内容前插入 at 节点）；"
                    "回复某条回复时，请填写 target_user_id + target_user_nick（系统自动插入「回复 @xxx」节点）。"
                )
            },
            "at_users": {
                "type": "array",
                "description": (
                    "被@的用户列表（reply_type=1 时可选）。"
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
                "description": (
                    "被回复的回复ID。"
                    "**当你要回复的对象是某条回复（而非评论本身）时，此字段必须填写**，"
                    "否则楼层嵌套关系丢失，UI 无法正确显示「回复 @xxx」。"
                    "从 get_feed_comments 的 replies_preview[].reply_id 或 get_next_page_replies 的 replies[].id 获取。"
                )
            },
            "target_user_id": {
                "type": "string",
                "description": (
                    "被回复人用户ID。"
                    "回复某条回复时必须填写（与 target_reply_id 配套使用）。"
                    "从 get_feed_comments 的 replies_preview[].author_id 或 get_next_page_replies 的 replies[].author_id 获取。"
                )
            },
            "target_user_nick": {
                "type": "string",
                "description": "被回复人昵称，string，选填。与 target_user_id 配合使用，系统会自动在内容前插入 @昵称 节点，使回复显示「回复 @xxx」"
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
        "required": [
            "feed_id", "feed_author_id", "feed_create_time",
            "comment_id", "comment_author_id", "comment_create_time",
            "reply_type", "replier_id"
        ]
    }
}


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

    # 枚举值校验：防止非法值（如 99）进入 else 分支错误构造删除请求
    valid_reply_types = (REPLY_TYPE_DEL, REPLY_TYPE_REPLY, REPLY_TYPE_DEL_OWNER)
    if reply_type not in valid_reply_types:
        return {"success": False, "error": f"reply_type 值无效：{reply_type}，仅支持 0（删除回复）/1（发表回复）/2（帖子主人删除回复）"}

    # 组装 reply（snake_case，交由 _to_camel_keys 转换）
    reply: dict = {
        "post_user": {"id": params["replier_id"]},
    }
    if reply_type == REPLY_TYPE_REPLY:
        if not params.get("content"):
            return {"success": False, "error": "发表回复时必须填写回复内容"}
        images = params.get("images") or []
        if len(images) > 1:
            return {"success": False, "error": f"回复图片数量超出限制：{len(images)} 张（上限 1 张）"}
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
        # 回复某条回复时，若有 target_user_id + target_user_nick 且 at_users 未手动指定，
        # 则自动注入，使 UI 显示「回复 @xxx」
        if not at_users and params.get("target_user_id") and params.get("target_user_nick"):
            at_users = [{"id": params["target_user_id"], "nick": params["target_user_nick"]}]
        contents = build_json_contents(params["content"], at_users)
        json_reply_obj: dict = {"contents": contents}
        images = params.get("images") or []
        if images:
            json_reply_obj["images"] = images
        arguments["json_reply"] = json.dumps(json_reply_obj, ensure_ascii=False, separators=(",", ":"))
    else:
        arguments["json_reply"] = "{}"

    try:
        result = call_mcp(TOOL_NAME, arguments)
        structured = result.get("structuredContent") or result
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"回复操作失败（错误码 {ret_code}）：{ret_msg}"}
        reply_info = structured.get("reply") or {}
        reply_id = reply_info.get("id") or reply_info.get("replyId") or ""
        create_time = reply_info.get("createTime") or reply_info.get("create_time") or ""
        data: dict = {"回复时间": format_timestamp(create_time)}
        if reply_type == REPLY_TYPE_REPLY:
            if reply_id:
                data["reply_id"] = reply_id
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

