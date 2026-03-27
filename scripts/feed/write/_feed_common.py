"""
_feed_common.py — 帖子内容构建公共工具

供 publish_feed.py 和 alter_feed.py 共同使用，消除重复实现。
包含：
  - make_pattern_info_long()  长贴 patternInfo JSON 生成
  - make_pattern_info_short() 短贴 patternInfo JSON 生成
  - make_pattern_info()       统一调度入口（按 feed_type 选择）
  - make_contents()           jsonFeed.contents.contents 数组构建

行为基准：以 alter_feed 版本为准（防御性 .get()，uuid block id，更完整的 fallback）。
"""

import json
import time
import uuid


# ── patternInfo 节点类型常量 ──────────────────────────────────────────────────
_NODE_TEXT     = 1   # 文本
_NODE_AT       = 3   # @用户
_NODE_IMAGE    = 6   # 图片
_NODE_VIDEO    = 7   # 视频
_NODE_END      = 11  # 段落结束占位节点


def _normalize_newlines(text: str) -> str:
    """统一换行符：将字面量 \\n（agent 有时会传转义字符串）替换为真正的换行符。
    防御 agent 把 content 里的换行符转义成 \\n 导致 split('\\n') 失效、
    整篇内容被压成 1 个节点，手机编辑器无法解析段落而显示空白。
    """
    return text.replace("\\n", "\n")


def _empty_node() -> dict:
    """短贴段落起始/结束的空占位节点（type=1 text=""）。"""
    return {"status": 0, "widthPercent": 0, "type": _NODE_TEXT,
            "text": "", "height": 0, "duration": 0, "width": 0}


def _header_empty_node() -> dict:
    """长贴首块的空占位节点（type=1，含 children:[]，对齐真实客户端格式）。"""
    return {"children": [], "text": "", "type": _NODE_TEXT}


def _end_node() -> dict:
    """段落结束节点（type=11），仅短贴使用。"""
    return {"status": 0, "widthPercent": 0, "type": _NODE_END,
            "height": 0, "duration": 0, "width": 0}


def _at_node(u: dict, index: int) -> dict:
    """patternInfo 中的 @用户 节点（type=3）。"""
    return {
        "user":         {"id": str(u.get("id", "")), "nick": u.get("nick", "")},
        "id":           str(index),
        "status":       0,
        "widthPercent": 0,
        "type":         _NODE_AT,
        "height":       0,
        "duration":     0,
        "width":        0,
    }


def _image_node(img: dict, idx: int, ts_ms: int) -> dict:
    """patternInfo 中的图片节点（type=6）。"""
    pic_id = img.get("task_id") or img.get("md5", str(ts_ms))
    return {
        "type":             _NODE_IMAGE,
        "width":            img.get("width", 0),
        "height":           img.get("height", 0),
        "widthPercentage":  100,
        "fileId":           pic_id,
        "url":              img.get("url", img.get("picUrl", "")),
        "id":               pic_id,
        "taskId":           pic_id,
        "status":           0,
        "duration":         0,
        "isInline":         True,
    }


def _video_node(v: dict, idx: int) -> dict:
    """patternInfo 中的视频节点（type=7）。"""
    vid_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", v.get("fileId", ""))
    return {
        "type":         _NODE_VIDEO,
        "width":        v.get("width", 0),
        "height":       v.get("height", 0),
        "widthPercent": 100,
        "fileId":       vid_id,
        "videoId":      vid_id,
        "taskId":       vid_id,
        "url":          v.get("url", v.get("playUrl", "")),
        "id":           str(idx + 1),
        "status":       0,
        "duration":     v.get("duration", 0),
    }


# ── patternInfo 生成 ──────────────────────────────────────────────────────────

def make_pattern_info_long(content: str, at_users: list,
                           images: list, videos: list) -> str:
    """
    生成长贴(feed_type=2)的 patternInfo JSON 字符串。

    结构（对齐真实客户端格式）：
      - block[0]：空白起始段（uuid id），data 含单个 children:[]/text:"" 节点
      - block[1..N]：正文按 \\n 拆分的段落（id=ts_ms+i）
        - 非空段落：data=[{type:1, text:..., props:{...}}]
          末段追加 AT 节点(type=3)、图片节点(type=6，含 isInline:true)、视频节点(type=7)
        - 空段落：data=[]
        - 注意：长贴段落末尾不追加 type=11 结束节点（type=11 仅短贴使用），
          否则编辑器解析失败，导致手机端编辑界面内容区空白。
    """
    ts_ms = int(time.time() * 1000)
    content = _normalize_newlines(content) if content else content
    paragraphs = content.split("\n") if content else [""]

    blocks = [
        {
            "id":   str(uuid.uuid4()).upper(),
            "type": "blockParagraph",
            "data": [_header_empty_node()],
        }
    ]

    for i, para in enumerate(paragraphs):
        is_last = (i == len(paragraphs) - 1)
        if not para and not is_last:
            # 空段落：data=[]，对齐客户端真实格式
            block_data = []
        else:
            block_data = []
            if para:
                block_data.append({
                    "type":  _NODE_TEXT,
                    "text":  para,
                    "props": {"fontWeight": 400, "italic": False, "underline": False},
                })
            if is_last:
                for j, u in enumerate(at_users or [], start=1):
                    block_data.append(_at_node(u, j))
                for idx, img in enumerate(images or []):
                    block_data.append(_image_node(img, idx, ts_ms))
                for idx, v in enumerate(videos or []):
                    block_data.append(_video_node(v, idx))

        blocks.append({
            "id":    str(ts_ms + i),
            "props": {"textAlignment": 0},
            "type":  "blockParagraph",
            "data":  block_data,
        })

    return json.dumps(blocks, ensure_ascii=False)


def make_pattern_info_short(content: str, at_users: list,
                            images: list, videos: list) -> str:
    """
    生成短贴(feed_type=1)的 patternInfo JSON 字符串。

    结构：
      - block[0]：空白起始段（uuid id）
      - block[1]：文本占位 + AT 节点(type=3) + 结束节点(type=11)（uuid id）
      - block[2..N]：每张图片 / 每个视频各占一个独立 blockParagraph（uuid id）
    """
    block1 = {
        "id":   str(uuid.uuid4()).upper(),
        "type": "blockParagraph",
        "data": [_empty_node()],
    }

    data2 = [
        {"props": {"textAlignment": 0}, "status": 0, "widthPercent": 0,
         "type": _NODE_TEXT, "height": 0, "duration": 0, "width": 0}
    ]
    for i, u in enumerate(at_users or [], start=1):
        data2.append(_at_node(u, i))
    data2.append(_end_node())

    block2 = {
        "id":    str(uuid.uuid4()).upper(),
        "props": {"textAlignment": 0},
        "type":  "blockParagraph",
        "data":  data2,
    }
    blocks = [block1, block2]

    for idx, img in enumerate(images or []):
        pic_id = img.get("task_id") or img.get("md5", "")
        blocks.append({
            "id":    str(uuid.uuid4()).upper(),
            "props": {"textAlignment": 0},
            "type":  "blockParagraph",
            "data":  [
                {
                    "taskId":          pic_id,
                    "id":              pic_id,
                    "fileId":          pic_id,
                    "status":          0,
                    "widthPercentage": 100,
                    "type":            _NODE_IMAGE,
                    "height":          img.get("height", 0),
                    "duration":        0,
                    "width":           img.get("width", 0),
                },
                _end_node(),
            ]
        })

    for idx, v in enumerate(videos or []):
        task_id = v.get("task_id") or v.get("video_id") or v.get("file_uuid", v.get("fileId", ""))
        blocks.append({
            "id":    str(uuid.uuid4()).upper(),
            "props": {"textAlignment": 0},
            "type":  "blockParagraph",
            "data":  [
                {
                    "taskId":       task_id,
                    "id":           str(idx + 1),
                    "fileId":       task_id,
                    "videoId":      task_id,
                    "status":       0,
                    "widthPercent": 100,
                    "type":         _NODE_VIDEO,
                    "height":       v.get("height", 0),
                    "duration":     v.get("duration", 0),
                    "width":        v.get("width", 0),
                },
                _end_node(),
            ]
        })

    return json.dumps(blocks, ensure_ascii=False)


def make_pattern_info(feed_type: int, content: str, at_users: list,
                      images: list, videos: list) -> str:
    """
    统一调度入口：按 feed_type 选择 long（2）或 short（1）生成器。

    参数:
        feed_type: 1=短贴，2=长贴
        content:   正文文本
        at_users:  被@用户列表，每项 {"id": str, "nick": str}
        images:    图片列表（含 task_id/md5/url/picUrl/width/height）
        videos:    视频列表（含 task_id/video_id/file_uuid/fileId/url/playUrl/width/height/duration）
    """
    if feed_type == 2:
        return make_pattern_info_long(content, at_users, images, videos)
    return make_pattern_info_short(content, at_users, images, videos)


# ── jsonFeed.contents.contents 构建 ──────────────────────────────────────────

def make_contents(text: str, at_users: list, feed_type: int = 1) -> list:
    """
    构造 jsonFeed.contents.contents 数组。

    顺序：文本节点在前，AT 节点在后（与 patternInfo 的 type=3 节点 id 一一对应）。
    AT 节点的 pattern_id 从 "1" 递增，与 patternInfo 里 type=3 节点的 id 对应。

    短贴(feed_type=1)：单个文本节点 + AT 节点列表。
    长贴(feed_type=2)：按 \\n 拆分为多个文本节点（与 patternInfo blockParagraph 块数对应），
                      AT 节点追加在最后一个文本节点之后。
    """
    def _at_content_node(u: dict, index: int) -> dict:
        return {
            "type": 2,
            "at_content": {
                "user": {
                    "id":   str(u.get("id", "")),
                    "nick": u.get("nick", ""),
                },
                "type": 1,
            },
            "pattern_id": str(index),
        }

    if feed_type == 2:
        text = _normalize_newlines(text) if text else text
        paragraphs = text.split("\n") if text else [""]
        nodes = [{"text_content": {"text": para}, "type": 1, "pattern_id": ""}
                 for para in paragraphs]
        for i, u in enumerate(at_users or [], start=1):
            nodes.append(_at_content_node(u, i))
        return nodes

    # feed_type == 1（短贴）
    nodes = []
    if text:
        text = _normalize_newlines(text)
        nodes.append({"text_content": {"text": text}, "type": 1, "pattern_id": ""})
    for i, u in enumerate(at_users or [], start=1):
        nodes.append(_at_content_node(u, i))
    return nodes
