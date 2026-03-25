"""
StRichText protobuf 解析工具。

评论/回复的 content 字段是 base64 编码的 StRichText protobuf 二进制数据。

StRichText 结构（base/protocol_meta.proto）：
    repeated StRichTextContent contents = 1
    repeated StImage            images   = 2  // 图片列表
    optional BaseEmoji          sticker  = 3  // 表情包（与图片互斥）

StRichTextContent.type（RICH_TEXT_CONTENT_TYPE）：
    1=TEXT   text_content   = 3  → StRichTextTextContent.text=1
    2=AT     at_content     = 4  → StRichTextAtContent.user=4 → StUser(id=1, nick=2)
    3=URL    url_content    = 5  → StRichTextURLContent.displayText=2 / url=1
    4=EMOJI  emoji_content  = 6  → StRichTextEmojiContent.name=3
    5=CH     channel_content= 7  （子频道，跳过）
    6=GUILD  guild_content  = 8  （频道，跳过）
    7=ICON   icon_content   = 9  → StRichTextIconContent.url=1
    8=TOPIC  topic_content  =10  → StRichTextTopicContent.topic_name=2

StImage.picUrl = 3
BaseEmoji.market_face.bytes_face_name = 1（bytes, UTF-8）

本模块提供 decode_richtext(b64_str) -> dict，返回：
    {
        "text":     str,           # 拼接后的纯文本（含 @昵称、#话题、[表情] 等占位）
        "images":   [str, ...],    # 图片 URL 列表
        "sticker":  str | None,    # 表情包名称（若有）
        "at_users": [              # 被@的用户列表（type=2 AT节点）
            {"id": str, "nick": str},
            ...
        ],
    }
为兼容旧调用，同时保留 decode_richtext_content(b64_str) -> str 只返回文本。
"""

import base64


# ──────────────────────────────────────────────
# 底层 protobuf 工具
# ──────────────────────────────────────────────

def _decode_varint(data: bytes, pos: int):
    result, shift = 0, 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _read_bytes(data: bytes, pos: int):
    length, pos = _decode_varint(data, pos)
    return data[pos:pos + length], pos + length


def _read_str(data: bytes, pos: int):
    raw, pos = _read_bytes(data, pos)
    return raw.decode("utf-8", errors="replace"), pos


def _skip(data: bytes, pos: int, wire_type: int) -> int:
    if wire_type == 0:
        _, pos = _decode_varint(data, pos)
    elif wire_type == 1:
        pos += 8
    elif wire_type == 2:
        _, pos = _read_bytes(data, pos)
    elif wire_type == 5:
        pos += 4
    return pos


def _iter_fields(data: bytes):
    """遍历 protobuf message，yield (field_num, wire_type, value)。
    wire_type=0: value=int; wire_type=2: value=bytes; 其他跳过。"""
    pos = 0
    while pos < len(data):
        tag, pos = _decode_varint(data, pos)
        field_num, wire_type = tag >> 3, tag & 0x7
        if wire_type == 0:
            val, pos = _decode_varint(data, pos)
            yield field_num, 0, val
        elif wire_type == 2:
            val, pos = _read_bytes(data, pos)
            yield field_num, 2, val
        elif wire_type == 1:
            pos += 8
        elif wire_type == 5:
            pos += 4
        else:
            break


def _get_str_field(data: bytes, target_field: int) -> str:
    """从 message bytes 中取指定 field（string 类型）的值。"""
    for fnum, wtype, val in _iter_fields(data):
        if fnum == target_field and wtype == 2:
            return val.decode("utf-8", errors="replace")
    return ""


def _get_bytes_field(data: bytes, target_field: int) -> bytes:
    for fnum, wtype, val in _iter_fields(data):
        if fnum == target_field and wtype == 2:
            return val
    return b""


# ──────────────────────────────────────────────
# 各 content 类型解析
# ──────────────────────────────────────────────

def _parse_text_content(data: bytes) -> str:
    """StRichTextTextContent: text=1"""
    return _get_str_field(data, 1)


def _parse_at_content(data: bytes) -> str:
    """StRichTextAtContent: user=4 → StUser.nick=2"""
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 4 and wtype == 2:
            nick = _get_str_field(val, 2)
            return f"@{nick}" if nick else "@"
    return "@"


def _parse_at_content_user(data: bytes) -> dict:
    """StRichTextAtContent: user=4 → StUser(id=1, nick=2)，返回结构化用户信息"""
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 4 and wtype == 2:
            uid  = _get_str_field(val, 1)
            nick = _get_str_field(val, 2)
            return {"id": uid, "nick": nick}
    return {}


def _parse_url_content(data: bytes) -> str:
    """StRichTextURLContent: displayText=2, url=1"""
    display, url = "", ""
    for fnum, wtype, val in _iter_fields(data):
        if wtype == 2:
            if fnum == 2:
                display = val.decode("utf-8", errors="replace")
            elif fnum == 1:
                url = val.decode("utf-8", errors="replace")
    return display or url


def _parse_emoji_content(data: bytes) -> str:
    """StRichTextEmojiContent: name=3"""
    name = _get_str_field(data, 3)
    return f"[{name}]" if name else "[表情]"


def _parse_icon_content(data: bytes) -> str:
    """StRichTextIconContent: url=1"""
    url = _get_str_field(data, 1)
    return f"[图片:{url}]" if url else "[图片]"


def _parse_topic_content(data: bytes) -> str:
    """StRichTextTopicContent: topic_name=2"""
    name = _get_str_field(data, 2)
    return f"#{name}" if name else "#话题"


# content type → 解析函数（对应 RICH_TEXT_CONTENT_TYPE field 编号）
_CONTENT_PARSERS = {
    3:  _parse_text_content,   # type=1 TEXT,  field=3
    4:  _parse_at_content,     # type=2 AT,    field=4
    5:  _parse_url_content,    # type=3 URL,   field=5
    6:  _parse_emoji_content,  # type=4 EMOJI, field=6
    9:  _parse_icon_content,   # type=7 ICON,  field=9
    10: _parse_topic_content,  # type=8 TOPIC, field=10
}


def _parse_at_content_combined(data: bytes) -> tuple:
    """单次迭代解析 AT content，同时提取文本和用户信息。
    合并 _parse_at_content 与 _parse_at_content_user 的两次独立迭代为一次。
    返回 (text, user_dict_or_None)。
    """
    for fnum, wtype, val in _iter_fields(data):
        if fnum == 4 and wtype == 2:
            uid  = _get_str_field(val, 1)
            nick = _get_str_field(val, 2)
            text = f"@{nick}" if nick else "@"
            user = {"id": uid, "nick": nick} if (uid or nick) else None
            return text, user
    return "@", None


def _parse_richtext_content_node(data: bytes) -> tuple:
    """解析单个 StRichTextContent 节点，返回 (text_fragment, at_user_or_None)。"""
    for fnum, wtype, val in _iter_fields(data):
        if wtype == 2:
            if fnum == 4:  # AT field，单次解析同时提取 text 和 user
                return _parse_at_content_combined(val)
            if fnum in _CONTENT_PARSERS:
                return _CONTENT_PARSERS[fnum](val), None
    return "", None


# ──────────────────────────────────────────────
# StRichText 顶层解析
# ──────────────────────────────────────────────

def _parse_image(data: bytes) -> str:
    """StImage: picUrl=3"""
    return _get_str_field(data, 3)


def _parse_sticker(data: bytes) -> dict:
    """
    BaseEmoji:
      field=1 emoji_type (varint)
      field=2 market_face → bytes_face_name=1（UTF-8 name）
      field=3 custom_face → file_name=4, pic_width=6, pic_height=7, origin_image_url=14

    返回结构化 dict：
        {"url": str, "name": str, "type": "market_face"|"custom_face", "width": int, "height": int}
    """
    emoji_type = 0
    result = {"url": "", "name": "", "type": "", "width": 0, "height": 0}

    for fnum, wtype, val in _iter_fields(data):
        if fnum == 1 and wtype == 0:
            emoji_type = val
        elif fnum == 2 and wtype == 2:  # market_face
            name_bytes = _get_bytes_field(val, 1)
            name = name_bytes.decode("utf-8", errors="replace") if name_bytes else "[商城表情]"
            result["type"] = "market_face"
            result["name"] = name
        elif fnum == 3 and wtype == 2:  # custom_face
            result["type"] = "custom_face"
            for f2, wt2, v2 in _iter_fields(val):
                if wt2 == 2:
                    if f2 == 4:   # file_name
                        result["name"] = v2.decode("utf-8", errors="replace")
                    elif f2 == 14:  # origin_image_url
                        result["url"] = v2.decode("utf-8", errors="replace")
                elif wt2 == 0:
                    if f2 == 6:   # pic_width
                        result["width"] = v2
                    elif f2 == 7:  # pic_height
                        result["height"] = v2

    if not result["type"]:
        result["type"] = "custom_face" if emoji_type == 2 else "market_face"
    if not result["name"]:
        result["name"] = "[表情包]"
    return result


def decode_richtext(b64_str: str) -> dict:
    """
    将 base64 编码的 StRichText protobuf 解码为结构化结果。

    返回:
        {
            "text":     str,           # 拼接纯文本，含 @昵称/#话题/[表情] 占位
            "images":   [str, ...],    # 图片 URL 列表（StRichText.images）
            "sticker":  dict | None,   # 表情包信息（有则含 url/name/type/width/height）
            "at_users": [              # 被@的用户列表，每项 {"id": str, "nick": str}
                {"id": "...", "nick": "..."},
            ],
        }
    解析失败时返回 {"text": b64_str, "images": [], "sticker": None, "at_users": []}
    """
    fallback = {"text": b64_str, "images": [], "sticker": None, "at_users": []}
    if not b64_str:
        return {"text": "", "images": [], "sticker": None, "at_users": []}
    try:
        raw = base64.b64decode(b64_str)
    except Exception:
        return fallback

    parts = []
    images = []
    sticker = None
    at_users = []

    try:
        for fnum, wtype, val in _iter_fields(raw):
            if wtype != 2:
                continue
            if fnum == 1:   # StRichTextContent
                text, at_user = _parse_richtext_content_node(val)
                if text:
                    parts.append(text)
                if at_user:
                    at_users.append(at_user)
            elif fnum == 2:  # StImage
                url = _parse_image(val)
                if url:
                    images.append(url)
            elif fnum == 3:  # BaseEmoji sticker
                sticker = _parse_sticker(val)
    except Exception:
        return fallback

    return {
        "text":     "".join(parts),
        "images":   images,
        "sticker":  sticker,
        "at_users": at_users,
    }


def decode_richtext_content(b64_str: str) -> str:
    """兼容旧接口，只返回文本部分。"""
    return decode_richtext(b64_str)["text"]


def _decode_richtext_content_node_dict(node: dict) -> tuple:
    """解析单个 StRichTextContent dict 节点，返回 (text_fragment, at_user_or_None)。

    MCP 返回的节点可能是 camelCase（feed title/contents）或 snake_case（richContents），两种均支持：
        {'type': 1, 'textContent': {'text': '你好'}}       # camelCase
        {'type': 1, 'text_content': {'text': '你好'}}      # snake_case
        {'type': 2, 'atContent': {'user': {'id': '...', 'nick': '张三'}}}
        {'type': 2, 'at_content': {'user': {'id': '...', 'nick': '张三'}}}
        {'type': 3, 'urlContent': {'displayText': '链接', 'url': 'https://...'}}
        {'type': 4, 'emojiContent': {'name': '微笑'}}
        {'type': 7, 'iconContent': {'url': 'https://...'}}
        {'type': 8, 'topicContent': {'topicName': '话题'}}
    """
    content_type = node.get("type")
    if content_type == 1:  # TEXT
        tc = node.get("textContent") or node.get("text_content") or {}
        return tc.get("text", ""), None
    if content_type == 2:  # AT
        at = node.get("atContent") or node.get("at_content") or {}
        user_obj = at.get("user", {})
        nick = user_obj.get("nick", "")
        uid  = user_obj.get("id", "")
        at_user = {"id": uid, "nick": nick} if (uid or nick) else None
        return (f"@{nick}" if nick else "@"), at_user
    if content_type == 3:  # URL
        uc = node.get("urlContent") or node.get("url_content") or {}
        return uc.get("displayText") or uc.get("url", ""), None
    if content_type == 4:  # EMOJI
        ec = node.get("emojiContent") or node.get("emoji_content") or {}
        name = ec.get("name", "")
        return (f"[{name}]" if name else "[表情]"), None
    if content_type == 7:  # ICON
        ic = node.get("iconContent") or node.get("icon_content") or {}
        url = ic.get("url", "")
        return (f"[图片:{url}]" if url else "[图片]"), None
    if content_type == 8:  # TOPIC
        tc = node.get("topicContent") or node.get("topic_content") or {}
        name = tc.get("topicName") or tc.get("topic_name") or ""
        return (f"#{name}" if name else "#话题"), None
    return "", None


def decode_richtext_dict(obj) -> dict:
    """
    将 MCP 返回的已反序列化 StRichText dict 解码为结构化结果。

    入参可以是：
        - dict，例如 {'contents': [...], 'images': [...], 'sticker': {...}}
        - str（base64），自动回退到 decode_richtext()

    返回：
        {
            "text":     str,           # 拼接纯文本
            "images":   [str, ...],    # 图片 URL 列表
            "sticker":  dict | None,   # 表情包信息（含 url/name/type/width/height），无则 None
            "at_users": [              # 被@的用户列表，每项 {"id": str, "nick": str}
                {"id": "...", "nick": "..."},
            ],
        }
    """
    if obj is None:
        return {"text": "", "images": [], "sticker": None, "at_users": []}
    # 若是字符串则交给原有 base64 解码路径
    if isinstance(obj, str):
        return decode_richtext(obj)
    if not isinstance(obj, dict):
        return {"text": str(obj), "images": [], "sticker": None, "at_users": []}

    parts = []
    at_users = []
    for node in obj.get("contents") or []:
        fragment, at_user = _decode_richtext_content_node_dict(node)
        if fragment:
            parts.append(fragment)
        if at_user:
            at_users.append(at_user)

    images = [
        img["picUrl"]
        for img in (obj.get("images") or [])
        if isinstance(img, dict) and img.get("picUrl")
    ]

    sticker = None
    sticker_obj = obj.get("sticker")
    if isinstance(sticker_obj, dict):
        # custom_face（snake_case，来自 richContents 直接反序列化）
        cf = sticker_obj.get("custom_face") or sticker_obj.get("customFace")
        if isinstance(cf, dict):
            sticker = {
                "type":   "custom_face",
                "url":    cf.get("origin_image_url") or cf.get("originImageUrl") or "",
                "name":   cf.get("file_name") or cf.get("fileName") or cf.get("file_uuid") or cf.get("fileUuid") or "[表情包]",
                "width":  cf.get("pic_width") or cf.get("picWidth") or 0,
                "height": cf.get("pic_height") or cf.get("picHeight") or 0,
            }
        else:
            # market_face
            mf = sticker_obj.get("market_face") or sticker_obj.get("marketFace") or {}
            if isinstance(mf, dict):
                name_raw = mf.get("bytes_face_name") or mf.get("bytesFaceName") or "[商城表情]"
                if isinstance(name_raw, (bytes, bytearray)):
                    name_raw = name_raw.decode("utf-8", errors="replace")
                sticker = {
                    "type":   "market_face",
                    "url":    "",
                    "name":   name_raw,
                    "width":  mf.get("width") or mf.get("uint32_image_width") or 0,
                    "height": mf.get("height") or mf.get("uint32_image_height") or 0,
                }
            elif sticker_obj:
                sticker = {"type": "unknown", "url": "", "name": "[表情包]", "width": 0, "height": 0}

    return {
        "text":     "".join(parts),
        "images":   images,
        "sticker":  sticker,
        "at_users": at_users,
    }

