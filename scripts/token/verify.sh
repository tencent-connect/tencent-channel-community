#!/usr/bin/env bash
# 校验 manage 鉴权：调用 get_user_info（查自己）探测 MCP（实现见 verify_qq_ai_connect_token.py）
#
# 用法（在 skill 根目录执行）：
#   bash scripts/token/verify.sh
#
# 依赖：python3；token 来自 ~/.openclaw/.env 或 mcporter（与业务脚本相同顺序）

set -euo pipefail

_TOKEN_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$_TOKEN_SCRIPT_DIR/../.." && pwd)"
cd "$SKILL_ROOT"

if ! command -v python3 &>/dev/null; then
  echo "错误: 需要 python3" >&2
  exit 1
fi

exec python3 scripts/manage/read/verify_qq_ai_connect_token.py </dev/null
