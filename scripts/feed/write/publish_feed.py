"""
Skill: publish_feed
描述: 在指定频道板块发表一篇新帖子
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp

TOOL_NAME = "publish_feed"

SKILL_MANIFEST = {
    "name": "publish-feed",
    "description": "在腾讯频道（QQ Channel）发表一篇新帖子。支持两种模式：1）普通用户模式：需传 guild_id 和 channel_id 指定频道和板块；2）作者身份模式：用户是频道作者时无需指定频道/板块，不传 guild_id 和 channel_id（或均传 0）即可全局发帖。支持短贴(feed_type=1,无标题)和长贴(feed_type=2,有标题)。支持附带图片/视频（本地文件自动上传至CDN）。支持在正文中@用户（at_users参数）。成功后返回新帖子ID、发表时间和分享链接。注意：只需传入 guild_id、channel_id、title、content、feed_type、at_users、images/file_paths/video_paths 等参数，patternInfo/jsonFeed 等底层字段由 skill 内部自动生成，严禁手动构造；严禁绕开本 skill 直接调用底层 MCP publish_feed 工具，否则会产生不合规的 jsonFeed 结构。",
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "integer",
                "description": "频道ID，uint64。普通用户模式必填；作者身份全局发帖时不填（默认0）"
            },
            "channel_id": {
                "type": "integer",
                "description": "板块（子频道）ID，uint64。普通用户模式必填；作者身份全局发帖时不填（默认0）"
            },
            "title": {
                "type": "string",
                "description": "帖子标题，string，长贴(feed_type=2)必填，短贴(feed_type=1)不填"
            },
            "content": {
                "type": "string",
                "description": "帖子正文（纯文本，支持换行），string，选填"
            },
            "at_users": {
                "type": "array",
                "description": (
                    "正文中被@的用户列表，选填。"
                    "系统会在正文内容最前面自动插入对应的 @用户 节点。"
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
                    "本地图片文件路径列表，选填。指定后自动上传至CDN，上传成功后追加到 images 列表最前面。"
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
            "on_upload_error": {
                "type": "string",
                "description": (
                    "file_paths/video_paths 上传失败时的处理策略：\n"
                    "  abort = 中止发帖并返回错误（默认）\n"
                    "  skip  = 跳过失败文件，继续发帖"
                ),
                "enum": ["abort", "skip"],
                "default": "abort"
            },
        },
        "required": []
    }
}


def _decode_varint(data: bytes, pos: int):
    """从 pos 解码 protobuf varint，返回 (value, new_pos)。"""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return result, pos


def _parse_proto_fields(data: bytes) -> dict:
    """解析 protobuf 字节流，返回 {field_num: value_or_list}。
    repeated 字段自动聚合为 list。wire_type=2 的值保留为 bytes。"""
    fields = {}
    pos = 0
    while pos < len(data):
        tag_val, pos = _decode_varint(data, pos)
        field_num = tag_val >> 3
        wire_type = tag_val & 7
        if wire_type == 0:
            val, pos = _decode_varint(data, pos)
        elif wire_type == 2:
            length, pos = _decode_varint(data, pos)
            val = data[pos:pos + length]; pos += length
        elif wire_type == 5:
            val = data[pos:pos + 4]; pos += 4
        elif wire_type == 1:
            val = data[pos:pos + 8]; pos += 8
        else:
            break  # 未知 wire_type，停止解析
        if field_num in fields:
            existing = fields[field_num]
            if isinstance(existing, list):
                existing.append(val)
            else:
                fields[field_num] = [existing, val]
        else:
            fields[field_num] = val
    return fields


def _get_field(fields: dict, field_num: int, default=None):
    """取字段值；repeated 取最后一个，absent 返回 default。"""
    val = fields.get(field_num, default)
    if isinstance(val, list):
        return val[-1]
    return val


def _parse_ext_info3(ext_info3: bytes, hint_width: int = 0,
                     hint_height: int = 0, file_md5: str = "",
                     file_size: int = 0, file_uuid: str = "") -> dict:
    """
    反序列化 ext_info3 (NTPhotoUploadRspExtinfo protobuf)，提取正确的 CDN 图片 URL。

    NTPhotoUploadRspExtinfo:
      field 2 = repeated ImgInfo img_infos
    ImgInfo:
      field 2 = uint32 img_class  (1=大图, 2=原图, 3=小图)
      field 4 = uint32 img_width
      field 5 = uint32 img_height
      field 7 = bytes  img_md5
      field 8 = string img_url    ← 正确的 CDN URL (channelr.photo.store.qq.com/psc?...)

    选择策略：优先取 img_class=2（原图），其次 img_class=1（大图），最后取任意有 img_url 的。
    返回: {"url", "width", "height", "md5", "orig_size", "task_id"}
    """
    if not ext_info3:
        return {"url": "", "width": hint_width, "height": hint_height,
                "md5": file_md5, "orig_size": file_size, "task_id": file_uuid or file_md5}

    root = _parse_proto_fields(ext_info3)

    # field 2 = repeated ImgInfo（可能是 bytes 或 list of bytes）
    img_infos_raw = root.get(2)
    if img_infos_raw is None:
        img_infos_raw = []
    elif isinstance(img_infos_raw, bytes):
        img_infos_raw = [img_infos_raw]
    # 否则已经是 list

    # 解析每个 ImgInfo
    candidates = []
    for raw in img_infos_raw:
        if not isinstance(raw, bytes):
            continue
        fi = _parse_proto_fields(raw)
        img_class  = _get_field(fi, 2, 0)
        img_width  = _get_field(fi, 4, 0)
        img_height = _get_field(fi, 5, 0)
        img_md5_b  = _get_field(fi, 7, b"")
        img_url_b  = _get_field(fi, 8, b"")
        img_url = img_url_b.decode("utf-8") if isinstance(img_url_b, bytes) else str(img_url_b)
        img_md5 = img_md5_b.hex() if isinstance(img_md5_b, bytes) else ""
        if img_url:
            candidates.append({
                "img_class":  img_class if isinstance(img_class, int) else 0,
                "img_url":    img_url,
                "img_width":  img_width if isinstance(img_width, int) else 0,
                "img_height": img_height if isinstance(img_height, int) else 0,
                "img_md5":    img_md5,
            })

    if not candidates:
        return {"url": "", "width": hint_width, "height": hint_height,
                "md5": file_md5, "orig_size": file_size, "task_id": file_uuid or file_md5}

    # 选择：img_class=2（原图）> img_class=1（大图）> 第一个有 URL 的
    chosen = None
    for c in candidates:
        if c["img_class"] == 2:  # 原图优先
            chosen = c; break
    if chosen is None:
        for c in candidates:
            if c["img_class"] == 1:  # 大图次之
                chosen = c; break
    if chosen is None:
        chosen = candidates[0]

    width  = chosen["img_width"]  or hint_width
    height = chosen["img_height"] or hint_height
    md5    = chosen["img_md5"]    or file_md5

    return {
        "url":       chosen["img_url"],
        "width":     width,
        "height":    height,
        "md5":       md5,
        "orig_size": file_size,
        "task_id":   file_uuid or file_md5,
    }


def _parse_video_ext_info3(ext_info3: bytes, hint_width: int = 0,
                           hint_height: int = 0, hint_duration: int = 0,
                           file_uuid: str = "", file_md5: str = "") -> dict:
    """
    反序列化 ext_info3 (NTVideoUploadRspExtinfo protobuf)，提取视频信息。

    NTVideoUploadRspExtinfo:
      field 1 = string videoid    — 视频 ID（转码时使用）
      field 2 = string file_name  — 文件名
      field 3 = zigzag32 upload_retcode
      field 4 = string url        — 视频 URL
      field 100 = bytes echo_msg

    返回: {"video_id", "url", "width", "height", "duration", "file_uuid", "md5"}
    """
    default = {
        "video_id": file_uuid,
        "url":      "",
        "width":    hint_width,
        "height":   hint_height,
        "duration": hint_duration,
        "file_uuid": file_uuid,
        "md5":      file_md5,
    }
    if not ext_info3:
        return default

    fields = _parse_proto_fields(ext_info3)

    def _bytes_to_str(v):
        if isinstance(v, bytes):
            return v.decode("utf-8", errors="replace")
        return str(v) if v else ""

    # zigzag32 解码
    def _zigzag32(n):
        return (n >> 1) ^ -(n & 1)

    video_id = _bytes_to_str(_get_field(fields, 1, b""))
    url      = _bytes_to_str(_get_field(fields, 4, b""))
    retcode_raw = _get_field(fields, 3, 0)
    retcode = _zigzag32(retcode_raw) if isinstance(retcode_raw, int) else 0

    return {
        "video_id":  video_id or file_uuid,
        "url":       url,
        "width":     hint_width,
        "height":    hint_height,
        "duration":  hint_duration,
        "file_uuid": file_uuid,
        "md5":       file_md5,
        "retcode":   retcode,
    }


def _extract_video_cover(video_path: str) -> str:
    """
    用 ffmpeg 从视频第 0 秒提取封面帧，保存为临时 JPEG 文件，返回文件路径。
    失败时返回空字符串。
    """
    import subprocess, tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-ss", "0", "-vframes", "1",
             "-q:v", "2", tmp.name],
            capture_output=True, timeout=30,
        )
        if proc.returncode == 0 and os.path.getsize(tmp.name) > 0:
            return tmp.name
    except Exception:
        pass
    try:
        os.unlink(tmp.name)
    except Exception:
        pass
    return ""


def _upload_video_paths(video_paths: list, guild_id: int, channel_id: int,
                        on_error: str = "abort") -> tuple:
    """
    批量上传视频文件，返回 (uploaded_videos, error_or_None)。
    uploaded_videos: list of {"video_id", "url", "width", "height", "duration", "file_uuid", "md5"}
    """
    import upload_image as _uimg
    import base64 as _b64

    uploaded = []
    for i, entry in enumerate(video_paths):
        if isinstance(entry, str):
            entry = {"file_path": entry}
        fp = entry.get("file_path", "")
        if not fp:
            err = f"video_paths[{i}].file_path 为空"
            if on_error == "abort":
                return uploaded, err
            continue

        try:
            result = _uimg._run_upload(
                {
                    "guild_id":      entry.get("guild_id", guild_id),
                    "channel_id":    entry.get("channel_id", channel_id),
                    "file_path":     fp,
                    "business_type": 1003,  # BUSINESS_TYPE_VIDEO
                },
                business_type=1003,
            )
        except _uimg._DepsNotInstalled as exc:
            return uploaded, {"needs_confirm": True, "error": str(exc)}
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        if not result.get("success"):
            err = f"video_paths[{i}] ({fp}) 上传失败: {result.get('error', '未知错误')}"
            if on_error == "abort":
                return uploaded, err
            import sys as _sys
            print(f"[publish_feed] WARN: {err}", file=_sys.stderr)
            continue

        data = result["data"]
        file_uuid = data.get("file_uuid", "")
        ext_info3_raw = data.get("ext_info3") or ""
        ext_info3_bytes = _b64.b64decode(ext_info3_raw) if ext_info3_raw else b""
        video_info = _parse_video_ext_info3(
            ext_info3    = ext_info3_bytes,
            hint_width   = entry.get("width", 0),
            hint_height  = entry.get("height", 0),
            hint_duration = entry.get("duration", 0),
            file_uuid    = file_uuid,
            file_md5     = data.get("file_md5", ""),
        )

        # 提取视频封面帧并上传为图片（cover_url 是必填字段）
        cover_url = ""
        cover_path = _extract_video_cover(fp)
        if cover_path:
            try:
                cover_result = _uimg._run_upload(
                    {
                        "guild_id":      entry.get("guild_id", guild_id),
                        "channel_id":    entry.get("channel_id", channel_id),
                        "file_path":     cover_path,
                        "business_type": 1002,  # 图片/视频缩略图
                    },
                    business_type=1002,
                )
                if cover_result.get("success"):
                    cdata = cover_result["data"]
                    cover_ext_raw = cdata.get("ext_info3") or ""
                    cover_ext_bytes = _b64.b64decode(cover_ext_raw) if cover_ext_raw else b""
                    cover_img = _parse_ext_info3(cover_ext_bytes, file_uuid=cdata.get("file_uuid", ""),
                                                  file_md5=cdata.get("file_md5", ""),
                                                  file_size=cdata.get("file_size", 0))
                    cover_url = cover_img.get("url", "")
            except Exception:
                pass
            finally:
                import os as _os
                try:
                    _os.unlink(cover_path)
                except Exception:
                    pass

        video_info["cover_url"] = cover_url

        # 生成客户端临时 task_id（时间戳格式，与 json_feed.videos[].fileId 对应）
        import datetime as _dt
        now = _dt.datetime.now()
        import random as _random
        task_id = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}_{_random.randint(10000, 99999)}"
        video_info["task_id"] = task_id

        uploaded.append(video_info)

    return uploaded, None


def _upload_file_paths(file_paths: list, guild_id: int, channel_id: int,
                       on_error: str = "abort") -> tuple:
    """
    批量上传 file_paths 条目，返回 (uploaded_images, error_or_None)。
    uploaded_images: list，成功上传的 images-compatible 字典列表
    error: str 或 None
    """
    import upload_image as _uimg  # 同目录 lazy import

    uploaded = []
    for i, entry in enumerate(file_paths):
        # 兼容字符串格式（直接传文件路径字符串）
        if isinstance(entry, str):
            entry = {"file_path": entry}
        fp = entry.get("file_path", "")
        if not fp:
            err = f"file_paths[{i}].file_path 为空"
            if on_error == "abort":
                return uploaded, err
            continue

        try:
            result = _uimg._run_upload(
                {
                    "action":        "upload",
                    "guild_id":      entry.get("guild_id", guild_id),
                    "channel_id":    entry.get("channel_id", channel_id),
                    "file_path":     fp,
                    "width":         entry.get("width", 0),
                    "height":        entry.get("height", 0),
                    "business_type": 1002,
                },
                business_type=1002,
            )
        except _uimg._DepsNotInstalled as exc:
            return uploaded, {"needs_confirm": True, "error": str(exc)}
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        if not result.get("success"):
            err = f"file_paths[{i}] ({fp}) 上传失败: {result.get('error', '未知错误')}"
            if on_error == "abort":
                return uploaded, err
            import sys as _sys
            print(f"[publish_feed] WARN: {err}", file=_sys.stderr)
            continue

        data = result["data"]
        file_uuid = data.get("file_uuid", "")
        ext_info3_raw = data.get("ext_info3") or ""
        # upload_image.py 返回 base64 字符串，解码为 bytes
        import base64 as _b64
        ext_info3_bytes = _b64.b64decode(ext_info3_raw) if ext_info3_raw else b""
        uploaded.append(_parse_ext_info3(
            ext_info3  = ext_info3_bytes,
            hint_width  = entry.get("width", 0),
            hint_height = entry.get("height", 0),
            file_md5    = data.get("file_md5", ""),
            file_size   = data.get("file_size", 0),
            file_uuid   = file_uuid,
        ))

    return uploaded, None


def _build_at_nodes(at_users: list) -> list:
    """将 at_users 列表转换为 type=2 AT 节点列表（snake_case，对齐线上 key 风格）。"""
    nodes = []
    for u in (at_users or []):
        nodes.append({
            "type": 2,
            "at_content": {
                "user": {
                    "id":   str(u.get("id", "")),
                    "nick": u.get("nick", ""),
                },
                "type": 1,  # AT_TYPE_USER=1
            },
            "pattern_id": "",
        })
    return nodes


def _make_rich_text_contents(text: str, at_users: list = None) -> list:
    """将纯文本（含可选 at_users）转换为 StRichText.contents 数组，key 对齐线上 snake_case。
    at 节点在前，文本节点在后（有 at 时文本前补一个空格）。"""
    nodes = _build_at_nodes(at_users)
    if text:
        body = (" " + text) if nodes else text
        nodes.append({"type": 1, "text_content": {"text": body}, "pattern_id": ""})
    return nodes


def _make_rich_text_contents_multi(text: str, at_users: list = None) -> list:
    """
    将纯文本按 \\n 拆成多个 StRichText.contents 元素，与 patternInfo 的
    blockParagraph 块数保持一一对应，避免服务端构建 content_with_style 时
    因 contents 项数不足而产生大量空白段落。
    文本节点在前，at 节点追加在末尾，pattern_id 与 patternInfo type=3 节点的 id 对应。
    """
    paragraphs = text.split("\n") if text else [""]
    result = []
    for para in paragraphs:
        result.append({"type": 1, "text_content": {"text": para}, "pattern_id": ""})
    # AT 节点追加在末尾，pattern_id 从 "1" 递增，与 patternInfo type=3 节点的 id 对应
    for i, u in enumerate(at_users or [], start=1):
        result.append({
            "type": 2,
            "at_content": {
                "user": {
                    "id":   str(u.get("id", "")),
                    "nick": u.get("nick", ""),
                },
                "type": 1,
            },
            "pattern_id": str(i),
        })
    return result


def _make_pattern_info_long(content: str, images: list, videos: list = None,
                            at_users: list = None) -> str:
    """
    生成长贴(feed_type=2)的 patternInfo JSON 字符串。
    AT节点(type=3)在末段，图片(type=6)和视频(type=7)节点追加在末段。
    """
    if videos is None:
        videos = []
    if at_users is None:
        at_users = []
    paragraphs = content.split("\n") if content else [""]
    ts_ms = int(time.time() * 1000)

    blocks = [
        {
            "id": "",
            "type": "blockParagraph",
            "data": [{"type": 1, "text": "", "children": [], "status": 0, "width": 0, "height": 0, "duration": 0, "widthPercent": 0}]
        }
    ]
    for i, para in enumerate(paragraphs):
        block_data = [
            {
                "type": 1,
                "text": para,
                "props": {"fontWeight": 400, "italic": False, "underline": False}
            }
        ]
        # 末段追加 AT 节点 type=3、图片节点 type=6 和视频节点 type=7
        if i == len(paragraphs) - 1:
            # AT 节点 type=3
            for j, u in enumerate(at_users, start=1):
                block_data.append({
                    "user": {"id": str(u.get("id", "")), "nick": u.get("nick", "")},
                    "id": str(j),
                    "status": 0, "widthPercent": 0,
                    "type": 3,
                    "height": 0, "duration": 0, "width": 0,
                })
            for idx, img in enumerate(images):
                pic_id = img.get("task_id") or img.get("md5", str(ts_ms))
                block_data.append({
                    "type": 6,
                    "width":        img.get("width", 0),
                    "height":       img.get("height", 0),
                    "widthPercent": 100,
                    "fileId":       pic_id,
                    "url":          img["url"],
                    "id":           str(idx + 1),
                    "taskId":       pic_id,
                    "status":       0,
                    "duration":     0,
                })
            for idx, v in enumerate(videos):
                vid_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", "")
                block_data.append({
                    "type": 7,
                    "width":        v.get("width", 0),
                    "height":       v.get("height", 0),
                    "widthPercent": 100,
                    "fileId":       vid_id,
                    "videoId":      vid_id,
                    "taskId":       vid_id,
                    "url":          v.get("url", ""),
                    "id":           str(idx + 1),
                    "status":       0,
                    "duration":     v.get("duration", 0),
                })
            block_data.append({
                "type": 11, "status": 0, "widthPercent": 0,
                "height": 0, "duration": 0, "width": 0,
            })
        blocks.append({
            "id": str(ts_ms + i),
            "type": "blockParagraph",
            "props": {"textAlignment": 0},
            "data": block_data,
        })
    return json.dumps(blocks, ensure_ascii=False)


def _make_pattern_info_short(content: str, images: list, videos: list = None,
                             at_users: list = None) -> str:
    """
    生成短贴(feed_type=1)的 patternInfo JSON 字符串。
    AT节点(type=3)在第二个 blockParagraph 中，图片节点 type=6，视频节点 type=7，各单独一个 blockParagraph。
    """
    import uuid
    if videos is None:
        videos = []
    if at_users is None:
        at_users = []
    blocks = [
        {
            "id": str(uuid.uuid4()).upper(),
            "type": "blockParagraph",
            "data": [{"status": 0, "widthPercent": 0, "type": 1, "text": "",
                       "height": 0, "duration": 0, "width": 0}]
        },
    ]
    # 第二个 blockParagraph：文本占位 + AT 节点 + type=11 结束节点
    data2 = [
        {"props": {"textAlignment": 0}, "status": 0, "widthPercent": 0,
         "type": 1, "height": 0, "duration": 0, "width": 0},
    ]
    for j, u in enumerate(at_users, start=1):
        data2.append({
            "user": {"id": str(u.get("id", "")), "nick": u.get("nick", "")},
            "id": str(j),
            "status": 0, "widthPercent": 0,
            "type": 3,
            "height": 0, "duration": 0, "width": 0,
        })
    data2.append({"status": 0, "widthPercent": 0, "type": 11,
                  "height": 0, "duration": 0, "width": 0})
    blocks.append({
        "id": str(uuid.uuid4()).upper(),
        "props": {"textAlignment": 0},
        "type": "blockParagraph",
        "data": data2,
    })
    # 图片节点 type=6
    for idx, img in enumerate(images):
        pic_id = img.get("task_id") or img.get("md5", "")
        blocks.append({
            "id": str(uuid.uuid4()).upper(),
            "props": {"textAlignment": 0},
            "type": "blockParagraph",
            "data": [
                {
                    "taskId":       pic_id,
                    "id":           str(idx + 1),
                    "fileId":       pic_id,
                    "status":       0,
                    "widthPercent": 100,
                    "type":         6,
                    "height":       img.get("height", 0),
                    "duration":     0,
                    "width":        img.get("width", 0),
                },
                {"status": 0, "widthPercent": 0, "type": 11,
                 "height": 0, "duration": 0, "width": 0},
            ]
        })
    # 视频节点 type=7
    for idx, v in enumerate(videos):
        task_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", "")
        blocks.append({
            "id": str(uuid.uuid4()).upper(),
            "props": {"textAlignment": 0},
            "type": "blockParagraph",
            "data": [
                {
                    "taskId":       task_id,
                    "id":           str(idx + 1),
                    "fileId":       task_id,
                    "videoId":      task_id,
                    "status":       0,
                    "widthPercent": 100,
                    "type":         7,
                    "height":       v.get("height", 0),
                    "duration":     v.get("duration", 0),
                    "width":        v.get("width", 0),
                },
                {"status": 0, "widthPercent": 0, "type": 11,
                 "height": 0, "duration": 0, "width": 0},
            ]
        })
    return json.dumps(blocks, ensure_ascii=False)


def _build_feed_business_param(feed_id: str) -> str:
    """
    将 feed_id 编码为 get_share_url MCP 工具所需的 businessParam（base64 protobuf）。
    逻辑来自 share-guild-v1/read/get_share_url.py。
    """
    import base64, binascii, struct

    FEED_ID_PREFIX   = "B_"
    APP_ID_FLAG      = "0X"
    BUSINESS_TYPE_FEED = 2

    if not feed_id.startswith(FEED_ID_PREFIX) or len(feed_id) < 24:
        raise ValueError(f"feed_id 不合法: {feed_id}")

    hex_part = feed_id[len(FEED_ID_PREFIX): len(FEED_ID_PREFIX) + 16]
    decoded  = binascii.unhexlify(hex_part)
    create_time = struct.unpack("<I", decoded[:4])[0]

    tail = feed_id[len(FEED_ID_PREFIX) + 16:]
    pos  = tail.find(APP_ID_FLAG)
    poster_text = tail[:pos] if pos != -1 else tail
    poster_tiny_id = int(poster_text, 10)

    def _varint(v: int) -> bytes:
        out = bytearray()
        while True:
            bits = v & 0x7F; v >>= 7
            out.append(bits | 0x80 if v else bits)
            if not v: break
        return bytes(out)

    def _field_varint(fn, v):  return _varint((fn << 3) | 0) + _varint(v)
    def _field_bytes(fn, b):   return _varint((fn << 3) | 2) + _varint(len(b)) + b
    def _field_string(fn, s):  return _field_bytes(fn, s.encode("utf-8"))

    feed_param = (
        _field_string(1, feed_id) +
        _field_varint(2, create_time) +
        _field_varint(3, poster_tiny_id)
    )
    business_param = (
        _field_varint(1, BUSINESS_TYPE_FEED) +
        _field_bytes(2, feed_param)
    )
    return base64.b64encode(business_param).decode("ascii")


def _get_share_url(guild_id: str, channel_id: str, feed_id: str) -> str:
    """发帖成功后通过 MCP 调用 get_share_url 获取帖子短链，失败时返回空字符串。"""
    try:
        business_param = _build_feed_business_param(feed_id)
        # MCP 工具需要 camelCase，_mcp_client 会自动转换
        result = call_mcp("get_share_url", {
            "guild_id":      guild_id,
            "channel_id":    channel_id,
            "business_param": business_param,
            "is_short_link": True,
        })
        structured = result.get("structuredContent") or {}
        url = structured.get("url", "")
        if not url:
            for item in result.get("content", []):
                text = item.get("text", "")
                if "url" in text:
                    import re
                    m = re.search(r'"url"\s*:\s*"([^"]+)"', text)
                    if m:
                        url = m.group(1)
                        break
        return url
    except Exception:
        return ""


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
      - images[].pattern_id 与 patternInfo 中 type=6 节点的 id 字段一一对应（使用 "1","2",... 递增序号）
      - images[].picUrl 短贴时填本地占位路径，长贴时留空；CDN URL 通过 client_content 传递
    """
    from _skill_runner import validate_required
    err = validate_required(params, SKILL_MANIFEST)
    if err:
        return err

    guild_id   = params.get("guild_id") or 0
    channel_id = params.get("channel_id") or 0
    title      = params.get("title", "")
    content    = params.get("content", "")
    images     = params.get("images", [])
    feed_type  = params.get("feed_type", 1)
    on_error   = params.get("on_upload_error", "abort")
    at_users   = params.get("at_users") or []

    if "image_paths" in params and "file_paths" not in params:
        return {"success": False, "error": (
            "参数名错误：应为 file_paths（不是 image_paths）。"
            "请将本地图片路径列表传入 file_paths 参数。"
        )}

    video_paths = params.get("video_paths", [])
    file_paths  = params.get("file_paths", [])

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
        # 检查 ffmpeg（视频帖需要提取封面帧）
        if video_paths:
            import shutil as _shutil
            if not _shutil.which("ffmpeg"):
                return {"success": False, "error": (
                    "发布视频帖需要 ffmpeg，但未找到该命令。\n"
                    "请先安装 ffmpeg：\n"
                    "  macOS:  brew install ffmpeg\n"
                    "  Ubuntu: sudo apt install ffmpeg"
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
    import uuid
    client_task_id = str(uuid.uuid4()).upper()

    # 选择 patternInfo 生成方式
    if feed_type == 1:
        pattern_info = _make_pattern_info_short(content, images, videos, at_users)
    else:
        pattern_info = _make_pattern_info_long(content, images, videos, at_users)

    # images[] 数组：pattern_id 使用递增序号 "1","2",...
    # 短贴时 picUrl 填本地占位路径（对齐线上客户端），长贴时留空
    json_images = []
    for i, img in enumerate(images):
        task_id = img.get("task_id") or img.get("md5", "")
        json_images.append({
            "picId":          task_id,
            "picUrl":         "/guildFeedPublish/localMedia/%s/%s/thumb.jpg" % (client_task_id, task_id) if feed_type == 1 else "",
            "pattern_id":     str(i + 1),
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
            "contents": _make_rich_text_contents(title) if title else []
        },
        "contents": {
            # 长贴按换行拆分，与 patternInfo 的 blockParagraph 块数一一对应，
            # 避免服务端构建 content_with_style 时因 contents 项数不足产生空白段落
            "contents": _make_rich_text_contents_multi(content, at_users) if (content or at_users) and feed_type == 2 else (
                _make_rich_text_contents(content, at_users) if (content or at_users) else []
            )
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
                    "picUrl":         "/guildFeedPublish/localMedia%s/%s/thumb_%s.jpg" % (
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

    # client_content：图片 + 视频 CDN 信息
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
            import re as _re
            raw = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "")
            m = _re.search(r":\s*(\d+)\s*$", raw)
            code = m.group(1) if m else ""
            err = f"发帖失败（错误码 {code}）" if code else (raw or "发帖失败")
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
        # 作者身份模式（guild_id=0）也尝试获取，_get_share_url 内部失败时返回空字符串
        share_url = ""
        if feed_id:
            share_url = _get_share_url(
                guild_id=str(guild_id),
                channel_id=str(channel_id),
                feed_id=feed_id,
            )

        # 构建可读性高的返回结果
        feed_type_label = "短贴（无标题）" if feed_type == 1 else "长贴（有标题）"
        result_data = {
            "帖子ID":   feed_id,
            "帖子类型": feed_type_label,
        }
        # 作者身份全局发帖模式标记
        if not guild_id and not channel_id:
            result_data["发帖模式"] = "作者身份（全局发帖）"

        # 尝试格式化发表时间
        raw_time = feed_resp.get("create_time") or feed_resp.get("createTime")
        if raw_time:
            import datetime
            try:
                dt = datetime.datetime.fromtimestamp(int(raw_time))
                result_data["发表时间"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                result_data["发表时间"] = str(raw_time)

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
        return {"success": False, "error": f"发帖时发生异常：{e}"}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
