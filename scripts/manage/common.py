#!/usr/bin/env python3
"""tencent-guild-manage 通用工具。

凭证：get_token() → .env → mcporter（默认 ~/.openclaw/.env；feed 经 _mcp_client 复用本模块）。
"""

import base64
import json
import os
import re
import select
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


MCP_SERVER_URL = "https://graph.qq.com/mcp_gateway/open_platform_agent_mcp/mcp"
DOTENV_TOKEN_KEY = "QQ_AI_CONNECT_TOKEN"
TOKEN_HELP_URL = "https://connect.qq.com/ai"
MCPORTER_SERVICE_ENV = "TENCENT_CHANNEL_MCPORTER_SERVICE"
DEFAULT_MCPORTER_SERVICE_NAME = "tencent-channel-mcp"
DOTENV_PATH_ENV = "QQ_AI_CONNECT_DOTENV"
VERIFY_SCRIPT_REL = "scripts/manage/read/verify_qq_ai_connect_token.py"
_DOTENV_WARNING = "# QQ AI Connect token — 敏感信息，勿提交到 git。"
try:
    from _test_env import get_test_cookie
except ImportError:
    get_test_cookie = None


class MCPUserError(Exception):
    """MCP 调用失败，供 verify 等非 fail() 场景捕获。"""

    def __init__(self, message: str, code: int = 200):
        super().__init__(message)
        self.message = message
        self.code = code


def fail(msg: str, code: int = 1):
    print(json.dumps({"code": code, "msg": msg, "data": None}, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


def ok(data):
    print(json.dumps({"code": 0, "msg": "success", "data": data}, ensure_ascii=False))
    sys.exit(0)


def read_input() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.0)
        if not ready:
            return {}
    except Exception:
        pass
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"输入不是合法 JSON: {exc}")
    if not isinstance(params, dict):
        fail("输入必须是 JSON 对象")
    params.pop("token", None)
    return params


def require_str(params: dict, key: str) -> str:
    value = params.get(key)
    if value is None:
        fail(f"参数 {key} 不能为空")
    text = str(value).strip()
    if not text:
        fail(f"参数 {key} 不能为空")
    return text


def optional_str(params: dict, key: str, default: str = "") -> str:
    value = params.get(key)
    if value is None:
        return default
    return str(value).strip()


def parse_positive_int(value, label: str) -> int:
    if isinstance(value, bool):
        fail(f"{label} 必须是正整数")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        fail(f"{label} 必须是正整数")
    if parsed <= 0:
        fail(f"{label} 必须大于 0")
    return parsed


def parse_nonnegative_int(value, label: str) -> int:
    if isinstance(value, bool):
        fail(f"{label} 必须是非负整数")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        fail(f"{label} 必须是非负整数")
    if parsed < 0:
        fail(f"{label} 必须大于等于 0")
    return parsed


_RE_PUBLIC_NAME = re.compile(r'^[\u4e00-\u9fff\w]+$')
_MAX_NAME_LEN = 15
_MAX_PROFILE_LEN = 300


def validate_guild_name(name: str, is_public: bool = False):
    """校验频道名：不超过15个字；公开频道只允许中文、英文、数字。"""
    if len(name) > _MAX_NAME_LEN:
        fail(f"频道名不能超过{_MAX_NAME_LEN}个字，当前{len(name)}个字")
    if is_public and not _RE_PUBLIC_NAME.fullmatch(name):
        fail("公开频道名称只能包含中文、英文字母和数字")


def validate_guild_profile(profile: str):
    """校验频道简介：不超过300个字符。"""
    if len(profile) > _MAX_PROFILE_LEN:
        fail(f"频道简介不能超过{_MAX_PROFILE_LEN}个字符，当前{len(profile)}个字符")


def check_sec_rets(rpc_result: dict):
    """检查 MCP 返回中的 sec_rets 安全打击字段，有内容则直接透传并 fail。"""
    structured = rpc_result.get("structuredContent") or {}
    sec_rets = None
    for key in ("sec_rets", "secRets", "sec_ret", "secRet"):
        val = structured.get(key) or rpc_result.get(key)
        if val is not None:
            sec_rets = val
            break

    if not sec_rets:
        return

    fail(f"安全审核未通过: {json.dumps(sec_rets, ensure_ascii=False)}", code=403)


def b64encode_text(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def b64encode_file(path: str) -> str:
    full_path = os.path.abspath(path)
    if not os.path.isfile(full_path):
        fail(f"文件不存在: {full_path}")
    with open(full_path, "rb") as f:
        content = f.read()
    if not content:
        fail(f"文件内容为空: {full_path}")
    return base64.b64encode(content).decode("ascii")


def maybe_b64decode(value: str):
    if not isinstance(value, str) or not value:
        return value
    try:
        raw = base64.b64decode(value, validate=True)
        return raw.decode("utf-8")
    except Exception:
        return value


def should_decode_text_key(key: str) -> bool:
    normalized = key.lower().replace("_", "")
    if "bytes" in normalized:
        return True
    return normalized in {
        "channelname",
        "guildname",
        "nickname",
        "membername",
        "profile",
        "guildnumber",
        "city",
        "province",
        "country",
    }


def decode_bytes_fields(obj):
    if isinstance(obj, list):
        return [decode_bytes_fields(item) for item in obj]
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                out[key] = decode_bytes_fields(value)
            elif isinstance(value, str) and should_decode_text_key(key):
                out[key] = maybe_b64decode(value)
            else:
                out[key] = value
        return out
    return obj


# ── 时间戳人类可读化 ──────────────────────────────────────────────
_BEIJING_TZ = timezone(timedelta(hours=8))

# 匹配的时间戳字段名（snake_case / camelCase 均覆盖），值为 Unix 秒级整数或数字字符串
_TIMESTAMP_FIELD_NAMES = {
    # 加入时间
    "join_time", "joinTime",
    "uint32JoinTime", "uint32_join_time",
    "uint64JoinTime", "uint64_join_time",
    # 创建时间
    "create_time", "createTime",
    "uint32CreateTime", "uint32_create_time",
    "uint64CreateTime", "uint64_create_time",
    # 禁言到期时间
    "shutup_expire_time", "shutupExpireTime",
    "uint32ShutupExpireTime", "uint32_shutup_expire_time",
    "uint64ShutupExpireTime", "uint64_shutup_expire_time",
    "time_stamp", "timeStamp",
}


def _ts_to_human(value, field_name: str) -> str | None:
    """将 Unix 秒级时间戳转为 'YYYY-MM-DD HH:MM:SS (北京时间)' 字符串。

    返回 None 表示不可转换或无意义。
    """
    try:
        ts = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if ts < 0:
        return None
    # 0 在禁言场景表示"未禁言/已解除"
    if ts == 0:
        lower = field_name.lower().replace("_", "")
        if "shutup" in lower or "timestamp" in lower:
            return "无禁言"
        return None
    # 合理范围：2000-01-01 ~ 2100-01-01
    if ts < 946684800 or ts > 4102444800:
        return None
    dt = datetime.fromtimestamp(ts, tz=_BEIJING_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def humanize_timestamps(obj):
    """递归遍历 dict/list，对已知时间戳字段追加 '{key}_human' 可读值。

    原始字段保持不变，方便回传给接口；仅新增 _human 后缀字段供 AI 阅读。
    """
    if isinstance(obj, list):
        return [humanize_timestamps(item) for item in obj]
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                out[key] = humanize_timestamps(value)
            else:
                out[key] = value
                if key in _TIMESTAMP_FIELD_NAMES:
                    human = _ts_to_human(value, key)
                    if human is not None:
                        out[f"{key}_human"] = human
        return out
    return obj


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def to_camel_keys(obj):
    if isinstance(obj, dict):
        return {_snake_to_camel(key): to_camel_keys(val) for key, val in obj.items()}
    if isinstance(obj, list):
        return [to_camel_keys(item) for item in obj]
    return obj


def get_mcporter_service_name() -> str:
    return os.environ.get(MCPORTER_SERVICE_ENV, "").strip() or DEFAULT_MCPORTER_SERVICE_NAME


def skill_root_dir() -> Path:
    """本 skill 根目录（SKILL.md 所在目录）。"""
    return Path(__file__).resolve().parent.parent.parent


def default_dotenv_path() -> Path:
    """OpenClaw 约定：用户主目录下 ~/.openclaw/.env（目录可在写入时自动创建）。"""
    return (Path.home() / ".openclaw" / ".env").resolve()


def get_dotenv_path() -> Path:
    override = os.environ.get(DOTENV_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return default_dotenv_path()


def read_token_from_dotenv(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[7:].strip()
        key_part = f"{DOTENV_TOKEN_KEY}="
        key_part_sp = f"{DOTENV_TOKEN_KEY} ="
        if s.startswith(key_part):
            val = s[len(key_part) :].strip()
        elif s.startswith(key_part_sp):
            val = s[len(key_part_sp) :].strip()
        else:
            continue
        if val.startswith('"') and val.endswith('"') and len(val) >= 2:
            inner = val[1:-1]
            val = (
                inner.replace("\\\\", "\\")
                .replace('\\"', '"')
            )
        elif val.startswith("'") and val.endswith("'") and len(val) >= 2:
            val = val[1:-1]
        val = val.strip()
        return val or None
    return None


def write_dotenv_qq_token(path: Path, token: str) -> None:
    if "\n" in token or "\r" in token:
        fail("token 不能包含换行符")
    escaped = token.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'{DOTENV_TOKEN_KEY}="{escaped}"'
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            fail(f"读取 {path} 失败: {exc}", code=200)
    out: list[str] = []
    replaced = False
    for line in lines:
        s = line.strip()
        if not s:
            out.append(line)
            continue
        if s.startswith("#"):
            out.append(line)
            continue
        t = s
        if t.startswith("export "):
            t = t[7:].strip()
        if t.startswith(f"{DOTENV_TOKEN_KEY}=") or t.startswith(f"{DOTENV_TOKEN_KEY} ="):
            if not replaced:
                out.append(new_line)
                replaced = True
            continue
        out.append(line)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        joined = "\n".join(out)
        if _DOTENV_WARNING not in joined:
            out.append(_DOTENV_WARNING)
        out.append(new_line)
    try:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError as exc:
        fail(f"写入 {path} 失败: {exc}", code=200)


def run_mcporter_config_add(token: str) -> tuple[bool, str]:
    svc = get_mcporter_service_name()
    try:
        proc = subprocess.run(
            [
                "mcporter",
                "config",
                "add",
                svc,
                MCP_SERVER_URL,
                "--header",
                f"Authorization=Bearer {token}",
                "--transport",
                "http",
                "--scope",
                "home",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except FileNotFoundError:
        return (
            False,
            "ERROR:mcporter_not_found — 未找到 mcporter 命令。请先安装 Node.js，再执行：npm install -g mcporter",
        )
    except Exception as exc:
        return False, str(exc)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "mcporter config add 失败").strip()
        return False, msg
    return True, ""


def persist_token_to_dotenv_and_mcporter(token: str) -> dict:
    """写入 .env 并注册 mcporter；返回结构化结果（不含 token）。"""
    path = get_dotenv_path()
    write_dotenv_qq_token(path, token)
    ok_mp, mp_msg = run_mcporter_config_add(token)
    return {
        "dotenvPath": str(path),
        "dotenvWritten": True,
        "mcporterOk": ok_mp,
        "mcporterMessage": "已注册 mcporter" if ok_mp else mp_msg,
        "mcporterService": get_mcporter_service_name(),
    }


def token_missing_fail_message() -> str:
    dot = get_dotenv_path()
    return (
        f"未找到鉴权 token（已查 .env → mcporter）。\n"
        f"请前往 {TOKEN_HELP_URL} 获取 token 后执行：\n"
        f"  bash scripts/token/setup.sh '<token>'\n"
        f"  （在 skill 根目录执行；会写入 `{dot}` 并注册 mcporter；若目录/文件不存在会自动创建）\n"
        f"配置后自检：在 skill 根目录执行 `bash scripts/token/verify.sh`（或 `python3 {VERIFY_SCRIPT_REL} </dev/null`）。\n"
        f"若需改用其它 .env 路径，可设置环境变量 {DOTENV_PATH_ENV}。"
    )


def _parse_authorization_from_mcporter_output(text: str) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        m = re.match(r"^\s*Authorization:\s*(.+)$", line, re.IGNORECASE)
        if not m:
            continue
        val = m.group(1).strip()
        if val.lower().startswith("bearer "):
            val = val[7:].strip()
        return val or None
    return None


def token_from_mcporter() -> str | None:
    svc = get_mcporter_service_name()
    try:
        proc = subprocess.run(
            ["mcporter", "config", "get", svc],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError:
        return None
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return _parse_authorization_from_mcporter_output(proc.stdout or "")


def try_resolve_token() -> tuple[str | None, str | None]:
    """实现 get_token() → .env → mcporter：先读 .env 文件，再 mcporter config get。"""
    dot = read_token_from_dotenv(get_dotenv_path())
    if dot:
        return dot, "dotenv"
    mp = token_from_mcporter()
    if mp:
        return mp, "mcporter"
    return None, None


def get_token() -> str:
    """【get_token() → .env → mcporter】：无 token 时 fail(code=100)。"""
    token, _src = try_resolve_token()
    if not token:
        fail(token_missing_fail_message(), code=100)
    return token


def _ret_code_int(ret_code: object | None) -> int | None:
    if ret_code is None:
        return None
    try:
        return int(str(ret_code).strip())
    except (TypeError, ValueError):
        return None


def is_likely_token_auth_failure(message: str | None, ret_code: object | None = None) -> bool:
    """根据网关/MCP 返回判断是否为 token / Authorization 鉴权类错误（实测无效 token 常见 retCode=8011）。"""
    rc = _ret_code_int(ret_code)
    if rc in (8011, 100007, 401):
        return True
    t = (message or "").lower()
    if re.search(r"retcode\s*[=:]\s*(8011|100007)\b", t):
        return True
    needles = (
        "auth failed",
        "hulian auth failed",
        "invalid authorization",
        "invalid authorization header",
        "decode ticket fail",
        "invalid ticket",
        "token expired",
        "unauthorized",
        "not authorized",
    )
    return any(n in t for n in needles)


def build_known_issue_hint(message: str, ret_code: object | None = None) -> str:
    if is_likely_token_auth_failure(message, ret_code):
        return (
            f"疑似 token 鉴权失败或票据无效。请到 {TOKEN_HELP_URL} 获取或更新 token，"
            "并执行 `bash scripts/token/setup.sh \\'<token>\\'`（在 skill 根目录）。"
        )
    text = (message or "").lower()
    if "agent不能被禁言" in message or "can not kick agent" in text:
        return "这是业务限制，不是 skill 调用链路问题。请改测非 agent 成员。"
    return ""


def http_post_ex(
    url: str, payload: dict, headers: dict, timeout: int = 30
) -> tuple[bool, dict | str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        return False, f"HTTP {exc.code}: {body}"
    except urllib.error.URLError as exc:
        return False, f"网络请求失败: {exc.reason}"


def http_post(url: str, payload: dict, headers: dict, timeout: int = 30) -> dict:
    ok, data = http_post_ex(url, payload, headers, timeout)
    if not ok:
        fail(str(data), code=200 if "HTTP" in str(data) else 300)
    assert isinstance(data, dict)
    return data


def _build_mcp_headers() -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_token()}",
        "X-Forwarded-Method": "POST",
    }
    cookie = get_test_cookie() if get_test_cookie else None
    if cookie:
        headers["Cookie"] = cookie
    return headers


def call_mcp_ex(tool_name: str, arguments: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": to_camel_keys(arguments),
        },
    }
    post_ok, result = http_post_ex(
        MCP_SERVER_URL,
        payload,
        _build_mcp_headers(),
    )
    if not post_ok:
        raise MCPUserError(str(result), code=200)

    assert isinstance(result, dict)
    if "error" in result:
        error = result["error"]
        if isinstance(error, dict):
            err_msg = str(error.get("message", "") or "")
            err_code = error.get("code")
            hint = build_known_issue_hint(err_msg, err_code)
            suffix = f" 诊断建议：{hint}" if hint else ""
            raise MCPUserError(
                f"MCP error {error.get('code', '')}: {err_msg}{suffix}",
                code=200,
            )
        raise MCPUserError(f"MCP error: {error}", code=200)

    rpc_result = result.get("result", {})
    if not isinstance(rpc_result, dict):
        raise MCPUserError(
            f"MCP 返回格式异常: {json.dumps(result, ensure_ascii=False)}",
            code=200,
        )

    meta = rpc_result.get("_meta", {})
    additional = meta.get("AdditionalFields", {}) if isinstance(meta, dict) else {}
    ret_code = additional.get("retCode")
    if ret_code not in (None, 0):
        err_msg = additional.get("errMsg") or json.dumps(rpc_result, ensure_ascii=False)
        hint = build_known_issue_hint(err_msg, ret_code)
        suffix = f" 诊断建议：{hint}" if hint else ""
        raise MCPUserError(
            f"MCP 调用失败，retCode={ret_code}: {err_msg}{suffix}",
            code=_ret_code_int(ret_code) or 200,
        )
    return rpc_result


def call_mcp(tool_name: str, arguments: dict) -> dict:
    try:
        return call_mcp_ex(tool_name, arguments)
    except MCPUserError as exc:
        fail(exc.message, code=exc.code)


def verify_token_and_mcp_connectivity() -> dict:
    """自检 token 与 MCP，不退出进程；响应中不包含 token 明文。

    探测调用与 get_user_info.py「查自己·全局」一致：不传 guild_id / member_tinyid，仅带 msg_filter。
    """
    token, source = try_resolve_token()
    if not token:
        return {
            "valid": False,
            "tokenResolved": False,
            "tokenSource": None,
            "mcpReachable": False,
            "mcpServerUrl": MCP_SERVER_URL,
            "probeTool": "get_user_info",
            "mcporterService": get_mcporter_service_name(),
            "likelyTokenAuthFailure": False,
            "message": "未找到 token，请配置 .env 或 mcporter。",
            "diagnosis": token_missing_fail_message(),
            "tokenHelpUrl": TOKEN_HELP_URL,
        }

    probe_args = {
        "msg_filter": {
            "uint32_nick_name": 1,
            "uint32_gender": 1,
            "uint32_country": 1,
            "uint32_province": 1,
            "uint32_city": 1,
            "uint32_is_guild_author": 1,  # 频道创作者身份
        },
    }
    try:
        result = call_mcp_ex("get_user_info", probe_args)
    except MCPUserError as exc:
        likely = is_likely_token_auth_failure(exc.message, None)
        diag = exc.message
        if likely:
            diag = (
                f"{exc.message}\n"
                f"判断为疑似 token 鉴权问题。请到 {TOKEN_HELP_URL} 获取或更新 token，"
                "并执行 `bash scripts/token/setup.sh \\'<token>\\'`。"
            )
        else:
            diag = f"MCP 探测失败：{exc.message}"
        return {
            "valid": False,
            "tokenResolved": True,
            "tokenSource": source,
            "mcpReachable": True,
            "mcpServerUrl": MCP_SERVER_URL,
            "probeTool": "get_user_info",
            "mcporterService": get_mcporter_service_name(),
            "likelyTokenAuthFailure": likely,
            "message": exc.message,
            "diagnosis": diag,
            "tokenHelpUrl": TOKEN_HELP_URL,
        }

    sc = result.get("structuredContent", result)
    profile_ok = isinstance(sc, dict) and bool(sc)
    return {
        "valid": True,
        "tokenResolved": True,
        "tokenSource": source,
        "mcpReachable": True,
        "userProfileProbeOk": profile_ok,
        "mcpServerUrl": MCP_SERVER_URL,
        "probeTool": "get_user_info",
        "mcporterService": get_mcporter_service_name(),
        "likelyTokenAuthFailure": False,
        "message": "token 已解析，已通过「查询当前用户资料」完成 MCP 探测。",
        "diagnosis": "可继续执行频道管理类工具。",
        "tokenHelpUrl": TOKEN_HELP_URL,
    }


def _parse_share_message_object(result: dict) -> dict:
    content = result.get("content")
    if not isinstance(content, list):
        return {}
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or ":" not in text:
            continue
        payload = text.split(":", 1)[1].strip()
        if not payload.startswith("{"):
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _parse_share_text_value(result: dict, field_names: tuple[str, ...]) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        for field_name in field_names:
            pattern = rf'"{re.escape(field_name)}"\s*:\s*"([^"]+)"'
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    return ""


def parse_share_url_from_mcp_result(rpc_result: dict) -> tuple[str, str]:
    """从 get_share_url 的 MCP result 解析 url 与 shareInfo（假定已通过 call_mcp 业务校验）。"""
    structured = rpc_result.get("structuredContent")
    message_obj = _parse_share_message_object(rpc_result)
    parsed = structured if isinstance(structured, dict) else message_obj
    if not isinstance(parsed, dict):
        parsed = {}

    url = ""
    share_info = ""
    for key in ("url", "shareUrl"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            url = value.strip()
            break
    for key in ("share_info", "shareInfo"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            share_info = value.strip()
            break

    if not url:
        url = _parse_share_text_value(rpc_result, ("url", "shareUrl"))
    if not share_info:
        share_info = _parse_share_text_value(rpc_result, ("share_info", "shareInfo"))
    return url, share_info


def fetch_guild_share_url(guild_id: str) -> str:
    """获取频道分享短链，失败返回空字符串。不会中断主流程。"""
    try:
        result = call_mcp(
            "get_share_url",
            {"guild_id": str(guild_id), "is_short_link": True},
        )
        url, _share = parse_share_url_from_mcp_result(result)
        return url
    except (SystemExit, Exception):
        return ""
