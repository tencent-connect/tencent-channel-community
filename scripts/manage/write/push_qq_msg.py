#!/usr/bin/env python3
"""通过 QQ 消息推送任务结果。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import call_mcp, fail, ok, read_input, require_str  # noqa: E402

_STATUS_MAP = {
    "success": "已完成",
    "failed": "执行失败",
    "partial": "部分完成",
}


def build_text(task_name: str, status: str, detail: str = "") -> str:
    if status not in _STATUS_MAP:
        fail("参数 status 只支持 success/failed/partial")
    text = f"【任务通知】{task_name} - {_STATUS_MAP[status]}"
    if detail:
        text += f"\n详情：{detail}"
    return text


def main():
    params = read_input()
    task_name = require_str(params, "task_name")
    status = require_str(params, "status")
    detail = str(params.get("detail", "")).strip()
    dry_run = bool(params.get("dry_run", False))
    text = build_text(task_name, status, detail)
    if dry_run:
        ok({
            "text": text,
            "dryRun": True,
            "raw": {
                "name": "push_qq_msg",
                "arguments": {"text": text},
            },
        })
    result = call_mcp("push_qq_msg", {"text": text})
    ok({
        "text": text,
        "dryRun": False,
        "raw": result,
    })


if __name__ == "__main__":
    main()
