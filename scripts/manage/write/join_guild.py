#!/usr/bin/env python3
"""加入频道：自动预检加入设置，需要验证时引导 AI 向用户收集信息。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import (  # noqa: E402
    MCPUserError,
    call_mcp,
    call_mcp_ex,
    decode_bytes_fields,
    ok,
    fail,
    optional_str,
    parse_positive_int,
    read_input,
)

_DIRECT_JOIN_TYPES = {
    "JOIN_GUILD_TYPE_UNKNOWN", "0",
    "JOIN_GUILD_TYPE_DIRECT", "1",
    "",
}

_DISABLED_JOIN_TYPES = {
    "JOIN_GUILD_TYPE_DISABLE", "3",
}

_COMMENT_TYPES = {
    "JOIN_GUILD_TYPE_ADMIN_AUDIT", "2",
    "JOIN_GUILD_TYPE_QUESTION", "4",
    "JOIN_GUILD_TYPE_QUESTION_WITH_ADMIN_AUDIT", "5",
}

_ANSWER_TYPES = {
    "JOIN_GUILD_TYPE_MULTI_QUESTION", "6",
    "JOIN_GUILD_TYPE_QUIZ", "7",
}


def _fetch_share_url(guild_id: str) -> str:
    try:
        result = call_mcp("get_share_url", {"guildId": guild_id, "isShortLink": True})
        sc = result.get("structuredContent", result)
        if isinstance(sc, dict):
            for key in ("url", "shareUrl"):
                val = sc.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return ""
    except (SystemExit, Exception):
        return ""


def _fetch_join_setting(guild_id: str) -> dict | None:
    try:
        result = call_mcp_ex("get_join_guild_setting", {"guild_id": guild_id})
        return decode_bytes_fields(result.get("structuredContent", result))
    except (MCPUserError, Exception):
        return None


def _get_join_type(setting: dict) -> str:
    return str((setting.get("setting") or {}).get("joinType", ""))


def _build_verification_hint(setting: dict) -> dict:
    s = setting.get("setting") or {}
    join_type = _get_join_type(setting)

    hint: dict = {
        "action": "need_verification",
        "join_type": join_type,
    }

    question = s.get("question") or {}
    q_items = question.get("items") or []
    if q_items:
        hint["questions"] = [
            {"question": item.get("question", "")} for item in q_items
        ]

    quiz = s.get("quiz") or {}
    quiz_items = quiz.get("items") or []
    if quiz_items:
        hint["quiz"] = [
            {
                "question": item.get("question", ""),
                "answers": item.get("answers", []),
            }
            for item in quiz_items
        ]
        min_answer = quiz.get("minAnswerNum")
        min_correct = quiz.get("minCorrectAnswerNum")
        if min_answer:
            hint["min_answer_num"] = min_answer
        if min_correct:
            hint["min_correct_answer_num"] = min_correct

    if join_type in _COMMENT_TYPES:
        if q_items:
            hint["message"] = (
                "该频道需要回答问题才能加入，"
                "请让用户查看以下问题并提供回答，填入 join_guild_comment 后重新调用。"
            )
        else:
            hint["message"] = (
                "该频道设置了管理员审核，"
                "请让用户提供一段加入附言，填入 join_guild_comment 后重新调用。"
            )
    elif join_type in _ANSWER_TYPES:
        if quiz_items:
            hint["message"] = (
                "该频道需要通过测试题才能加入，"
                "请让用户从选项中作答，将答案填入 join_guild_answers 后重新调用。"
            )
        else:
            hint["message"] = (
                "该频道需要回答问题才能加入，"
                "请让用户回答以下问题，将答案填入 join_guild_answers 后重新调用。"
            )
    else:
        hint["message"] = (
            "该频道需要验证才能加入（join_type=%s），"
            "请根据返回的验证信息向用户收集答案后重新调用。" % join_type
        )

    return hint


def _do_join(guild_id: str, params: dict) -> dict:
    mcp_args: dict = {"uint64_guild_id": guild_id}

    answers = params.get("join_guild_answers")
    if isinstance(answers, list) and answers:
        mcp_args["join_guild_answers"] = answers

    comment = optional_str(params, "join_guild_comment")
    if comment:
        mcp_args["join_guild_comment"] = comment

    result = call_mcp("join_guild", mcp_args)
    data = result.get("structuredContent", result)
    if not isinstance(data, dict):
        data = {}

    share_url = _fetch_share_url(guild_id)
    if share_url:
        data["share_url"] = share_url

    return data


def main():
    params = read_input()
    guild_id = str(parse_positive_int(params.get("guild_id"), "参数 guild_id"))

    has_answers = isinstance(params.get("join_guild_answers"), list) and params["join_guild_answers"]
    has_comment = bool(optional_str(params, "join_guild_comment"))

    if has_answers or has_comment:
        ok(_do_join(guild_id, params))
        return

    setting = _fetch_join_setting(guild_id)

    if setting is None:
        ok(_do_join(guild_id, params))
        return

    join_type = _get_join_type(setting)

    if join_type in _DISABLED_JOIN_TYPES:
        fail("当前频道不允许被加入")
        return

    if join_type in _DIRECT_JOIN_TYPES:
        ok(_do_join(guild_id, params))
        return

    ok(_build_verification_hint(setting))


if __name__ == "__main__":
    main()
