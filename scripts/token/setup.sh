#!/usr/bin/env bash
# 将 token 写入 ~/.openclaw/.env（不存在则创建目录与文件），并注册 mcporter
#
# 前置：已安装 Node.js 与 mcporter（npm install -g mcporter）；写入 .env 仅需 Python3
#
# 用法（在 skill 根目录执行，路径相对 SKILL.md）：
#   bash scripts/token/setup.sh '<token>'
# token 从 https://connect.qq.com/ai 获取（一般为 bot:v1_...）。
#
# 若 token 以 "-" 开头，请使用：
#   bash scripts/token/setup.sh -- '<token>'
#
# 可选环境变量：
#   TENCENT_CHANNEL_MCPORTER_SERVICE  服务别名，默认 tencent-channel-mcp
#   QQ_AI_CONNECT_DOTENV              覆盖默认 .env 路径（默认为 ~/.openclaw/.env）

set -euo pipefail

_TOKEN_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$_TOKEN_SCRIPT_DIR/../.." && pwd)"

usage() {
  cat >&2 <<'EOF'
用法:
  bash scripts/token/setup.sh <token>

说明:
  在 skill 根目录执行。会写入 ~/.openclaw/.env（目录/文件不存在会自动创建）并执行 mcporter config add。
  读取 token 时优先 .env 文件，其次 mcporter（由 manage 脚本解析）。

示例:
  bash scripts/token/setup.sh 'bot:v1_xxxxxxxx'

注意:
  命令行传 token 可能进入 shell 历史；用完后可考虑清理历史或使用专用配置终端。
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

if [[ "$1" == "--" ]]; then
  shift
  if [[ $# -lt 1 ]]; then
    echo "错误: -- 后缺少 token" >&2
    exit 1
  fi
fi

TOKEN="$1"
if [[ -z "$TOKEN" ]]; then
  echo "错误: token 不能为空" >&2
  exit 1
fi

export SKILL_ROOT
export PYTHONPATH="${SKILL_ROOT}/scripts/manage"
cd "$SKILL_ROOT"

if ! command -v python3 &>/dev/null; then
  echo "错误: 需要 python3 以写入 .env" >&2
  exit 1
fi

export TOKEN_TO_PERSIST="${TOKEN}"
OUT="$(python3 <<'PY'
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ["SKILL_ROOT"], "scripts", "manage"))
from common import persist_token_to_dotenv_and_mcporter

token = os.environ.get("TOKEN_TO_PERSIST", "")
print(json.dumps(persist_token_to_dotenv_and_mcporter(token), ensure_ascii=False))
PY
)" || exit 1
unset TOKEN_TO_PERSIST

echo "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print('dotenv:', d.get('dotenvPath')); print('mcporter:', 'ok' if d.get('mcporterOk') else d.get('mcporterMessage','fail'))"

echo "完成。请在 skill 根目录执行自检（输出不含 token 明文）："
echo "  bash scripts/token/verify.sh"
