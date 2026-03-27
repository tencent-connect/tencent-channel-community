"""
Skill: alter_feed
描述: 修改已有帖子的标题或正文内容，支持替换/删除图片和视频
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）

⚠️  调用前必读：references/feed-reference.md
    包含内容长度限制、拆分规则、正确调用流程等关键说明。
    禁止仅凭此脚本推断用法。
"""

import hashlib
import json
import re
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp, get_feed_share_url
from _feed_common import make_pattern_info, make_contents

TOOL_NAME = "alter_feed"  # 服务端实际注册的 MCP tool name

SKILL_MANIFEST = {
    "name": "alter-feed",
    "description": (
        "修改腾讯频道（QQ Channel）已有帖子的标题或正文内容，需提供帖子ID、帖子发表时间、频道ID和版块ID。"
        "可选择性只修改标题或正文。支持在正文中@用户（at_users参数）。"
        "支持替换图片（file_paths，本地文件自动上传）、替换视频（video_paths，本地文件自动上传）、"
        "删除所有图片（clear_images=true）、删除所有视频（clear_videos=true）。"
        "不传 file_paths/video_paths/clear_images/clear_videos 时，原帖的图片/视频会自动保留。"
    ),
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
            },
            "feed_type": {
                "type": "integer",
                "description": "帖子类型：1=短贴（无标题），2=长贴（有标题），必填",
                "enum": [1, 2]
            },
            "title": {
                "type": "string",
                "description": "修改后的帖子标题，长贴(feed_type=2)时选填"
            },
            "content": {
                "type": "string",
                "description": "修改后的帖子正文（纯文本，支持换行），string，选填"
            },
            "at_users": {
                "type": "array",
                "description": (
                    "正文中被@的用户列表，选填。"
                    "系统会在正文内容后面自动追加对应的 @用户 节点。"
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
            "file_paths": {
                "type": "array",
                "description": (
                    "替换帖子图片：本地图片文件路径列表，选填。"
                    "指定后自动上传至CDN，并完全替换帖子原有图片（原图片将被覆盖）。"
                    "与 clear_images 不可同时使用。"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string",  "description": "本地文件绝对路径，必填"},
                        "width":     {"type": "integer", "description": "图片宽度（像素），选填"},
                        "height":    {"type": "integer", "description": "图片高度（像素），选填"},
                    },
                    "required": ["file_path"]
                }
            },
            "video_paths": {
                "type": "array",
                "description": (
                    "替换帖子视频：本地视频文件路径列表，选填。"
                    "指定后自动上传至CDN，并完全替换帖子原有视频（原视频将被覆盖）。"
                    "与 clear_videos 不可同时使用。"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string",  "description": "本地视频文件绝对路径，必填"},
                        "width":     {"type": "integer", "description": "视频宽度（像素），选填"},
                        "height":    {"type": "integer", "description": "视频高度（像素），选填"},
                        "duration":  {"type": "integer", "description": "视频时长（秒），选填"},
                    },
                    "required": ["file_path"]
                }
            },
            "clear_images": {
                "type": "boolean",
                "description": "是否删除帖子所有图片，默认 false。为 true 时删除所有图片。与 file_paths 不可同时使用。"
            },
            "clear_videos": {
                "type": "boolean",
                "description": "是否删除帖子所有视频，默认 false。为 true 时删除所有视频。与 video_paths 不可同时使用。"
            },
            "on_upload_error": {
                "type": "string",
                "description": (
                    "file_paths/video_paths 上传失败时的处理策略：\n"
                    "  abort = 中止改帖并返回错误（默认）\n"
                    "  skip  = 跳过失败文件，继续改帖"
                ),
                "enum": ["abort", "skip"],
                "default": "abort"
            },
        },
        "required": ["feed_id", "create_time", "guild_id", "channel_id", "feed_type"]
    }
}


from _upload_util import (
    _parse_proto_fields, _get_field,
    _parse_ext_info3, _parse_video_ext_info3,
    _ensure_ffmpeg, _extract_video_cover,
    _upload_file_paths, _upload_video_paths,
    _calculate_content_length,
)

def _normalize_orig_images(images: list, client_task_id: str, feed_type: int) -> list:
    """
    将原帖透传的图片结构（仅含 picUrl/width/height）规范化为 alter_feed json_feed.images 所需结构。
    与 _build_json_images 逻辑相同，但 picId 从 picUrl hash 派生，避免空 picId。
    """
    json_images = []
    for i, img in enumerate(images):
        pic_url = img.get("url", img.get("picUrl", ""))
        # 用 picUrl 的 md5 前16位作为 picId 占位
        pic_id = img.get("picId") or img.get("task_id") or img.get("md5") or (
            hashlib.md5(pic_url.encode()).hexdigest()[:16] if pic_url else ""
        )
        json_images.append({
            "picId":           pic_id,
            "picUrl":          pic_url,
            "pattern_id":      pic_id or str(i + 1),
            "width":           img.get("width", 0),
            "height":          img.get("height", 0),
            "imageMD5":        "",
            "orig_size":       0,
            "is_orig":         False,
            "is_gif":          False,
            "isFromGameShare": False,
            "display_index":   i,
            "layerPicUrl":     "",
            "vecImageUrl":     [],
        })
    return json_images


def _build_json_images(images: list, client_task_id: str, feed_type: int) -> list:
    """构建新上传图片的 json_feed.images 数组（对齐 publish_feed 结构）。"""
    json_images = []
    for i, img in enumerate(images):
        task_id = img.get("task_id") or img.get("md5", "")
        pic_url = img.get("url", img.get("picUrl", ""))
        json_images.append({
            "picId":           task_id or img.get("picId", ""),
            "picUrl":          "/guildFeedPublish/localMedia/%s/%s/thumb.jpg" % (client_task_id, task_id) if feed_type == 1 else pic_url,
            "pattern_id":      task_id or img.get("picId", "") or str(i + 1),
            "width":           img.get("width", 0),
            "height":          img.get("height", 0),
            "imageMD5":        "",
            "orig_size":       0,
            "is_orig":         False,
            "is_gif":          False,
            "isFromGameShare": False,
            "display_index":   i,
            "layerPicUrl":     "",
            "vecImageUrl":     [],
        })
    return json_images


def _build_json_videos(videos: list, client_task_id: str) -> list:
    """构建 json_feed.videos 数组（对齐 publish_feed 结构）。
    透传原帖视频时优先用真实 cover picUrl/picId，新上传视频用本地占位路径。
    """
    json_videos = []
    for i, v in enumerate(videos):
        task_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", v.get("fileId", ""))
        # 封面：优先用原帖真实封面（透传场景），fallback 用本地占位路径（新上传场景）
        orig_cover = v.get("cover") or {}
        cover_pic_id  = orig_cover.get("picId") or task_id
        cover_pic_url = orig_cover.get("picUrl") or (
            "/guildFeedPublish/localMedia/%s/%s/thumb_%s.jpg" % (
                client_task_id, task_id, str(uuid.uuid4()).upper()
            )
        )
        cover_width  = orig_cover.get("width")  or v.get("width", 0)
        cover_height = orig_cover.get("height") or v.get("height", 0)
        json_videos.append({
            "cover": {
                "picId":           cover_pic_id,
                "picUrl":          cover_pic_url,
                "pattern_id":      str(i + 1),
                "width":           cover_width,
                "height":          cover_height,
                "imageMD5":        "",
                "orig_size":       0,
                "is_orig":         False,
                "is_gif":          False,
                "isFromGameShare": False,
                "display_index":   0,
                "layerPicUrl":     "",
                "vecImageUrl":     [],
            },
            "fileId":             task_id,
            "videoMD5":           "",
            "videoSource":        0,
            "mediaQualityScore":  0,
            "approvalStatus":     0,
            "videoRate":          0,
            "display_index":      i,
            "height":             v.get("height", 0),
            "width":              v.get("width", 0),
            "duration":           v.get("duration", 0),
            "transStatus":        0,
            "pattern_id":         str(i + 1),
            "videoPrior":         0,
            "playUrl":            v.get("playUrl", "") or v.get("url", ""),
        })
    return json_videos


def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    底层透传说明（对齐线上改帖抓包）：
      - feed=2（StFeed）：完全为空
      - json_feed=8（StAlterFeedReq.jsonFeed=8）：完整 JSON，关键字段：
        - channelInfo.sign 使用 snake_case 整数（guild_id/channel_id/channel_type）
        - 包含 patternInfo、client_task_id、poi、third_bar、feed_risk_info 等
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    guild_id      = params["guild_id"]
    channel_id    = params["channel_id"]
    feed_id       = params["feed_id"]
    create_time   = params["create_time"]
    try:
        create_time = int(create_time)
    except (ValueError, TypeError):
        return {"success": False, "error": "create_time 必须为整数（秒级时间戳）的字符串形式，当前传入的无法转换为整数"}
    feed_type     = params["feed_type"]
    title         = params.get("title", "")
    content       = params.get("content", "")
    at_users      = params.get("at_users") or []
    clear_images  = params.get("clear_images", False)
    clear_videos  = params.get("clear_videos", False)
    file_paths    = params.get("file_paths") or []
    video_paths   = params.get("video_paths") or []
    on_error      = params.get("on_upload_error", "abort")

    # 参数互斥校验
    if clear_images and file_paths:
        return {"success": False, "error": "clear_images 与 file_paths 不可同时使用"}
    if clear_videos and video_paths:
        return {"success": False, "error": "clear_videos 与 video_paths 不可同时使用"}

    # ── 内容限制校验（上传前快速失败）──────────────────────────────────────
    # 内容不能完全为空（无正文、无图片、无视频，且不是仅清除操作）
    if not content and not file_paths and not video_paths and not clear_images and not clear_videos:
        return {"success": False, "error": "内容不能为空，请提供正文内容或图片/视频"}

    # 长贴必须有标题
    if feed_type == 2 and not title:
        return {"success": False, "error": (
            "长贴（feed_type=2）必须提供标题（title 参数）。"
            "请补充标题后重试，或改为短贴（feed_type=1，无需标题，正文上限 1000 字）。"
        )}

    # 长短贴正文字数上限（与服务端加权规则一致：汉字=1，英文/数字=0.5）
    content_len = _calculate_content_length(content) if content else 0.0
    if feed_type == 1 and content_len > 1000:
        return {"success": False, "error": (
            f"短贴正文超过字数限制：{content_len:.0f} 字（上限 1000 字）。"
            "如需发布更长的内容，请改用长贴（feed_type=2，需提供标题）。"
        )}
    if feed_type == 2 and content_len > 10000:
        return {"success": False, "error": f"长贴正文超过字数限制：{content_len:.0f} 字（上限 10000 字）"}

    # 图片数量上限（仅替换场景，clear_images 时不涉及）
    if file_paths:
        img_limit = 18 if feed_type == 1 else 50
        if len(file_paths) > img_limit:
            return {"success": False, "error": (
                f"图片数量超出限制：共 {len(file_paths)} 张"
                f"（{'短贴' if feed_type == 1 else '长贴'}上限 {img_limit} 张）"
            )}

    # 视频数量上限（仅替换场景，clear_videos 时不涉及）
    if video_paths:
        video_limit = 1 if feed_type == 1 else 5
        if len(video_paths) > video_limit:
            return {"success": False, "error": (
                f"视频数量超出限制：共 {len(video_paths)} 个"
                f"（{'短贴' if feed_type == 1 else '长贴'}上限 {video_limit} 个）"
            )}
    # ────────────────────────────────────────────────────────────────────────

    # ── 先拉原帖，透传 images/videos/files，避免改帖时丢失媒体内容 ──
    orig_images = []
    orig_videos = []
    orig_files  = []
    try:
        detail_result = call_mcp("get_feed_detail", {
            "feed_id":    feed_id,
            "guild_id":   str(guild_id),
            "channel_id": str(channel_id),
            "create_time": str(create_time),
        })
        orig_feed = (detail_result.get("structuredContent") or {}).get("feed") or {}
        if isinstance(orig_feed.get("images"), list):
            orig_images = orig_feed["images"]
        if isinstance(orig_feed.get("videos"), list):
            orig_videos = orig_feed["videos"]
        if isinstance(orig_feed.get("files"), list):
            orig_files = orig_feed["files"]
    except Exception:
        pass  # 拉取失败不影响改帖流程，媒体字段保持空

    # ── 确定最终图片列表 ──
    if clear_images:
        final_images = []
    elif file_paths:
        uploaded_images, upload_err = _upload_file_paths(file_paths, guild_id, channel_id, on_error=on_error)
        if upload_err:
            if isinstance(upload_err, dict) and upload_err.get("needs_confirm"):
                return {"success": False, "needs_confirm": True, "error": upload_err["error"]}
            return {"success": False, "error": upload_err}
        final_images = uploaded_images
    else:
        # 原帖图片补齐 task_id：优先用 picId（服务端真实 ID），fallback 用 picUrl md5
        # picId 由 get_feed_detail 透传，用于 patternInfo 图片节点 taskId/fileId 与 images[].picId 对齐
        final_images = []
        for img in orig_images:
            img = dict(img)  # 浅拷贝，避免修改原始数据
            if not img.get("task_id") and not img.get("md5"):
                pic_id = img.get("picId", "")
                if pic_id:
                    img["task_id"] = pic_id
                else:
                    pic_url = img.get("url", img.get("picUrl", ""))
                    img["task_id"] = hashlib.md5(pic_url.encode()).hexdigest()[:16] if pic_url else ""
            final_images.append(img)

    # ── 确定最终视频列表 ──
    if clear_videos:
        final_videos = []
    elif video_paths:
        uploaded_videos, video_err = _upload_video_paths(video_paths, guild_id, channel_id, on_error=on_error)
        if video_err:
            if isinstance(video_err, dict) and video_err.get("needs_confirm"):
                return {"success": False, "needs_confirm": True, "error": video_err["error"]}
            return {"success": False, "error": video_err}
        final_videos = uploaded_videos
    else:
        final_videos = orig_videos  # 保留原帖视频

    client_task_id = str(uuid.uuid4()).upper()

    # ── 生成 patternInfo（含图片/视频节点）──
    pattern_info = make_pattern_info(feed_type, content, at_users, final_images, final_videos)

    # ── 构建 json_feed.images / videos ──
    # 新上传的图片用新结构；原帖透传的图片保持原结构不变（服务端兼容）
    has_new_images = bool(file_paths and not clear_images)
    has_new_videos = bool(video_paths and not clear_videos)

    if has_new_images:
        json_images = _build_json_images(final_images, client_task_id, feed_type)
    else:
        # 原帖图片结构仅含 picUrl/width/height，需规范化补齐必要字段
        json_images = _normalize_orig_images(final_images, client_task_id, feed_type)

    if has_new_videos:
        json_videos = _build_json_videos(final_videos, client_task_id)
    else:
        # 原帖视频结构仅含 fileId/playUrl/duration/width/height，需规范化补齐必要字段
        # （cover、pattern_id、videoMD5 等），与 _build_json_videos 对齐
        json_videos = _build_json_videos(final_videos, client_task_id) if final_videos else []

    json_feed_obj = {
        "id":            feed_id,
        "feed_type":     feed_type,
        "createTime":    create_time,
        "createTimeNs":  create_time * 1_000_000_000,
        "client_task_id": client_task_id,
        "poster": {
            "id":   "",
            "nick": "",
            "icon": {"iconUrl": ""},
        },
        # ⚠️ sign 内部用 snake_case + 整数，与 publish_feed 保持一致
        "channelInfo": {
            "sign": {
                "guild_id":    guild_id,
                "channel_id":  channel_id,
                "channel_type": 7,
            },
            "name":      "",
            "is_square": False,
        },
        "title":    {"contents": [{"type": 1, "textContent": {"text": title}}] if title else []},
        "contents": {"contents": make_contents(content, at_users, feed_type)},
        "at_users": at_users,   # 顶层 at_users，与 publish_feed 保持一致，用于详情页解析
        "patternInfo":       pattern_info,
        "tagInfos":          [],
        "recommend_channels": [],
        "images":            json_images,
        "videos":            json_videos,
        "files":             orig_files,
        "feed_source_type":  0,
        "media_lock_count":  0,
        "feed_risk_info":    {"risk_content": "", "iconUrl": "", "declaration_type": 0},
        "poi": {
            "title": "", "address": "",
            "location": {"lng": 0, "lat": 0},
            "poi_id": "",
            "ad_info": {"province": "", "adcode": 0, "district": "", "city": ""},
        },
        "third_bar": {"id": "", "button_scheme": "", "content_scheme": ""},
    }

    # client_content：新上传图片/视频的 CDN 信息；长贴时还必须写入 patternInfo
    # 长贴（feed_type=2）客户端编辑器依赖 client_content.patternInfo 渲染富文本正文，
    # 即使没有新上传的媒体文件也必须传入，否则编辑器正文显示空白。
    arguments: dict = {
        "feed":      {},
        "json_feed": json.dumps(json_feed_obj, ensure_ascii=False),
    }
    if has_new_images or has_new_videos or feed_type == 2:
        client_content: dict = {}
        if feed_type == 2:
            client_content["patternInfo"] = pattern_info  # 长贴必须写入，客户端编辑器依赖此字段渲染富文本
        if has_new_images:
            client_content["clientImageContents"] = [
                {
                    "url":       img.get("url", ""),
                    "md5":       img.get("md5", ""),
                    "orig_size": img.get("orig_size", 0),
                    "task_id":   img.get("task_id") or img.get("md5", ""),
                }
                for img in final_images
            ]
        if has_new_videos:
            client_content["clientVideoContents"] = [
                {
                    "task_id":   v.get("task_id") or v.get("video_id") or v.get("file_uuid", ""),
                    "video_id":  v.get("video_id") or v.get("file_uuid", ""),
                    "cover_url": v.get("cover_url", ""),
                }
                for v in final_videos
            ]
        arguments["client_content"] = client_content

    try:
        result = call_mcp(TOOL_NAME, arguments)
        # isError=True：错误码/msg 在 content[].text 里
        if result.get("isError"):
            raw = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "")
            m = re.search(r"retCode[:\s]+(\d+)[,\s]*(?:msg[:\s]*(.+))?$", raw, re.IGNORECASE)
            if m:
                code = m.group(1)
                msg  = (m.group(2) or "").strip().lstrip("[backend]").strip()
                err  = f"改帖失败（错误码 {code}）：{msg}" if msg else f"改帖失败（错误码 {code}）"
            else:
                err = raw or "改帖失败"
            return {"success": False, "error": err}
        # retCode 在 structuredContent._meta 里
        structured = result.get("structuredContent") or {}
        top_meta = result.get("_meta", {}).get("AdditionalFields", {})
        sc_meta  = structured.get("_meta", {}).get("AdditionalFields", {})
        meta     = top_meta if top_meta.get("retCode") else sc_meta
        ret_code = meta.get("retCode", 0)
        if ret_code != 0:
            ret_msg = meta.get("errMsg", "") or meta.get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"改帖失败（错误码 {ret_code}）：{ret_msg}"}

        share_url = get_feed_share_url(str(guild_id), str(channel_id), feed_id)
        result_data: dict = {"updated": True, "content": content}
        if title:
            result_data["title"] = title
        if at_users:
            result_data["at_users"] = [u.get("nick", u.get("id", "")) for u in at_users]
        if clear_images:
            result_data["images"] = "已清空"
        elif file_paths:
            result_data["images"] = f"已替换（{len(final_images)} 张）"
        if clear_videos:
            result_data["videos"] = "已清空"
        elif video_paths:
            result_data["videos"] = f"已替换（{len(final_videos)} 个）"
        if share_url:
            result_data["share_url"] = share_url

        return {"success": True, "data": result_data}
    except Exception as e:
        m = re.search(r"retCode[=:\s]+(\d+)\)?\s*[:\s]+(?:\[backend\]\s*)?(.+)", str(e))
        if m:
            code, msg = m.group(1), m.group(2).strip()
            return {"success": False, "error": f"改帖失败（错误码 {code}）：{msg}"}
        return {"success": False, "error": f"改帖失败：{e}"}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
