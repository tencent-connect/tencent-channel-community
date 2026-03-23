"""
Skill: alter_feed
描述: 修改已有帖子的标题或正文内容，支持替换/删除图片和视频
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）
"""

import json
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _mcp_client import call_mcp, get_feed_share_url

TOOL_NAME = "alter_feed"  # 服务端实际注册的 MCP tool name

SKILL_MANIFEST = {
    "name": "alter-feed",
    "description": (
        "修改腾讯频道（QQ Channel）已有帖子的标题或正文内容，需提供帖子ID、帖子发表时间、频道ID和板块ID。"
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
                "type": "integer",
                "description": "帖子发表时间（秒级时间戳），uint64，必填"
            },
            "guild_id": {
                "type": "integer",
                "description": "频道ID，uint64，必填"
            },
            "channel_id": {
                "type": "integer",
                "description": "板块（子频道）ID，uint64，必填"
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


# ── 从 publish_feed.py 复制的上传/patternInfo 工具函数 ──────────────────────

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
    """解析 protobuf 字节流，返回 {field_num: value_or_list}。"""
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
            break
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
    val = fields.get(field_num, default)
    if isinstance(val, list):
        return val[-1]
    return val


def _parse_ext_info3(ext_info3: bytes, hint_width: int = 0,
                     hint_height: int = 0, file_md5: str = "",
                     file_size: int = 0, file_uuid: str = "") -> dict:
    """反序列化图片上传响应 ext_info3，提取 CDN URL。"""
    if not ext_info3:
        return {"url": "", "width": hint_width, "height": hint_height,
                "md5": file_md5, "orig_size": file_size, "task_id": file_uuid or file_md5}

    root = _parse_proto_fields(ext_info3)
    img_infos_raw = root.get(2)
    if img_infos_raw is None:
        img_infos_raw = []
    elif isinstance(img_infos_raw, bytes):
        img_infos_raw = [img_infos_raw]

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

    chosen = None
    for c in candidates:
        if c["img_class"] == 2:
            chosen = c; break
    if chosen is None:
        for c in candidates:
            if c["img_class"] == 1:
                chosen = c; break
    if chosen is None:
        chosen = candidates[0]

    return {
        "url":       chosen["img_url"],
        "width":     chosen["img_width"]  or hint_width,
        "height":    chosen["img_height"] or hint_height,
        "md5":       chosen["img_md5"]    or file_md5,
        "orig_size": file_size,
        "task_id":   file_uuid or file_md5,
    }


def _parse_video_ext_info3(ext_info3: bytes, hint_width: int = 0,
                           hint_height: int = 0, hint_duration: int = 0,
                           file_uuid: str = "", file_md5: str = "") -> dict:
    """反序列化视频上传响应 ext_info3，提取视频信息。"""
    default = {
        "video_id": file_uuid, "url": "",
        "width": hint_width, "height": hint_height, "duration": hint_duration,
        "file_uuid": file_uuid, "md5": file_md5,
    }
    if not ext_info3:
        return default

    fields = _parse_proto_fields(ext_info3)

    def _bytes_to_str(v):
        if isinstance(v, bytes):
            return v.decode("utf-8", errors="replace")
        return str(v) if v else ""

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
    """用 ffmpeg 提取视频封面帧，失败返回空字符串。"""
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


def _upload_file_paths(file_paths: list, guild_id: int, channel_id: int,
                       on_error: str = "abort") -> tuple:
    """批量上传本地图片，返回 (uploaded_images, error_or_None)。"""
    import upload_image as _uimg

    uploaded = []
    for i, entry in enumerate(file_paths):
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
            print(f"[alter_feed] WARN: {err}", file=_sys.stderr)
            continue

        data = result["data"]
        file_uuid = data.get("file_uuid", "")
        ext_info3_raw = data.get("ext_info3") or ""
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


def _upload_video_paths(video_paths: list, guild_id: int, channel_id: int,
                        on_error: str = "abort") -> tuple:
    """批量上传本地视频，返回 (uploaded_videos, error_or_None)。"""
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
                    "business_type": 1003,
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
            print(f"[alter_feed] WARN: {err}", file=_sys.stderr)
            continue

        data = result["data"]
        file_uuid = data.get("file_uuid", "")
        ext_info3_raw = data.get("ext_info3") or ""
        ext_info3_bytes = _b64.b64decode(ext_info3_raw) if ext_info3_raw else b""
        video_info = _parse_video_ext_info3(
            ext_info3     = ext_info3_bytes,
            hint_width    = entry.get("width", 0),
            hint_height   = entry.get("height", 0),
            hint_duration = entry.get("duration", 0),
            file_uuid     = file_uuid,
            file_md5      = data.get("file_md5", ""),
        )

        # 提取视频封面帧并上传为图片
        cover_url = ""
        cover_path = _extract_video_cover(fp)
        if cover_path:
            try:
                cover_result = _uimg._run_upload(
                    {
                        "guild_id":      entry.get("guild_id", guild_id),
                        "channel_id":    entry.get("channel_id", channel_id),
                        "file_path":     cover_path,
                        "business_type": 1002,
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

        import datetime as _dt, random as _random
        now = _dt.datetime.now()
        task_id = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}_{_random.randint(10000, 99999)}"
        video_info["task_id"] = task_id

        uploaded.append(video_info)

    return uploaded, None


# ── patternInfo 生成（含图片/视频节点，对齐 publish_feed） ──────────────────

def _make_pattern_info_long(content: str, at_users: list, images: list, videos: list) -> str:
    """
    生成长贴(feed_type=2)的 patternInfo JSON。
    AT节点(type=3)在末段，图片节点(type=6)、视频节点(type=7)追加在末段。
    """
    import time as _time
    ts_ms = int(_time.time() * 1000)

    paragraphs = content.split("\n") if content else [""]
    blocks = [
        {
            "id": str(uuid.uuid4()).upper(),
            "type": "blockParagraph",
            "data": [{"status": 0, "widthPercent": 0, "type": 1, "text": "",
                      "height": 0, "duration": 0, "width": 0}],
        }
    ]
    for i, para in enumerate(paragraphs):
        block_data = [
            {
                "type": 1,
                "text": para,
                "props": {"fontWeight": 400, "italic": False, "underline": False},
            }
        ]
        if i == len(paragraphs) - 1:
            # AT节点
            for j, u in enumerate(at_users or [], start=1):
                block_data.append({
                    "user": {"id": str(u.get("id", "")), "nick": u.get("nick", "")},
                    "id": str(j),
                    "status": 0, "widthPercent": 0,
                    "type": 3,
                    "height": 0, "duration": 0, "width": 0,
                })
            # 图片节点 type=6
            for idx, img in enumerate(images or []):
                pic_id = img.get("task_id") or img.get("md5", str(ts_ms))
                block_data.append({
                    "type": 6,
                    "width":        img.get("width", 0),
                    "height":       img.get("height", 0),
                    "widthPercent": 100,
                    "fileId":       pic_id,
                    "url":          img.get("url", img.get("picUrl", "")),
                    "id":           str(idx + 1),
                    "taskId":       pic_id,
                    "status":       0,
                    "duration":     0,
                })
            # 视频节点 type=7
            for idx, v in enumerate(videos or []):
                vid_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", v.get("fileId", ""))
                block_data.append({
                    "type": 7,
                    "width":        v.get("width", 0),
                    "height":       v.get("height", 0),
                    "widthPercent": 100,
                    "fileId":       vid_id,
                    "videoId":      vid_id,
                    "taskId":       vid_id,
                    "url":          v.get("url", v.get("playUrl", "")),
                    "id":           str(idx + 1),
                    "status":       0,
                    "duration":     v.get("duration", 0),
                })
            block_data.append({"status": 0, "widthPercent": 0, "type": 11,
                               "height": 0, "duration": 0, "width": 0})
        blocks.append({
            "id": str(ts_ms + i),
            "props": {"textAlignment": 0},
            "type": "blockParagraph",
            "data": block_data,
        })
    return json.dumps(blocks, ensure_ascii=False)


def _make_pattern_info_short(content: str, at_users: list, images: list, videos: list) -> str:
    """
    生成短贴(feed_type=1)的 patternInfo JSON。
    图片节点 type=6，视频节点 type=7，各独立 blockParagraph。
    """
    block1 = {
        "id": str(uuid.uuid4()).upper(),
        "type": "blockParagraph",
        "data": [{"status": 0, "widthPercent": 0, "type": 1, "text": "",
                  "height": 0, "duration": 0, "width": 0}],
    }
    data2 = [{"props": {"textAlignment": 0}, "status": 0, "widthPercent": 0,
               "type": 1, "height": 0, "duration": 0, "width": 0}]
    for i, u in enumerate(at_users or [], start=1):
        data2.append({
            "user": {"id": str(u.get("id", "")), "nick": u.get("nick", "")},
            "id": str(i),
            "status": 0, "widthPercent": 0,
            "type": 3,
            "height": 0, "duration": 0, "width": 0,
        })
    data2.append({"status": 0, "widthPercent": 0, "type": 11,
                   "height": 0, "duration": 0, "width": 0})
    block2 = {
        "id": str(uuid.uuid4()).upper(),
        "props": {"textAlignment": 0},
        "type": "blockParagraph",
        "data": data2,
    }
    blocks = [block1, block2]

    # 图片节点 type=6，每张独立 blockParagraph
    for idx, img in enumerate(images or []):
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

    # 视频节点 type=7，每个独立 blockParagraph
    for idx, v in enumerate(videos or []):
        task_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", v.get("fileId", ""))
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


def _make_contents(text: str, at_users: list, feed_type: int = 1) -> list:
    """
    构造 jsonFeed.contents.contents 数组（对齐线上改帖抓包）。
    顺序：文本节点在前，at 节点在后（与发帖/评论的 at 在前不同）。
    at 节点携带 pattern_id（从 "1" 递增），与 patternInfo 里 type=3 节点的 id 对应。

    短贴(feed_type=1)：单个文本节点 + AT 节点列表。
    长贴(feed_type=2)：按 \\n 拆分为多个文本节点（与 patternInfo blockParagraph 对应），
                      AT 节点追加在最后一个文本节点之后。
    """
    if feed_type == 2:
        paragraphs = text.split("\n") if text else [""]
        nodes = []
        for para in paragraphs:
            nodes.append({"text_content": {"text": para}, "type": 1, "pattern_id": ""})
        for i, u in enumerate(at_users or [], start=1):
            nodes.append({
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
        return nodes
    else:
        nodes = []
        if text:
            nodes.append({"text_content": {"text": text}, "type": 1, "pattern_id": ""})
        for i, u in enumerate(at_users or [], start=1):
            nodes.append({
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
        return nodes


def _normalize_orig_images(images: list, client_task_id: str, feed_type: int) -> list:
    """
    将原帖透传的图片结构（仅含 picUrl/width/height）规范化为 alter_feed json_feed.images 所需结构。
    与 _build_json_images 逻辑相同，但 picId 从 picUrl hash 派生，避免空 picId。
    """
    import hashlib
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
            "pattern_id":      str(i + 1),
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
            "pattern_id":      str(i + 1),
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
            "/guildFeedPublish/localMedia%s/%s/thumb_%s.jpg" % (
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
        import hashlib as _hashlib
        final_images = []
        for img in orig_images:
            img = dict(img)  # 浅拷贝，避免修改原始数据
            if not img.get("task_id") and not img.get("md5"):
                pic_id = img.get("picId", "")
                if pic_id:
                    img["task_id"] = pic_id
                else:
                    pic_url = img.get("url", img.get("picUrl", ""))
                    img["task_id"] = _hashlib.md5(pic_url.encode()).hexdigest()[:16] if pic_url else ""
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
    if feed_type == 2:
        pattern_info = _make_pattern_info_long(content, at_users, final_images, final_videos)
    else:
        pattern_info = _make_pattern_info_short(content, at_users, final_images, final_videos)

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
        "contents": {"contents": _make_contents(content, at_users, feed_type)},
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

    # client_content：新上传图片/视频的 CDN 信息（原帖透传时不需要）
    arguments: dict = {
        "feed":      {},
        "json_feed": json.dumps(json_feed_obj, ensure_ascii=False),
    }
    if has_new_images or has_new_videos:
        client_content: dict = {}
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
        structured = result.get("structuredContent") or {}
        ret_code = structured.get("_meta", {}).get("AdditionalFields", {}).get("retCode", 0)
        if ret_code != 0:
            ret_msg = structured.get("_meta", {}).get("AdditionalFields", {}).get("retMsg", "") or str(ret_code)
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
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
