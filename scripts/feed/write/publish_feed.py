"""
Skill: publish_feed
描述: 在指定频道版块发表一篇新帖子
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）

⚠️  调用前必读：references/feed-reference.md
    包含内容长度限制、拆分规则、正确调用流程等关键说明。
    禁止仅凭此脚本推断用法。
"""

import json
import re
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp, format_timestamp, get_feed_share_url
from _feed_common import make_pattern_info, make_contents
from _upload_util import (
    _parse_proto_fields, _get_field,
    _parse_ext_info3, _parse_video_ext_info3,
    _ensure_ffmpeg, _extract_video_cover,
    _upload_file_paths, _upload_video_paths,
    _calculate_content_length,
)

TOOL_NAME = "publish_feed"

SKILL_MANIFEST = {
    "name": "publish-feed",
    "description": "在腾讯频道（QQ Channel）发表一篇新帖子。支持两种模式：1）普通用户模式（默认）：需传 guild_id 指定频道；若上下文中没有 channel_id，必须先调用 get_guild_channel_list 获取版块列表（接口返回所有类型版块），自行排除语音频道、文字消息频道、分类分组等非帖子类型版块，在剩余帖子类版块中找到名为「帖子广场」的版块（向用户描述为「全部」版块，严禁对用户提及「帖子广场」），默认使用该版块的 channel_id 直接发帖，无需再次询问用户；只有用户明确要求发到其他具体版块时，才展示其余帖子类版块列表供用户选择；2）作者身份模式：用户是频道作者时无需指定频道/版块，不传 guild_id 和 channel_id（或均传 0）即可全局发帖。支持短贴(feed_type=1,无标题)和长贴(feed_type=2,有标题)。支持附带图片/视频（本地文件自动上传至CDN）。支持在正文中@用户（at_users参数）。成功后返回新帖子ID、发表时间和分享链接。注意：只需传入 guild_id、channel_id、title、content、feed_type、at_users、images/file_paths/video_paths 等参数，patternInfo/jsonFeed 等底层字段由 skill 内部自动生成，严禁手动构造；严禁绕开本 skill 直接调用底层 MCP publish_feed 工具，否则会产生不合规的 jsonFeed 结构。",
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "string",
                "description": "频道ID，uint64 字符串，选填。用户提供时在对应频道下发帖；用户未提供时须先询问用户是发到指定频道还是全局发帖，确认后再决定是否填入"
            },
            "channel_id": {
                "type": "string",
                "description": "版块（子频道）ID，uint64 字符串。普通用户模式必填（默认场景）；若上下文中没有 channel_id，必须先调用 get_guild_channel_list 后只保留帖子类版块，找到「帖子广场」版块（对用户称「全部」版块）使用其 channel_id，无需询问用户；用户明确指定其他版块时才填对应值；作者身份全局发帖时不填（默认0）"
            },
            "title": {
                "type": "string",
                "description": "帖子标题，string，长贴(feed_type=2)必填，短贴(feed_type=1)不填。⚠️ 发长贴前必须先向用户获取标题，严禁在无标题时发长贴"
            },
            "content": {
                "type": "string",
                "description": "帖子正文（纯文本，支持换行），string，选填"
            },
            "at_users": {
                "type": "array",
                "description": (
                    "正文中被@的用户列表，选填。"
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
            "feed_type": {
                "type": "integer",
                "description": "帖子类型：1=短贴（无标题），2=长贴（有标题），默认1",
                "enum": [1, 2],
                "default": 1
            },
            "images": {
                "type": "array",
                "description": "图片列表，选填。每项必须包含 url 字段（CDN地址），注意字段名是 url 不是 picUrl。可选 width、height、md5、orig_size、task_id。通常由 file_paths 自动上传后内部生成，无需手动构造",
                "items": {
                    "type": "object",
                    "properties": {
                        "url":       {"type": "string",  "description": "图片CDN URL"},
                        "width":     {"type": "integer", "description": "图片宽度（像素）"},
                        "height":    {"type": "integer", "description": "图片高度（像素）"},
                        "md5":       {"type": "string",  "description": "图片MD5，选填"},
                        "orig_size": {"type": "integer", "description": "原始文件大小（字节），选填"},
                        "task_id":   {"type": "string",  "description": "上传任务ID，选填，用于关联client_content"}
                    },
                    "required": ["url"]
                }
            },
            "file_paths": {
                "type": "array",
                "description": (
                    "本地【图片】文件路径列表，选填。仅用于图片（jpg/png/gif 等），内部使用 business_type=1002 上传。"
                    "⚠️ 严禁将视频文件（mp4/mov/avi 等）传入此参数，视频必须使用 video_paths 参数，"
                    "否则会因 business_type 错误导致上传失败（slice N failed）。"
                    "与 images 参数可同时使用（file_paths 中的图片在前）。"
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
                    "本地视频文件路径列表，选填。指定后自动上传至CDN，上传成功后填充到 videos 字段。"
                    "视频帖子只能包含一个视频，与 images/file_paths 不可同时使用。"
                    "发视频帖前须先询问用户是否需要封面，如需要则通过每项的 cover_path 字段提供封面图片本地路径。"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "file_path":  {"type": "string",  "description": "本地视频文件绝对路径，必填"},
                        "cover_path": {"type": "string",  "description": "封面图片本地绝对路径，选填。提供后自动上传并设置为视频封面"},
                        "width":      {"type": "integer", "description": "视频宽度（像素），选填"},
                        "height":     {"type": "integer", "description": "视频高度（像素），选填"},
                        "duration":   {"type": "integer", "description": "视频时长（秒），选填"},
                    },
                    "required": ["file_path"]
                }
            },
            "on_upload_error": {
                "type": "string",
                "description": (
                    "file_paths/video_paths 上传失败时的处理策略：\n"
                    "  abort = 中止发帖并返回错误（默认，推荐）\n"
                    "  skip  = 跳过失败文件，继续发帖（图片帖可用；视频帖只有一个视频，跳过后等同于发纯文字帖）"
                ),
                "enum": ["abort", "skip"],
                "default": "abort"
            },
        },
        "required": []
    }
}



def run(params: dict) -> dict:
    """
    Skill 主入口，供 agent 框架调用。

    参数:
        params: 符合 SKILL_MANIFEST.parameters 描述的字典

    返回:
        {"success": True, "data": {"feed": {"id": ..., "create_time": ...}}}
        或 {"success": False, "error": "..."}

    底层透传说明（对齐线上抓包）：
      - feed=2（StFeed）：仅填路由信息：poster.id、channelInfo.sign
        实际内容字段（title/contents）留空，由 jsonFeed 承载
      - json_feed=7（StPublishFeedReq.jsonFeed）：JSON字符串，包含完整帖子内容
        - feed_type=1（短贴，无标题）或 feed_type=2（长贴，有标题）
        - 所有 key 使用 snake_case（对齐线上客户端抓包）
        - patternInfo：富文本块结构，按换行拆分段落
      - images[].pattern_id / picId 与 patternInfo 中 type=6 节点的 id/taskId 一一对应（均使用 task_id）
      - images[].picUrl 短贴时填本地占位路径（对齐线上客户端），长贴时填真实 CDN URL
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    guild_id   = params.get("guild_id") or 0
    channel_id = params.get("channel_id") or 0
    title      = (params.get("title") or "").strip()
    content    = (params.get("content") or "").strip()
    images     = params.get("images", [])
    # feed_type 推断：如果传了 title 但 feed_type 默认为 1，自动升级为 2（长贴）
    feed_type  = params.get("feed_type", 1)
    if title and feed_type == 1:
        feed_type = 2  # 有标题时强制使用长贴模式
    on_error   = params.get("on_upload_error", "abort")
    at_users   = params.get("at_users") or []

    # 普通用户模式下，guild_id 和 channel_id 须为有效正整数
    # 作者身份全局发帖时 guild_id=0 且 channel_id=0 是合法的
    if guild_id and not channel_id:
        return {"success": False, "error": (
            "缺少 channel_id（版块ID）。请先调用 get_guild_channel_list 获取版块列表，"
            "找到「帖子广场」版块（对用户称「全部」版块）并使用其 channel_id。"
        )}
    if channel_id and not guild_id:
        return {"success": False, "error": "缺少 guild_id（频道ID），请提供有效的频道ID。"}

    if "image_paths" in params and "file_paths" not in params:
        return {"success": False, "error": (
            "参数名错误：应为 file_paths（不是 image_paths）。"
            "请将本地图片路径列表传入 file_paths 参数。"
        )}

    video_paths = params.get("video_paths", [])
    file_paths  = params.get("file_paths", [])

    # ── 参数误用检测：file_paths 里混入视频文件 ──────────────────────────────
    _VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".ts", ".rmvb"}
    _bad_videos = []
    for _entry in file_paths:
        _fp = _entry if isinstance(_entry, str) else _entry.get("file_path", "")
        if os.path.splitext(_fp.lower())[1] in _VIDEO_EXTS:
            _bad_videos.append(_fp)
    if _bad_videos:
        return {"success": False, "error": (
            f"file_paths 中包含视频文件：{_bad_videos}。\n"
            "视频文件必须通过 video_paths 参数传入（内部使用 business_type=1003），"
            "用 file_paths 传视频会因 business_type=1002（图片）导致上传失败（slice N failed）。\n"
            "请将视频路径移到 video_paths 参数后重试。"
        )}
    # ────────────────────────────────────────────────────────────────────────

    # ── 内容限制校验（上传前快速失败）──────────────────────────────────────
    # 内容不能完全为空（无正文、无图片、无视频）
    # 注意：content 已经 strip，纯空格内容会变为空字符串被拦截
    if not content and not images and not file_paths and not video_paths:
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

    # 图片数量上限：合并 images + file_paths 计总数
    total_images = len(images) + len(file_paths)
    img_limit = 18 if feed_type == 1 else 50
    if total_images > img_limit:
        return {"success": False, "error": (
            f"图片数量超出限制：共 {total_images} 张"
            f"（{'短贴' if feed_type == 1 else '长贴'}上限 {img_limit} 张）"
        )}

    # 视频数量上限
    video_limit = 1 if feed_type == 1 else 5
    if len(video_paths) > video_limit:
        return {"success": False, "error": (
            f"视频数量超出限制：共 {len(video_paths)} 个"
            f"（{'短贴' if feed_type == 1 else '长贴'}上限 {video_limit} 个）"
        )}
    # ────────────────────────────────────────────────────────────────────────

    # 有本地媒体文件时，提前检查并自动安装依赖，避免上传到一半才报错
    if video_paths or file_paths:
        import upload_image as _uimg_check
        if not _uimg_check._libsliceupload_ready():
            print("[publish_feed] 检测到缺少上传依赖，正在自动安装 libsliceupload…", file=sys.stderr)
            try:
                _uimg_check._install_libsliceupload()
                print("[publish_feed] 依赖安装完成。", file=sys.stderr)
            except Exception as _install_exc:
                return {"success": False, "error": f"依赖安装失败，无法上传媒体文件：{_install_exc}"}
        # 检查并自动安装 ffmpeg（视频帖需要提取封面帧）
        if video_paths:
            if not _ensure_ffmpeg():
                return {"success": False, "error": (
                    "ffmpeg 自动安装失败，无法提取视频封面。\n"
                    "请手动安装后重试：\n"
                    "  macOS:   brew install ffmpeg\n"
                    "  Ubuntu:  sudo apt-get install -y ffmpeg\n"
                    "  Windows: winget install Gyan.FFmpeg"
                )}

    videos = []
    if video_paths:
        uploaded_videos, video_err = _upload_video_paths(
            video_paths, guild_id, channel_id, on_error=on_error
        )
        if video_err:
            if isinstance(video_err, dict) and video_err.get("needs_confirm"):
                return {"success": False, "needs_confirm": True, "error": video_err["error"]}
            return {"success": False, "error": video_err}
        videos = uploaded_videos

    # file_paths：自动上传本地图片，上传结果追加到 images 列表最前面
    # （file_paths 已在上方依赖检查处声明）
    if file_paths:
        uploaded_images, upload_err = _upload_file_paths(
            file_paths, guild_id, channel_id, on_error=on_error
        )
        if upload_err:
            if isinstance(upload_err, dict) and upload_err.get("needs_confirm"):
                return {"success": False, "needs_confirm": True, "error": upload_err["error"]}
            return {"success": False, "error": upload_err}
        images = uploaded_images + list(images)  # 新上传图片排在前面

    # client_content（已上传图片/视频的 CDN 信息，透传给 MCP）
    client_image_contents = []
    for idx, img in enumerate(images):
        if "url" not in img:
            hint = ""
            if "picUrl" in img:
                hint = "字段名应为 url 而非 picUrl。"
            elif "pic_url" in img:
                hint = "字段名应为 url 而非 pic_url。"
            return {"success": False, "error": (
                f"images[{idx}] 缺少 url 字段。{hint}"
                "提示：发本地图片请用 file_paths 参数（传文件路径列表），skill 会自动上传；"
                "images 参数仅用于已有 CDN URL 的场景。"
            )}
        task_id = img.get("task_id") or img.get("md5", "")
        client_image_contents.append({
            "url":       img["url"],
            "md5":       img.get("md5", ""),
            "orig_size": img.get("orig_size", 0),
            "task_id":   task_id,
        })

    # 生成 client_task_id
    client_task_id = str(uuid.uuid4()).upper()

    # 选择 patternInfo 生成方式
    pattern_info = make_pattern_info(feed_type, content, at_users, images, videos)

    # images[] 数组：pattern_id / picId 与 patternInfo type=6 节点的 id/taskId 保持一致（均为 task_id）
    # 短贴时 picUrl 填本地占位路径（对齐线上客户端），长贴时填真实 CDN URL
    json_images = []
    for i, img in enumerate(images):
        task_id = img.get("task_id") or img.get("md5", "")
        json_images.append({
            "picId":          task_id,
            "picUrl":         "/guildFeedPublish/localMedia/%s/%s/thumb.jpg" % (client_task_id, task_id) if feed_type == 1 else img.get("url", img.get("picUrl", "")),
            "pattern_id":     task_id,
            "width":          img.get("width", 0),
            "height":         img.get("height", 0),
            "imageMD5":       "",
            "orig_size":      0,
            "is_orig":        False,
            "is_gif":         False,
            "isFromGameShare": False,
            "display_index":  i,
            "layerPicUrl":    "",
            "vecImageUrl":    [],
        })

    # jsonFeed 内容（对应底层 StPublishFeedReq.jsonFeed=7）
    json_feed_obj = {
        "feed_type": feed_type,
        "id": "",
        "title": {
            "contents": make_contents(title, None, feed_type=1) if title else []
        },
        "contents": {
            "contents": make_contents(content, at_users, feed_type) if (content or at_users) else []
        },
        "at_users": at_users,  # 新增顶层at_users字段，用于详情页解析
        "patternInfo": pattern_info,
        "poster": {
            "id": "",
            "nick": "",
            "icon": {"iconUrl": ""}
        },
        "channelInfo": {
            "sign": {
                "guild_id":    guild_id,
                "channel_id":  channel_id,
                "channel_type": 0,
            },
            "name": "",
            "is_square": True,
        },
        "tagInfos": [],
        "recommend_channels": [],
        "images": json_images,
        "videos": [
            {
                "cover": {
                    "picId":          v.get("task_id") or v.get("file_uuid", ""),
                    "picUrl":         "/guildFeedPublish/localMedia/%s/%s/thumb_%s.jpg" % (
                                          client_task_id,
                                          v.get("task_id") or v.get("file_uuid", ""),
                                          str(uuid.uuid4()).upper()
                                      ),
                    "pattern_id":     str(i + 1),
                    "width":          v.get("width", 0),
                    "height":         v.get("height", 0),
                    "imageMD5":       "",
                    "orig_size":      0,
                    "is_orig":        False,
                    "is_gif":         False,
                    "isFromGameShare": False,
                    "display_index":  0,
                    "layerPicUrl":    "",
                    "vecImageUrl":    [],
                },
                "fileId":            v.get("task_id") or v.get("file_uuid", ""),
                "videoMD5":          "",
                "videoSource":       0,
                "mediaQualityScore": 0,
                "approvalStatus":    0,
                "videoRate":         0,
                "display_index":     i,
                "height":            v.get("height", 0),
                "width":             v.get("width", 0),
                "duration":          v.get("duration", 0),
                "transStatus":       0,
                "pattern_id":        str(i + 1),
                "videoPrior":        0,
                "playUrl":           "",
            }
            for i, v in enumerate(videos)
        ],
        "files": [],
        "feed_source_type": 0,
        "media_lock_count": 0,
        "createTime": 0,
        "createTimeNs": 0,
        "client_task_id": client_task_id,
        "feed_risk_info": {"risk_content": "", "iconUrl": "", "declaration_type": 0},
        "poi": {
            "title": "", "address": "",
            "location": {"lng": 0, "lat": 0},
            "poi_id": "",
            "ad_info": {"province": "", "adcode": 0, "district": "", "city": ""}
        },
        "third_bar": {"id": "", "button_scheme": "", "content_scheme": ""},
    }

    # feed=2（StFeed）：填路由信息
    feed = {
        "poster": {"id": ""},       # StFeed.poster=4
        "channel_info": {                        # StFeed.channelInfo=21
            "sign": {
                "guild_id":   str(guild_id),     # StChannelSign.guild_id=1
                "channel_id": str(channel_id),   # StChannelSign.channel_id=2
            }
        },
    }

    # client_content：图片 + 视频 CDN 信息（透传给 MCP）
    # 对齐真实客户端格式：client_content 只含 clientImageContents / clientVideoContents，
    # 不包含 patternInfo——编辑器从 jsonFeed.patternInfo 读取富文本结构，
    # 写入 client_content.patternInfo 会被客户端忽略且与真实请求不符。
    client_content = {}
    if client_image_contents:
        client_content["clientImageContents"] = client_image_contents
    if videos:
        client_video_contents = []
        for v in videos:
            task_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", "")
            vid_id  = v.get("video_id") or v.get("file_uuid", "")
            client_video_contents.append({
                "task_id":   task_id,
                "video_id":  vid_id,
                "cover_url": v.get("cover_url", ""),
            })
        client_content["clientVideoContents"] = client_video_contents

    arguments = {
        "feed":           feed,
        "json_feed":      json.dumps(json_feed_obj, ensure_ascii=False),
        "client_content": client_content,
    }

    try:
        result = call_mcp(TOOL_NAME, arguments)
        # 带图时 structuredContent 为空，错误码只出现在 content[].text，需先判断 isError
        if result.get("isError"):
            raw = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "")
            # 兼容两种格式：
            #   "... retCode: 10046, msg:频道不存在"
            #   "... failed, retCode: 10010"
            m = re.search(r"retCode[:\s]+(\d+)[,\s]*(?:msg[:\s]*(.+))?$", raw, re.IGNORECASE)
            if m:
                code = m.group(1)
                msg  = (m.group(2) or "").strip().lstrip("[backend]").strip()
                err  = f"发帖失败（错误码 {code}）：{msg}" if msg else f"发帖失败（错误码 {code}）"
            else:
                err = raw or "发帖失败"
            return {"success": False, "error": err}
        # 错误也可能在顶层或 structuredContent 的 _meta 里
        structured = result.get("structuredContent") or {}
        top_meta = result.get("_meta", {}).get("AdditionalFields", {})
        sc_meta  = structured.get("_meta", {}).get("AdditionalFields", {})
        meta     = top_meta if top_meta.get("retCode") else sc_meta
        ret_code = meta.get("retCode", 0)
        if ret_code != 0:
            ret_msg = meta.get("errMsg", "") or meta.get("retMsg", "") or str(ret_code)
            return {"success": False, "error": f"发帖失败（错误码 {ret_code}）：{ret_msg}"}
        feed_resp = structured.get("feed") or {}
        feed_id = feed_resp.get("id", "")

        # 发帖成功后自动获取分享链接
        # 作者身份模式（guild_id=0）也尝试获取，get_feed_share_url 内部失败时返回空字符串
        share_url = ""
        if feed_id:
            share_url = get_feed_share_url(
                guild_id=str(guild_id),
                channel_id=str(channel_id),
                feed_id=feed_id,
            )

        # 构建可读性高的返回结果
        feed_type_label = "短贴（无标题）" if feed_type == 1 else "长贴（有标题）"
        result_data = {
            "帖子类型": feed_type_label,
            "feed_id":  feed_id,                                           # 供后续 do_comment/do_reply 使用
            "create_time_raw": int(feed_resp.get("create_time") or feed_resp.get("createTime") or 0),
        }
        # 作者身份全局发帖模式标记
        if not guild_id and not channel_id:
            result_data["发帖模式"] = "作者身份（全局发帖）"

        # 格式化发表时间
        raw_time = feed_resp.get("create_time") or feed_resp.get("createTime")
        if raw_time:
            result_data["发表时间"] = format_timestamp(raw_time)

        if feed_type == 2 and title:
            result_data["标题"] = title
        if content:
            preview = (content[:50] + "……") if len(content) > 50 else content
            result_data["内容摘要"] = preview
        if at_users:
            result_data["@用户"] = [u.get("nick", u.get("id", "")) for u in at_users]
        if images:
            result_data["图片数量"] = f"{len(images)} 张"
        if videos:
            result_data["视频数量"] = f"{len(videos)} 个"
        if share_url:
            result_data["分享链接"] = f"<{share_url}>"
        else:
            result_data["分享链接"] = "（获取失败，可稍后手动查看）"

        return {"success": True, "data": result_data}
    except Exception as e:
        # 将 "MCP 业务错误 (retCode=10046): [backend] 频道不存在" 规整为统一格式
        m = re.search(r"retCode[=:\s]+(\d+)\)?\s*[:\s]+(?:\[backend\]\s*)?(.+)", str(e))
        if m:
            code, msg = m.group(1), m.group(2).strip()
            return {"success": False, "error": f"发帖失败（错误码 {code}）：{msg}"}
        return {"success": False, "error": f"发帖失败：{e}"}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)