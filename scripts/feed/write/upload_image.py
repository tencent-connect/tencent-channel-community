"""
Skill: upload_image
描述: 频道帖子富媒体图片/视频上传完整流程（申请上传 → 分片上传 → 状态同步）
MCP 服务: trpc.group_pro.open_platform_agent_mcp.GuildDisegtSvr

鉴权：get_token() → .env → mcporter（与频道 manage 相同，见 scripts/manage/common.py）。

⚠️  调用前必读：references/feed-reference.md
    包含内容长度限制、拆分规则、正确调用流程等关键说明。
    禁止仅凭此脚本推断用法。

上传完整流程（已验证）：
    1. apply_media_upload  — 申请上传，获取 ukey + 上传服务器地址（支持秒传）
    2. POST /sliceupload   — 使用 protobuf 格式分片上传文件数据（Content-Type: application/protobuf）
    3. apply_media_upload_status_sync — 通知后台上传完成，携带 ext_info3

关键参数（已验证）：
    - reqHead.common_head.cmd         : 整数，100=CMD_UPLOAD
    - reqHead.scene.business_type     : 整数，1=图片/视频缩略图
    - reqHead.scene.app_type          : 整数，25=APP_TYPE_CHANNEL_FEEDS
    - reqHead.scene.scene_type        : 整数，5=APP_CUSTOM
    - uploadReq.upload_info[].file_info.size : 整数
    - 所有字段名保持 snake_case，通过 client_content 透传绕过 camelCase 转换

上传协议（已验证）：
    - 路径: POST /sliceupload (非 /upload)
    - Content-Type: application/protobuf
    - appid: msgInfo.msgInfoBody[0].indexNode.storeAppid（= 1487）
    - slice_size = partDataSize / 8（partDataSize 来自 uploadCtrl.partDataSize）
    - extend_type: extinfo[0].extType
    - extend_info (ext_info2): extinfo[0].extInfo（base64 解码）
    - IP 解析: outIp 为小端序 uint32

状态同步（已验证）：
    - cmd=103 (CMD_UPLOAD_STATUS_SYNC)
    - uploadReq.upload_channel_info.extend_type + extend_info = ext_info3（分片上传返回）
    - uploadReq.index_node[0].file_uuid = fileid（分片上传返回）
"""

import json
import sys
import os
import hashlib
import socket
import struct
import base64
import platform
import subprocess
import logging
import logging.handlers

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ── 日志初始化 ─────────────────────────────────────────────────────────────────
def _init_logger() -> logging.Logger:
    """初始化上传日志，同时输出到 stderr 和 scripts/feed/logs/upload.log（按天滚动）。"""
    logger = logging.getLogger("upload")
    if logger.handlers:          # 避免重复初始化（模块被多次 import 时）
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # stderr handler
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # 文件 handler（按天滚动，保留 7 天）
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "upload.log")
    fh = logging.handlers.TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=7, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger

_logger = _init_logger()

def _log(msg: str) -> None:
    """写一条 INFO 日志（同时到 stderr 和文件）。"""
    _logger.info(msg)


from _mcp_client import call_mcp, get_token

try:
    from _test_env import get_test_cookie
except ImportError:
    get_test_cookie = None

TOOL_APPLY_UPLOAD   = "apply_media_upload"
TOOL_STATUS_SYNC    = "apply_media_upload_status_sync"

# ============================================================
# Go 二进制（分片上传核心）
# ⚠️ libsliceupload 目录下的文件是 **Go 编译的可执行程序**（ELF/Mach-O），
#    不是 .so/.dylib 动态库。调用方式是 subprocess.run([bin_path], stdin=JSON)，
#    **禁止**使用 ctypes / dlopen / CDLL 等方式加载。
# ============================================================

_LIBSLICEUPLOAD_CDN    = "https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/references/libsliceupload.zip"


class _DepsNotInstalled(Exception):
    """依赖未安装，需要用户确认后再安装。"""


def _libsliceupload_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "libsliceupload")


def _libsliceupload_ready() -> bool:
    d = _libsliceupload_dir()
    return os.path.isdir(d) and bool(os.listdir(d))


def _install_libsliceupload() -> str:
    """从 CDN 下载并解压 libsliceupload，返回安装目录。"""
    import zipfile, tempfile, urllib.request
    bin_dir = _libsliceupload_dir()
    os.makedirs(bin_dir, exist_ok=True)
    tmp_zip = os.path.join(tempfile.gettempdir(), "libsliceupload.zip")
    try:
        urllib.request.urlretrieve(_LIBSLICEUPLOAD_CDN, tmp_zip)
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            zf.extractall(bin_dir)
        for f in os.listdir(bin_dir):
            fp = os.path.join(bin_dir, f)
            if os.path.isfile(fp) and not f.startswith("."):
                os.chmod(fp, 0o755)
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)
    return bin_dir


def _get_slice_bin():
    """按平台返回 sliceupload **可执行程序**路径（非动态库，用 subprocess 调用）。

    依赖不存在时抛出 _DepsNotInstalled，由调用方提示用户确认安装。
    """
    if not _libsliceupload_ready():
        raise _DepsNotInstalled("发布图/视频帖子需要安装相关依赖，是否继续？")
    bin_dir = _libsliceupload_dir()
    system = platform.system().lower()
    if system == "darwin":
        bin_name = "sliceupload_darwin"
    elif system == "linux":
        bin_name = "sliceupload_linux"
    elif system == "windows":
        bin_name = "sliceupload_windows.exe"
    else:
        raise OSError(f"不支持的平台: {system}")
    bin_path = os.path.join(bin_dir, bin_name)
    if not os.path.isfile(bin_path):
        raise OSError(f"二进制不存在: {bin_path}（CDN 包中可能缺少该平台的二进制）")
    return bin_path

# MCP 接口枚举字符串（req_head 用字符串，后端 schema 要求）
_APP_TYPE_CHANNEL_FEEDS = "APP_TYPE_CHANNEL_FEEDS"
_SCENE_TYPE_APP_CUSTOM  = "SCENE_TYPE_APP_CUSTOM"
_BIZ_TYPE_PICTURE       = "BUSINESS_TYPE_PICTURE"
_BIZ_TYPE_VIDEO         = "BUSINESS_TYPE_VIDEO"
_BIZ_TYPE_FILE          = "BUSINESS_TYPE_FILE"
_CMD_UPLOAD             = "CMD_UPLOAD"
_CMD_UPLOAD_STATUS_SYNC = "CMD_UPLOAD_STATUS_SYNC"

# business_type 参数（用户传入 1002/1003/1004）→ 内部枚举字符串
_BIZ_TYPE_MAP = {
    1002: _BIZ_TYPE_PICTURE,
    1003: _BIZ_TYPE_VIDEO,
    1004: _BIZ_TYPE_FILE,
}

SKILL_MANIFEST = {
    "name": "upload-image",
    "description": (
        "腾讯频道（QQ Channel）帖子富媒体（图片/视频/文件）上传。"
        "上传流程：申请上传 → 分片HTTP上传（/sliceupload protobuf格式）→ 同步状态通知后台入库，一次调用完成全流程。"
        "支持秒传（已存在相同文件时直接返回）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "string",
                "description": "频道ID（uint64 字符串），必填"
            },
            "channel_id": {
                "type": "string",
                "description": "子频道ID（uint64 字符串），必填"
            },
            "business_type": {
                "type": "integer",
                "description": (
                    "富媒体业务类型：\n"
                    "  1002 = 频道帖子图片/视频缩略图（默认）\n"
                    "  1003 = 频道帖子视频主体（⚠️ 发视频帖必须传此值，传 1002 会导致 slice N failed）\n"
                    "  1004 = 频道帖子文件"
                ),
                "default": 1002
            },
            "file_path": {
                "type": "string",
                "description": "本地文件路径，必填"
            },
            "file_name": {
                "type": "string",
                "description": "文件名（含扩展名，如 photo.jpg），不填时从 file_path 中提取"
            },
            "width": {
                "type": "integer",
                "description": "图片/视频宽度（像素），选填"
            },
            "height": {
                "type": "integer",
                "description": "图片/视频高度（像素），选填"
            },
        },
        "required": ["guild_id", "channel_id", "file_path"]
    }
}


# ============================================================
# 内部工具函数
# ============================================================

def _build_req_head(business_type: int, cmd: int) -> dict:
    """构造 richmedia.ReqHead（camelCase，_call_raw 不做自动转换）。"""
    biz_type = _BIZ_TYPE_MAP.get(business_type, _BIZ_TYPE_PICTURE)
    return {
        "commonHead": {
            "requestId": "0",
            "cmd": cmd,
        },
        "scene": {
            "businessType": biz_type,
            "appType":      _APP_TYPE_CHANNEL_FEEDS,
            "sceneType":    _SCENE_TYPE_APP_CUSTOM,
        }
    }


def _call_raw(tool_name: str, req_head: dict, upload_req: dict) -> dict:
    """直接发 HTTP 请求，完全绕过 _mcp_client 的 camelCase 转换。"""
    import httpx

    token = get_token()
    server_url = "https://graph.qq.com/mcp_gateway/open_platform_agent_mcp/mcp"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    cookie = get_test_cookie() if get_test_cookie else None
    if cookie:
        headers["Cookie"] = cookie

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": {
                "reqHead":   req_head,
                "uploadReq": upload_req,
            }
        }
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            server_url,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()

    if "error" in result:
        raise RuntimeError(f"MCP error {result['error']['code']}: {result['error']['message']}")

    return result.get("result", {})


def _check_error(result: dict, tool_name: str) -> None:
    """检查 MCP 响应是否有错误，有则抛出 RuntimeError。"""
    if result.get("isError"):
        meta     = result.get("_meta", {}).get("AdditionalFields", {})
        ret_code = meta.get("retCode", -1)
        err_msg  = meta.get("errMsg", str(result.get("content", "")))
        raise RuntimeError(f"{tool_name} failed: code={ret_code} msg={err_msg}")
    content  = result.get("structuredContent", {})
    head     = content.get("head", {})
    ret_code = head.get("retCode", 0)
    ret_msg  = head.get("retMsg", "")
    if ret_code != 0:
        raise RuntimeError(f"{tool_name} failed: code={ret_code} msg={ret_msg}")


def _calc_file_hashes(file_path: str) -> tuple:
    """计算文件 MD5 和 SHA1，返回 (md5_hex, sha1_hex, file_size)"""
    md5  = hashlib.md5()
    sha1 = hashlib.sha1()
    size = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            md5.update(chunk)
            sha1.update(chunk)
            size += len(chunk)
    return md5.hexdigest(), sha1.hexdigest(), size


def _int_ip_to_str(n: int) -> str:
    """将整数 IP 转为点分十进制字符串（小端序）。"""
    return socket.inet_ntoa(struct.pack("<I", n))


# ============================================================
# 三个底层接口封装
# ============================================================

def _apply_media_upload(business_type: int,
                        file_size: int, file_md5: str, file_sha1: str,
                        file_name: str, width: int, height: int) -> dict:
    """调用 apply_media_upload，返回 {ukey, upload_addrs, domain, appid, extend_type,
    extend_info (ext_info2), part_size, msg_info, is_fast_upload}"""
    req_head   = _build_req_head(business_type, _CMD_UPLOAD)
    file_info  = {
        "size":       str(file_size),
        "md5":        file_md5,
        "sha1":       file_sha1,
        "fileName":   file_name,
        "isOriginal": True,
    }
    if width:
        file_info["width"]  = width
    if height:
        file_info["height"] = height

    upload_req = {
        "uploadInfo":    [{"fileInfo": file_info}],
        "bizTransInfo": "",
    }

    result     = _call_raw(TOOL_APPLY_UPLOAD, req_head, upload_req)
    _check_error(result, TOOL_APPLY_UPLOAD)
    content    = result.get("structuredContent", {})
    upload_rsp = content.get("uploadRsp", {})

    ukey       = upload_rsp.get("ukey", "")
    domain     = upload_rsp.get("domain", "")
    msg_info   = upload_rsp.get("msgInfo", None) or {}

    # 解析上传地址：outIp（整数小端序）+ outPort
    upload_addrs = []
    for addr in upload_rsp.get("ipv4", []):
        try:
            host = _int_ip_to_str(addr["outIp"])
            port = addr.get("outPort", 80)
            upload_addrs.append({"host": host, "port": port})
        except Exception:
            pass

    # 解析 storeAppid（分片上传的 appid）
    store_appid = 0
    for body in msg_info.get("msgInfoBody", []):
        idx_node = body.get("indexNode") or {}
        if idx_node.get("storeAppid"):
            store_appid = int(idx_node["storeAppid"])
            break

    # 解析 extinfo（ext_info2）
    extinfo_list = upload_rsp.get("extinfo") or []
    extend_type = 0
    extend_info = b""
    if extinfo_list:
        ext = extinfo_list[0]
        extend_type = ext.get("extType", 0)
        ext_b64 = ext.get("extInfo", "")
        if ext_b64:
            try:
                extend_info = base64.b64decode(ext_b64)
            except Exception:
                pass

    # 分片大小：协议要求 slice_size = partDataSize / 8
    ctrl = upload_rsp.get("uploadCtrl") or {}
    part_data_size = int(ctrl.get("partDataSize", 1048576)) or 1048576
    part_size = part_data_size // 8

    # 秒传判断：有 msgInfo 且无 ukey
    is_fast_upload = bool(msg_info) and not ukey

    return {
        "ukey":           ukey,
        "upload_addrs":   upload_addrs,
        "domain":         domain,
        "appid":          store_appid,
        "extend_type":    extend_type,
        "extend_info":    extend_info,
        "part_size":      part_size,
        "msg_info":       msg_info,
        "is_fast_upload": is_fast_upload,
    }


def _http_slice_upload(file_path: str, upload_info: dict) -> dict:
    """调用 Go 二进制完成分片上传，返回 {fileid, file_sha1, extend_info (ext_info3)}"""
    params = {
        "file_path":    file_path,
        "ukey":         upload_info["ukey"],
        "appid":        upload_info["appid"],
        "extend_type":  upload_info["extend_type"],
        "extend_info":  base64.b64encode(upload_info["extend_info"]).decode() if upload_info["extend_info"] else "",
        "part_size":    upload_info["part_size"],
        "upload_addrs": upload_info["upload_addrs"],
    }
    bin_path = _get_slice_bin()
    if not os.access(bin_path, os.X_OK):
        os.chmod(bin_path, 0o755)
    try:
        proc = subprocess.run(
            [bin_path],
            input=json.dumps(params).encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("sliceupload 超时（60s），请检查网络连接后重试")
    except OSError as e:
        raise RuntimeError(
            f"sliceupload 执行失败: {e}。"
            "注意：libsliceupload 是 Go 编译的可执行程序（用 subprocess 调用），"
            "不是 .so/.dylib 动态库，禁止用 ctypes/dlopen 加载。"
        ) from e
    try:
        result = json.loads(proc.stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        stderr_hint = proc.stderr.decode("utf-8", errors="replace")[:200] if proc.stderr else ""
        raise RuntimeError(
            f"sliceupload 返回了非 JSON 数据（exit={proc.returncode}）。{stderr_hint}"
        )
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "分片上传失败"))
    ext_info3 = base64.b64decode(result.get("extend_info", "")) if result.get("extend_info") else b""
    # Windows 秒传场景：Go 二进制返回 {"ok":true} 但不含 fileid/file_sha1，
    # 此时 fileid 已在 apply_media_upload 第一步的 msg_info 里（fileUuid 字段）。
    fileid = result.get("fileid") or _extract_file_uuid(upload_info.get("msg_info") or {})
    file_sha1 = result.get("file_sha1", "")
    return {
        "fileid":      fileid,
        "file_sha1":   file_sha1,
        "extend_info": ext_info3,
    }


def _apply_media_upload_status_sync(business_type: int,
                                    file_uuid: str, file_md5: str, file_sha1: str,
                                    file_size: int, file_name: str,
                                    extend_type: int, extend_info: bytes) -> dict:
    """调用 apply_media_upload_status_sync，通知后台文件上传完成。"""
    req_head   = _build_req_head(business_type, _CMD_UPLOAD_STATUS_SYNC)
    upload_req = {
        "indexNode": {
            "fileInfo": {
                "size":      str(file_size),
                "md5":       file_md5,
                "sha1":      file_sha1,
                "fileName":  file_name,
            },
            "fileUuid": file_uuid,
        },
        "uploadStatus": {
            "fileStatus": "UPLOAD_SUCCESS",
        },
        "uploadChannelInfo": {
            "extendType": extend_type,
            "extendInfo": base64.b64encode(extend_info).decode() if extend_info else "",
        },
    }

    result  = _call_raw(TOOL_STATUS_SYNC, req_head, upload_req)
    _check_error(result, TOOL_STATUS_SYNC)
    content           = result.get("structuredContent", {})
    upload_status_rsp = content.get("uploadStatusRsp", {}) or content.get("upload_status_sync_rsp", {})
    biz_error_info    = upload_status_rsp.get("bizErrorInfo", {}) or {}

    # 尝试从 status_sync 响应中提取 video_id（.mov 等格式无法从 ext_info3 获取时的兜底）
    # 响应结构未知，先把完整内容透传出去以便调试
    return {
        "biz_error_code":      biz_error_info.get("errorCode", 0),
        "biz_error_msg":       biz_error_info.get("errorMsg", ""),
        "_upload_status_rsp":  upload_status_rsp,   # 完整响应，供 _run_upload 调试用
    }


# ============================================================
# 主入口
# ============================================================

def run(params: dict) -> dict:
    """
    上传入口，完成申请上传 → 分片HTTP上传 → 状态同步全流程。

    支持两种 action:
      - "upload"（默认）：执行上传，依赖不存在时返回 needs_confirm
      - "install_deps"：用户确认后安装 libsliceupload 依赖

    返回:
        成功: {"success": True, "data": {
            "file_uuid", "file_md5", "file_sha1", "file_size",
            "is_fast_upload", "msg_info", "biz_error_code", "biz_error_msg"}}
        依赖缺失: {"success": False, "needs_confirm": True, "error": "..."}
        失败: {"success": False, "error": "..."}
    """
    action = params.get("action", "upload")

    if action == "install_deps":
        try:
            install_dir = _install_libsliceupload()
            return {"success": True, "data": {"installed": True, "path": install_dir}}
        except Exception as e:
            return {"success": False, "error": f"依赖安装失败: {e}"}

    business_type = params.get("business_type", 1002)
    try:
        return _run_upload(params, business_type)
    except _DepsNotInstalled as e:
        return {"success": False, "needs_confirm": True, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_upload(params: dict, business_type: int) -> dict:
    """执行完整上传流程：申请上传 → 分片HTTP上传 → 状态同步"""
    file_path = params.get("file_path", "")
    if not file_path:
        return {"success": False, "error": "action=upload 时 file_path 为必填参数"}
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    file_name = params.get("file_name") or os.path.basename(file_path)
    width     = params.get("width", 0)
    height    = params.get("height", 0)
    biz_label = {1002: "图片", 1003: "视频", 1004: "文件"}.get(business_type, str(business_type))

    _log(f"[upload] 开始上传 {biz_label}: {file_path}")

    # Step 0: 计算文件哈希和大小
    file_md5, file_sha1, file_size = _calc_file_hashes(file_path)
    _log(f"[upload] 文件信息: size={file_size}B  md5={file_md5}  name={file_name}")

    # Step 1: 申请上传
    _log("[upload] Step1 申请上传 (apply_media_upload)...")
    try:
        upload_info = _apply_media_upload(
            business_type, file_size, file_md5, file_sha1, file_name, width, height,
        )
    except Exception as e:
        _log(f"[upload] Step1 失败: {e}")
        raise

    msg_info = upload_info.get("msg_info") or {}

    # 秒传：无需 HTTP 上传，直接完成
    if upload_info["is_fast_upload"]:
        file_uuid = _extract_file_uuid(msg_info)
        _log(f"[upload] 秒传命中，file_uuid={file_uuid}")
        return {"success": True, "data": {
            "file_uuid":      file_uuid,
            "file_md5":       file_md5,
            "file_sha1":      file_sha1,
            "file_size":      file_size,
            "is_fast_upload": True,
            "msg_info":       msg_info,
            "biz_error_code": 0,
            "biz_error_msg":  "",
        }}

    addrs_str = [f"{a['host']}:{a['port']}" for a in upload_info["upload_addrs"]]
    _log(
        f"[upload] Step1 成功: ukey={upload_info['ukey'][:16]}...  "
        f"appid={upload_info['appid']}  part_size={upload_info['part_size']}B  "
        f"addrs={addrs_str}"
    )

    # Step 2: 分片上传文件（/sliceupload）
    _log("[upload] Step2 分片上传 (sliceupload)...")
    try:
        slice_result = _http_slice_upload(file_path, upload_info)
    except _DepsNotInstalled:
        raise
    except Exception as e:
        _log(f"[upload] Step2 失败: {e}")
        return {"success": False, "error": f"文件分片上传失败: {e}"}

    fileid      = slice_result["fileid"]
    ext_info3   = slice_result.get("extend_info", b"")   # .mov 等格式服务端不返回 extend_info
    extend_type = upload_info["extend_type"]
    ext_info3_desc = "有" if ext_info3 else "无"
    _log(
        f"[upload] Step2 成功: fileid={fileid}  "
        f"ext_info3={ext_info3_desc}({len(ext_info3)}B)  "
        f"extend_type={extend_type}"
    )

    # Step 3: 状态同步（携带 ext_info3）
    _log("[upload] Step3 状态同步 (apply_media_upload_status_sync)...")
    try:
        sync_result = _apply_media_upload_status_sync(
            business_type, fileid, file_md5, file_sha1, file_size,
            file_name, extend_type, ext_info3,
        )
    except Exception as e:
        _log(f"[upload] Step3 失败: {e}")
        return {"success": False, "error": f"状态同步失败: {e}"}

    biz_code = sync_result["biz_error_code"]
    biz_msg  = sync_result["biz_error_msg"]
    if biz_code:
        _log(f"[upload] Step3 biz错误: code={biz_code}  msg={biz_msg}")
    else:
        _log(f"[upload] Step3 成功: biz_error_code=0  status_sync_rsp={sync_result.get('_upload_status_rsp', {})}")
    _log(f"[upload] 上传完成: file_uuid={fileid}")

    return {"success": True, "data": {
        "file_uuid":          fileid,
        "file_md5":           file_md5,
        "file_sha1":          file_sha1,
        "file_size":          file_size,
        "ext_info3":          base64.b64encode(ext_info3).decode() if ext_info3 else "",   # NTPhotoUploadRspExtinfo protobuf 字节（base64）
        "is_fast_upload":     False,
        "msg_info":           msg_info,
        "biz_error_code":     sync_result["biz_error_code"],
        "biz_error_msg":      sync_result["biz_error_msg"],
        "_status_sync_rsp":   sync_result.get("_upload_status_rsp", {}),   # 调试：status_sync 完整响应
    }}


def _extract_file_uuid(msg_info: dict) -> str:
    """从 msgInfo 中提取 fileUuid（兼容多级嵌套）"""
    if not msg_info:
        return ""
    if "fileUuid" in msg_info:
        return msg_info["fileUuid"]
    for body in msg_info.get("msgInfoBody", []):
        uuid = (body.get("indexNode") or {}).get("fileUuid", "")
        if uuid:
            return uuid
    return (msg_info.get("indexNode") or {}).get("fileUuid", "")


if __name__ == "__main__":
    from _skill_runner import run_as_cli
    run_as_cli(SKILL_MANIFEST, run)
