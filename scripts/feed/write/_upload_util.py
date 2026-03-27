"""
_upload_util.py — 媒体上传共享工具函数

供 publish_feed.py 和 alter_feed.py 共同使用，避免代码重复。
包含：
  - protobuf 解析（_decode_varint / _parse_proto_fields / _get_field）
  - 上传响应解析（_parse_ext_info3 / _parse_video_ext_info3）
  - ffmpeg 管理（_ensure_ffmpeg / _extract_video_cover）
  - 批量上传（_upload_file_paths / _upload_video_paths）
"""

import sys


# ── Protobuf 工具 ──────────────────────────────────────────────────────────────

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


# ── 上传响应解析 ───────────────────────────────────────────────────────────────

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

    选择策略：仅使用 channelr.photo.store.qq.com 域名的条目，优先取 img_class=2（原图），其次 img_class=1（大图），最后取任意符合条件的。
    无符合条件的条目时返回空 url。
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

    # 只有 channelr.photo.store.qq.com 是可公开访问的图片 CDN 域名。
    # multimedia.nt.qq.com.cn 等为 NT 协议内网临时地址，外网不可访问，严禁使用。
    _CDN_HOST = "channelr.photo.store.qq.com"
    candidates = [c for c in candidates if _CDN_HOST in c["img_url"]]
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

    返回: {"video_id", "url", "width", "height", "duration", "file_uuid", "md5", "retcode"}
    """
    default = {
        "video_id": file_uuid,  # fallback 到 file_uuid，便于 task_id 追踪
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
        "video_id":  video_id,
        "url":       url,
        "width":     hint_width,
        "height":    hint_height,
        "duration":  hint_duration,
        "file_uuid": file_uuid,
        "md5":       file_md5,
        "retcode":   retcode,
    }


# ── ffmpeg 管理 ────────────────────────────────────────────────────────────────

def _ensure_ffmpeg() -> bool:
    """检测 ffmpeg 是否可用，不可用时尝试自动安装。返回是否可用。
    - macOS：brew install ffmpeg
    - Linux：sudo apt-get install -y ffmpeg
    - Windows：winget install ffmpeg（需 winget 可用）
    """
    import shutil, subprocess, platform

    if shutil.which("ffmpeg"):
        return True

    system = platform.system().lower()
    print("[media_upload] ffmpeg 未找到，尝试自动安装...", file=sys.stderr)

    install_cmds = {
        "darwin":  ["brew", "install", "ffmpeg"],
        "linux":   ["sudo", "apt-get", "install", "-y", "ffmpeg"],
        "windows": ["winget", "install", "--id", "Gyan.FFmpeg", "-e",
                    "--accept-source-agreements", "--accept-package-agreements"],
    }
    cmd = install_cmds.get(system)
    if not cmd:
        print(f"[media_upload] 不支持的平台 ({system})，请手动安装 ffmpeg", file=sys.stderr)
        return False

    if system == "linux":
        try:
            subprocess.run(["sudo", "apt-get", "update", "-y"],
                           capture_output=True, timeout=120)
        except Exception:
            pass

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
        if proc.returncode == 0 and shutil.which("ffmpeg"):
            print("[media_upload] ffmpeg 安装成功", file=sys.stderr)
            return True
        else:
            stderr_text = proc.stderr.decode("utf-8", errors="replace")[:500] if proc.stderr else ""
            print(f"[media_upload] ffmpeg 安装失败 (returncode={proc.returncode}): {stderr_text}",
                  file=sys.stderr)
            return False
    except FileNotFoundError:
        fallback = {
            "darwin":  "请先安装 Homebrew (https://brew.sh)，然后运行: brew install ffmpeg",
            "linux":   "请运行: sudo apt-get install -y ffmpeg",
            "windows": "请从 https://ffmpeg.org/download.html 下载安装，或运行: choco install ffmpeg",
        }
        print(f"[media_upload] 自动安装失败，{fallback.get(system, '请手动安装 ffmpeg')}",
              file=sys.stderr)
        return False
    except Exception as e:
        print(f"[media_upload] ffmpeg 安装异常: {e}", file=sys.stderr)
        return False


def _extract_video_cover(video_path: str) -> str:
    """用 ffmpeg 提取视频封面帧，ffmpeg 不存在时尝试自动安装。失败返回空字符串。"""
    import subprocess, tempfile, os

    if not _ensure_ffmpeg():
        return ""

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


# ── 字数计算 ───────────────────────────────────────────────────────────────────

def _calculate_content_length(text: str) -> float:
    """
    计算文本的加权字数，与服务端 CalculateContentLength 规则一致：
      - 汉字 / 中文标点 / 全角符号 = 1 字
      - 英文字母 / 数字 / 半角符号  = 0.5 字
    判断依据：Unicode 码点 > 0x7F 视为中文系字符（含中日韩、全角、表情等）。
    """
    total = 0.0
    for ch in text:
        total += 1.0 if ord(ch) > 0x7F else 0.5
    return total


# ── 批量上传 ───────────────────────────────────────────────────────────────────

def _upload_file_paths(file_paths: list, guild_id: int, channel_id: int,
                       on_error: str = "abort") -> tuple:
    """
    批量上传 file_paths 条目，返回 (uploaded_images, error_or_None)。
    uploaded_images: list，成功上传的 images-compatible 字典列表
    error: str 或 None
    """
    import upload_image as _uimg  # 同目录 lazy import
    import base64 as _b64

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
            print(f"[media_upload] WARN: {err}", file=sys.stderr)
            continue

        data = result["data"]
        file_uuid = data.get("file_uuid", "")
        ext_info3_raw = data.get("ext_info3") or ""
        ext_info3_bytes = _b64.b64decode(ext_info3_raw) if ext_info3_raw else b""
        uploaded.append(_parse_ext_info3(
            ext_info3   = ext_info3_bytes,
            hint_width  = entry.get("width", 0),
            hint_height = entry.get("height", 0),
            file_md5    = data.get("file_md5", ""),
            file_size   = data.get("file_size", 0),
            file_uuid   = file_uuid,
        ))

    return uploaded, None


def _upload_video_paths(video_paths: list, guild_id: int, channel_id: int,
                        on_error: str = "abort") -> tuple:
    """
    批量上传视频文件，返回 (uploaded_videos, error_or_None)。
    uploaded_videos: list of {"video_id", "url", "width", "height", "duration",
                               "file_uuid", "md5", "cover_url", "task_id"}
    """
    import upload_image as _uimg
    import base64 as _b64
    import datetime as _dt, random as _random

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
            print(f"[media_upload] WARN: {err}", file=sys.stderr)
            continue

        data = result["data"]
        file_uuid = data.get("file_uuid", "")
        ext_info3_raw = data.get("ext_info3") or ""
        ext_info3_bytes = _b64.b64decode(ext_info3_raw) if ext_info3_raw else b""

        # 用 ffprobe 探测视频真实宽高和时长，优于用户手动传入的 hint（通常为 0）
        hint_width    = entry.get("width", 0)
        hint_height   = entry.get("height", 0)
        # 用户传入的 duration 单位为秒，内部统一转为毫秒后传给服务端
        hint_duration = int(entry.get("duration", 0) or 0) * 1000
        try:
            import subprocess as _sp, json as _json
            probe = _sp.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_entries",
                 "stream=width,height,codec_type,duration:stream_tags=rotate:stream_side_data",
                 fp],
                capture_output=True, text=True, timeout=10,
            )
            if probe.returncode == 0:
                video_stream = next(
                    (s for s in _json.loads(probe.stdout).get("streams", [])
                     if s.get("codec_type") == "video"),
                    None,
                )
                if video_stream:
                    w = video_stream.get("width", 0)  or hint_width
                    h = video_stream.get("height", 0) or hint_height
                    hint_duration = int(float(video_stream.get("duration", 0) or 0) * 1000) or hint_duration

                    # 检查旋转角度：手机竖拍视频通常编码为横向 + rotate=90/270，
                    # 需要交换宽高才能得到正确的显示分辨率。
                    _rotate = 0
                    # 来源1：tags.rotate（旧版 ffprobe）
                    _tags = video_stream.get("tags") or {}
                    try:
                        _rotate = int(_tags.get("rotate", 0) or 0)
                    except (ValueError, TypeError):
                        _rotate = 0
                    # 来源2：side_data_list 中的 displaymatrix（新版 ffprobe）
                    if _rotate == 0:
                        for _sd in (video_stream.get("side_data_list") or []):
                            if _sd.get("side_data_type") == "Display Matrix":
                                try:
                                    _rotate = int(_sd.get("rotation", 0) or 0)
                                except (ValueError, TypeError):
                                    pass
                                break
                    # ±90° / ±270° 需要交换宽高
                    if abs(_rotate) in (90, 270):
                        w, h = h, w

                    hint_width  = w
                    hint_height = h
        except Exception:
            pass  # 探测失败时继续使用用户传入的 hint

        video_info = _parse_video_ext_info3(
            ext_info3     = ext_info3_bytes,
            hint_width    = hint_width,
            hint_height   = hint_height,
            hint_duration = hint_duration,
            file_uuid     = file_uuid,
            file_md5      = data.get("file_md5", ""),
        )

        if not video_info.get("video_id"):
            err = f"video_paths[{i}] ({fp}) 上传失败：服务端未返回 video_id，请重试"
            if on_error == "abort":
                return uploaded, err
            print(f"[media_upload] WARN: {err}", file=sys.stderr)
            continue

        # 提取视频封面帧并上传为图片（cover_url 是必填字段）
        cover_url = ""
        # 优先使用用户指定的封面路径，否则从视频自动提取
        cover_source = entry.get("cover_path") or _extract_video_cover(fp)
        if cover_source:
            try:
                cover_result = _uimg._run_upload(
                    {
                        "guild_id":      entry.get("guild_id", guild_id),
                        "channel_id":    entry.get("channel_id", channel_id),
                        "file_path":     cover_source,
                        "business_type": 1002,  # 图片/视频缩略图
                    },
                    business_type=1002,
                )
                if cover_result.get("success"):
                    cdata = cover_result["data"]
                    cover_ext_raw = cdata.get("ext_info3") or ""
                    cover_ext_bytes = _b64.b64decode(cover_ext_raw) if cover_ext_raw else b""
                    cover_img = _parse_ext_info3(cover_ext_bytes,
                                                 file_uuid=cdata.get("file_uuid", ""),
                                                 file_md5=cdata.get("file_md5", ""),
                                                 file_size=cdata.get("file_size", 0))
                    cover_url = cover_img.get("url", "")
            except Exception:
                pass
            finally:
                # 仅删除自动提取的临时文件，用户指定的封面文件不删除
                if not entry.get("cover_path") and cover_source:
                    import os as _os
                    try:
                        _os.unlink(cover_source)
                    except Exception:
                        pass

        video_info["cover_url"] = cover_url

        # 生成客户端临时 task_id（时间戳格式，与 json_feed.videos[].fileId 对应）
        now = _dt.datetime.now()
        task_id = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}_{_random.randint(10000, 99999)}"
        video_info["task_id"] = task_id

        uploaded.append(video_info)

    return uploaded, None
