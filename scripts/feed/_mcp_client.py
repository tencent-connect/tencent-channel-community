"""
公共 MCP 客户端模块
鉴权：get_token() → .env → mcporter（见 scripts/manage/common.py）。

禁止在 feed 的 stdin JSON 中传入 token（见 _skill_runner.py）。
"""

import base64
import binascii
import os
import re
import struct
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

_MANAGE_DIR = str(Path(__file__).resolve().parent.parent / "manage")
if not Path(_MANAGE_DIR).is_dir():
    raise ImportError(
        f"[tencent-channel-community] 找不到 manage 目录：{_MANAGE_DIR}\n"
        "请确认 skill 包已完整解压（应包含 scripts/manage/common.py），"
        "或重新安装 skill。"
    )
if _MANAGE_DIR not in sys.path:
    sys.path.insert(0, _MANAGE_DIR)
from common import get_token  # noqa: E402

_MCP_SERVER_URL = "https://graph.qq.com/mcp_gateway/open_platform_agent_mcp/mcp"
_BEIJING_TZ = timezone(timedelta(hours=8))  # UTC+8，模块级常量，避免每次调用重复创建

try:
    from _test_env import get_test_cookie
except ImportError:
    get_test_cookie = None

# token 相关错误码（8011=token无效/过期，8001=未授权，8003=token格式错误）
_TOKEN_ERR_CODES = {8001, 8003, 8011}
# 业务错误码友好化映射
_BUSINESS_ERR_MAP = {
    155: "操作的帖子/评论不存在或已被删除",
}


def _snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


_SNAKE_CASE_PRESERVE_KEYS = {"guild_id", "channel_id", "group_id", "channel_type"}
_TOP_LEVEL_PRESERVE_KEYS = {"client_content"}


def _to_camel_keys(obj, _in_sign=False, _top_level=False):
    """递归将 dict 的键从 snake_case 转换为 camelCase。
    - sign 直接子字段保持 snake_case 不变
    - 顶层 arguments 中 client_content 等 key 保持 snake_case 不变
      （client_content 的 value 已是 camelCase，直接透传，不做递归转换）
    """
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if _top_level and k in _TOP_LEVEL_PRESERVE_KEYS:
                result[k] = v
            elif _in_sign and k in _SNAKE_CASE_PRESERVE_KEYS:
                result[k] = _to_camel_keys(v, _in_sign=(k == "sign"))
            else:
                result[_snake_to_camel(k)] = _to_camel_keys(v, _in_sign=(k == "sign"))
        return result
    if isinstance(obj, list):
        return [_to_camel_keys(item, _in_sign) for item in obj]
    return obj


def call_mcp(tool_name: str, arguments: dict) -> dict:
    """向 MCP 服务发起 JSON-RPC 调用，返回 result 字段内容。"""
    token = get_token()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Forwarded-Method": "POST",
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
            "arguments": _to_camel_keys(arguments, _top_level=True)
        }
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            _MCP_SERVER_URL,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()

    if "error" in result:
        raise RuntimeError(f"MCP error {result['error']['code']}: {result['error']['message']}")

    mcp_result = result.get("result", {})

    if mcp_result.get("isError"):
        meta = mcp_result.get("_meta", {}).get("AdditionalFields", {})
        ret_code = meta.get("retCode", "unknown")
        err_msg = meta.get("errMsg", "")
        contents = mcp_result.get("content", [])
        detail = err_msg or "; ".join(c.get("text", "") for c in contents if c.get("type") == "text")
        try:
            _code_int = int(ret_code)
        except (TypeError, ValueError):
            _code_int = None
        _token_hint = ""
        if _code_int in _TOKEN_ERR_CODES or "token" in detail.lower() or "auth" in detail.lower():
            _token_hint = "\n[诊断] Token 可能已过期或无效，请前往 https://connect.qq.com/ai 更新 Token 后重试。"
        # 用友好消息覆盖晦涩的后端错误描述
        if _code_int in _BUSINESS_ERR_MAP:
            detail = _BUSINESS_ERR_MAP[_code_int]
        elif detail and "请求发送给后端Server失败" in detail:
            detail = "请求发送给后端服务失败，请稍后重试"
        raise RuntimeError(f"MCP 业务错误 (retCode={ret_code}): {detail}{_token_hint}")

    return mcp_result


# ── 帖子分享短链 ──────────────────────────────────────────────

def _build_feed_business_param(feed_id: str) -> str:
    """将 feed_id 编码为 get_share_url 所需的 businessParam（base64 protobuf）。"""
    FEED_ID_PREFIX = "B_"
    APP_ID_FLAG = "0X"
    BUSINESS_TYPE_FEED = 2

    if not feed_id.startswith(FEED_ID_PREFIX) or len(feed_id) < 24:
        raise ValueError(f"feed_id 不合法: {feed_id}")

    hex_part = feed_id[len(FEED_ID_PREFIX): len(FEED_ID_PREFIX) + 16]
    decoded = binascii.unhexlify(hex_part)
    create_time = struct.unpack("<I", decoded[:4])[0]

    tail = feed_id[len(FEED_ID_PREFIX) + 16:]
    pos = tail.find(APP_ID_FLAG)
    poster_text = tail[:pos] if pos != -1 else tail
    poster_tiny_id = int(poster_text, 10)

    def _varint(v: int) -> bytes:
        out = bytearray()
        while True:
            bits = v & 0x7F; v >>= 7
            out.append(bits | 0x80 if v else bits)
            if not v:
                break
        return bytes(out)

    def _field_varint(fn, v): return _varint((fn << 3) | 0) + _varint(v)
    def _field_bytes(fn, b):  return _varint((fn << 3) | 2) + _varint(len(b)) + b
    def _field_string(fn, s): return _field_bytes(fn, s.encode("utf-8"))

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


def _extract_url_from_mcp_result(result: dict) -> str:
    """从 MCP 响应中提取 URL：先从 structuredContent.url 取，失败再扫描 content[].text。"""
    structured = result.get("structuredContent") or {}
    url = structured.get("url", "")
    if not url:
        for item in result.get("content", []):
            text = item.get("text", "")
            m = re.search(r'"url"\s*:\s*"([^"]+)"', text)
            if m:
                url = m.group(1)
                break
    return url


def get_feed_share_url(guild_id: str, channel_id: str, feed_id: str) -> str:
    """获取帖子分享短链，失败返回空字符串。"""
    try:
        business_param = _build_feed_business_param(feed_id)
        args = {
            "guild_id": guild_id,
            "business_param": business_param,
            "is_short_link": True,
        }
        if channel_id:
            args["channel_id"] = channel_id
        result = call_mcp("get_share_url", args)
        return _extract_url_from_mcp_result(result)
    except Exception:
        return ""


def get_guild_share_url(guild_id: str) -> str:
    """获取频道分享短链，失败返回空字符串。"""
    try:
        result = call_mcp("get_share_url", {
            "guild_id": guild_id,
            "is_short_link": True,
        })
        return _extract_url_from_mcp_result(result)
    except Exception:
        return ""


def format_timestamp(ts) -> str:
    """将秒级时间戳转为可读时间字符串（北京时间 UTC+8），失败返回原始值字符串。"""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=_BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def build_json_contents(content: str, at_users: list) -> list:
    """构造 jsonComment/jsonReply.contents 数组，供 do_comment 和 do_reply 共用。

    结构：AT 节点在前（type=2），文本节点在后（type=1）；有 AT 时文本前补一个空格。
    at_content 结构对应线上抓包（type=1 表示普通用户 AT）。
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
        text = (" " + content) if contents else content
        contents.append({
            "text_content": {"text": text},
            "type": 1,
            "pattern_id": "",
        })
    return contents
