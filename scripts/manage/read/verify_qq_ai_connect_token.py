#!/usr/bin/env python3
"""校验 QQ AI Connect token 与 MCP 连通性（响应不含 token 明文）。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import ok, read_input, verify_token_and_mcp_connectivity  # noqa: E402


def main():
    read_input()
    data = verify_token_and_mcp_connectivity()
    ok(data)


if __name__ == "__main__":
    main()
