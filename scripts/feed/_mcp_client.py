"""
公共 MCP 客户端模块
鉴权：get_token() → .env → mcporter（见 scripts/manage/common.py）。

禁止在 feed 的 stdin JSON 中传入 token（见 _skill_runner.py）。
"""

import base64
import os
import sys
from pathlib import Path

import httpx

_MANAGE_DIR = str(Path(__file__).resolve().parent.parent / "manage")
if _MANAGE_DIR not in sys.path:
    sys.path.insert(0, _MANAGE_DIR)
from common import get_token  # noqa: E402

_MCP_SERVER_URL = "https://graph.qq.com/mcp_gateway/open_platform_agent_mcp/mcp"
_MCP_ENV = os.environ.get("QQ_AI_CONNECT_MCP_ENV", "").strip().lower()
_MCP_TEST_COOKIE = "qq_env_front=test; qq_env_back=test"


def _snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


_SNAKE_CASE_PRESERVE_KEYS = {"guild_id", "channel_id", "group_id", "channel_type"}
_TOP_LEVEL_PRESERVE_KEYS = {"client_content"}


def _to_camel_keys(obj, _in_sign=False, _top_level=False):
    """递归将 dict 的键从 snake_case 转换为 camelCase。
    - sign 直接子字段保持 snake_case 不变
    - 顶层 arguments 中 client_content 等 key 保持 snake_case 不变
    """
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if _top_level and k in _TOP_LEVEL_PRESERVE_KEYS:
                new_key = k
                result[new_key] = v
            elif _in_sign and k in _SNAKE_CASE_PRESERVE_KEYS:
                new_key = k
                result[new_key] = _to_camel_keys(v, _in_sign=(k == "sign"))
            else:
                new_key = _snake_to_camel(k)
                result[new_key] = _to_camel_keys(v, _in_sign=(k == "sign"))
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

    if _MCP_ENV == "test":
        headers["Cookie"] = _MCP_TEST_COOKIE

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
        raise RuntimeError(f"MCP 业务错误 (retCode={ret_code}): {detail}")

    return mcp_result


# ── 帖子分享短链 ──────────────────────────────────────────────

def _build_feed_business_param(feed_id: str) -> str:
    """将 feed_id 编码为 get_share_url 所需的 businessParam（base64 protobuf）。"""
    import base64, binascii, struct

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
        structured = result.get("structuredContent") or {}
        url = structured.get("url", "")
        if not url:
            import re
            for item in result.get("content", []):
                text = item.get("text", "")
                m = re.search(r'"url"\s*:\s*"([^"]+)"', text)
                if m:
                    url = m.group(1)
                    break
        return url
    except Exception:
        return ""


def get_guild_share_url(guild_id: str) -> str:
    """获取频道分享短链，失败返回空字符串。"""
    try:
        result = call_mcp("get_share_url", {
            "guild_id": guild_id,
            "is_short_link": True,
        })
        structured = result.get("structuredContent") or {}
        url = structured.get("url", "")
        if not url:
            import re
            for item in result.get("content", []):
                text = item.get("text", "")
                m = re.search(r'"url"\s*:\s*"([^"]+)"', text)
                if m:
                    url = m.group(1)
                    break
        return url
    except Exception:
        return ""
