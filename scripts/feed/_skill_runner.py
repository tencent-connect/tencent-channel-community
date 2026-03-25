"""
_skill_runner.py

支持两种 CLI 调用方式：

1. stdin JSON（推荐，与频道 manage 一致）：
    echo '{"feed_id": "B_xxx", "guild_id": 123456789}' | python3 read/get_feed_detail.py

2. argparse 命令行参数：
    python3 read/get_feed_detail.py --feed_id B_xxx --guild_id 123456789

凭证：get_token() → .env → mcporter（见 scripts/manage/common.py）；禁止在 stdin JSON 中传 token。

参数类型映射（argparse 模式）：
    string  → str
    integer → int
    boolean → true/false 字符串（不区分大小写）
    object  → JSON 字符串，自动解析为 dict
    array   → JSON 字符串，自动解析为 list
"""

import argparse
import json
import os
import re
import select
import sys

_FEED_TOKEN_FORBIDDEN = (
    "禁止在 stdin JSON 中传入 token。请按 SKILL.md 完成 get_token() → .env → mcporter 配置（与频道 manage 相同）。"
)


class StdinTokenForbidden(Exception):
    """stdin JSON 含 token 字段时抛出，勿与其它 ValueError 混淆。"""


def _read_stdin_json() -> dict | None:
    """尝试从 stdin 读取 JSON 输入，非 tty 且有数据时返回解析结果；否则返回 None。

    Raises:
        StdinTokenForbidden: stdin JSON 含 token 字段。
        ValueError: stdin 有内容但 JSON 解析失败（畸形输入）。
    """
    if sys.stdin.isatty():
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.0)
        if not ready:
            return None
        raw = sys.stdin.read().strip()
        if not raw:
            return None
        try:
            params = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"stdin 输入不是合法的 JSON：{exc}") from exc
        if not isinstance(params, dict):
            raise ValueError(f"stdin JSON 应为对象（dict），实际为 {type(params).__name__}")
        if "token" in params:
            raise StdinTokenForbidden()
        return params
    except (StdinTokenForbidden, ValueError):
        raise
    except Exception:
        return None


def validate_required(params: dict, manifest: dict) -> "dict | None":
    """
    检查 manifest 中声明的必填参数是否都存在于 params 中。
    有缺失时返回 {"success": False, "error": "缺少必填信息：频道ID、版块ID"}，
    其中字段名从 manifest 的 properties.description 中提取中文描述。
    否则返回 None。
    """
    required = manifest.get("parameters", {}).get("required", [])
    properties = manifest.get("parameters", {}).get("properties", {})
    missing = [k for k in required if k not in params or params[k] is None]
    if missing:
        labels = []
        for k in missing:
            desc = properties.get(k, {}).get("description", "")
            # 取 description 的首个语义片段（中文逗号/句号/冒号前，最多20字）
            m = re.match(r"^([^，,。；;：:]{1,20})", desc)
            label = m.group(1).strip() if m else k
            # 去掉末尾的英文技术修饰词（uint64/string/必填 等）
            label = re.sub(r"\s*(uint64|string|integer|int|bool|必填|选填)\s*$", "", label).strip()
            labels.append(label if label else k)
        return {"success": False, "error": f"缺少必填信息：{'、'.join(labels)}"}
    return None


def run_as_cli(manifest: dict, run_fn):
    """
    根据 SKILL_MANIFEST 支持两种入口：
    1. stdin JSON：优先；直接将 JSON 对象作为 params 调用 run_fn
    2. argparse：无 stdin 时自动生成 argparse CLI

    结果以 JSON 格式打印到 stdout。
    失败（success=false）时以 exit code 1 退出。
    """
    # ── 1. 优先尝试 stdin JSON ──────────────────────────────
    try:
        stdin_params = _read_stdin_json()
    except StdinTokenForbidden:
        print(
            json.dumps({"success": False, "error": _FEED_TOKEN_FORBIDDEN}, ensure_ascii=False, indent=2)
        )
        sys.exit(1)
    except ValueError as exc:
        print(
            json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, indent=2)
        )
        sys.exit(1)
    if stdin_params is not None:
        result = run_fn(stdin_params)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("success") else 1)

    # ── 2. 回退到 argparse ──────────────────────────────────
    params_schema   = manifest.get("parameters", {})
    required_fields = set(params_schema.get("required", []))
    properties      = params_schema.get("properties", {})

    parser = argparse.ArgumentParser(
        description=manifest.get("description", ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "也可以通过 stdin 传入 JSON 参数：\n"
            f"  echo '{{...}}' | python3 {os.path.basename(sys.argv[0])}"
        ),
    )

    for name, prop in properties.items():
        ptype   = prop.get("type", "string")
        desc    = prop.get("description", "")
        default = prop.get("default", None)
        choices = prop.get("enum", None)
        is_required = (name in required_fields) and (default is None)

        help_text = desc
        if default is not None:
            help_text += f" [默认: {default}]"
        if choices:
            help_text += f" 可选值: {choices}"

        kwargs = dict(
            help=help_text,
            required=is_required,
            dest=name,
            default=None,
        )

        if choices:
            kwargs["choices"] = choices  # 保持原始类型，与 type= 转换后的值一致

        if ptype == "integer":
            kwargs["type"] = int
        elif ptype == "number":
            kwargs["type"] = float
        elif ptype == "boolean":
            kwargs["type"] = lambda x: x.lower() in ("true", "1", "yes")
            kwargs["metavar"] = "true|false"
        elif ptype in ("object", "array"):
            kwargs["type"] = json.loads
            kwargs["metavar"] = "JSON"
        else:
            kwargs["type"] = str

        parser.add_argument(f"--{name}", **kwargs)

    args = parser.parse_args()
    # 过滤掉未传入的参数（None），只传用户实际提供的
    params = {k: v for k, v in vars(args).items() if v is not None}

    result = run_fn(params)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)
