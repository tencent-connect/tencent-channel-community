#!/usr/bin/env python3
"""解析频道分享链接，返回对应的频道信息。"""

import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import ok, fail, read_input, require_str, call_mcp, decode_bytes_fields  # noqa: E402


def _parse_url(url: str) -> dict:
    """根据链接类型构造 MCP 入参。

    短链（如 https://pd.qq.com/s/xxx）→ shortUrl
    长链（含 inviteCode / contentID query 参数）→ inviteCode + contentId
    """
    parsed = urlparse(url)

    if parsed.hostname != "pd.qq.com":
        fail("这不是一个有效的频道分享链接（域名必须是 pd.qq.com）")

    qs = parse_qs(parsed.query)

    invite_code = qs.get("inviteCode", [None])[0]
    content_id = qs.get("contentID", [None])[0]

    if invite_code:
        args = {"inviteCode": invite_code}
        if content_id:
            args["contentId"] = content_id
        return args

    # 短链：路径以 /s/ 开头
    if parsed.path.startswith("/s/") and len(parsed.path) > 3:
        return {"shortUrl": url}

    fail("这不是一个有效的频道分享链接（需要是 pd.qq.com/s/xxx 短链或含 inviteCode 的长链）")


def main():
    params = read_input()
    url = require_str(params, "url")
    mcp_args = _parse_url(url)
    result = call_mcp("get_share_info", mcp_args)
    structured = result.get("structuredContent") or result
    data = decode_bytes_fields(structured)
    ok(data)


if __name__ == "__main__":
    main()
