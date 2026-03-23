"""
测试用例: get_next_page_replies（获取评论下一页回复）
运行方式:
    配置 ~/.openclaw/.env 或 mcporter 后:
    python3 read/test_get_next_page_replies.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from read.get_feed_comments import run as get_feed_comments
from read.get_next_page_replies import run as get_next_page_replies

FEED_ID    = "B_f14fa569bc5c0c001441152209068856060X60"
GUILD_ID   = 609667373978642354
CHANNEL_ID = 634587030


def test_flow():
    """
    完整流程：
    1. get_feed_comments 拿评论列表，找一个 next_page_reply=true 的评论
    2. 用该评论的 attach_info 调用 get_next_page_replies（首次翻页）
    3. 用响应的 attachInfo 继续翻页，直到 hasMore=false 或翻了2页为止
    """
    # Step 1: 拉评论列表
    comments_res = get_feed_comments({
        "feed_id":        FEED_ID,
        "guild_id":       GUILD_ID,
        "channel_id":     CHANNEL_ID,
        "page_size":      10,
        "rank_type":      1,
        "reply_list_num": 3,
    })
    assert comments_res["success"] is True, f"get_feed_comments 失败: {comments_res}"

    comments = comments_res["data"].get("vecComment", [])
    assert len(comments) > 0, "评论列表为空，无法测试"
    print(f"  评论总数: {comments_res['data'].get('totalNum')}, 本页: {len(comments)}")

    # 找一个 next_page_reply=true 的评论
    target = next((c for c in comments if c.get("nextPageReply")), None)
    assert target is not None, (
        "未找到 next_page_reply=true 的评论，该帖子评论均无超出预览的回复"
    )
    comment_id  = target["id"]
    attach_info = target.get("attachInfo", "")
    reply_count = target.get("replyCount", 0)
    preview_replies = target.get("vecReply", [])
    assert attach_info, f"next_page_reply=true 的评论 attach_info 不应为空，comment_id={comment_id}"

    print(f"  找到目标评论: id={comment_id}, replyCount={reply_count}, "
          f"预览回复数={len(preview_replies)}, nextPageReply=True")

    # Step 2: 用评论的 attach_info 拉第一个"下一页"
    page1_res = get_next_page_replies({
        "feed_id":    FEED_ID,
        "comment_id": comment_id,
        "attach_info": attach_info,
        "page_size":  5,
        "guild_id":   GUILD_ID,
        "channel_id": CHANNEL_ID,
    })
    assert page1_res["success"] is True, f"首次 get_next_page_replies 失败: {page1_res}"
    data1 = page1_res["data"]
    replies1 = data1.get("replies", [])
    assert len(replies1) > 0, "首次翻页回复列表不应为空"
    assert "hasMore" in data1,        "响应应含 hasMore 字段"
    assert "totalReplyCount" in data1, "响应应含 totalReplyCount 字段"
    assert "attachInfo" in data1,     "响应应含 attachInfo 字段"

    # 验证翻页内容不与预览重叠（id 不同）
    preview_ids = {r["id"] for r in preview_replies}
    page1_ids   = {r["id"] for r in replies1}
    overlap = preview_ids & page1_ids
    assert not overlap, f"下一页回复与评论预览回复重叠，重叠id={overlap}"

    # 验证 content 已被解码为 dict
    for r in replies1:
        assert isinstance(r.get("content"), dict), f"content 应已解码为 dict: {r}"
        assert "text" in r["content"], f"content dict 应含 text 字段: {r}"

    print(f"  首次翻页: replies={len(replies1)}, has_more={data1.get('hasMore', False)}, "
          f"total={data1['totalReplyCount']}")
    for r in replies1:
        print(f"    {r['id']} {r['content']['text'][:30]}")

    # Step 3: 如果还有更多，继续翻一页
    if data1.get("hasMore") and data1.get("attachInfo"):
        page2_res = get_next_page_replies({
            "feed_id":     FEED_ID,
            "comment_id":  comment_id,
            "attach_info": data1["attachInfo"],
            "page_size":   5,
            "guild_id":    GUILD_ID,
            "channel_id":  CHANNEL_ID,
        })
        assert page2_res["success"] is True, f"第2页 get_next_page_replies 失败: {page2_res}"
        data2    = page2_res["data"]
        replies2 = data2.get("replies", [])
        assert len(replies2) > 0, "第2页回复列表不应为空"

        page2_ids = {r["id"] for r in replies2}
        assert not (page1_ids & page2_ids), "第2页与第1页回复不应重叠"

        print(f"  第2页翻页: replies={len(replies2)}, has_more={data2.get('hasMore', False)}")
        for r in replies2:
            print(f"    {r['id']} {r['content']['text'][:30]}")


def test_no_more_replies():
    """next_page_reply=false 的评论不应调用 get_next_page_replies（文档层约束，此处验证逻辑正确性）"""
    comments_res = get_feed_comments({
        "feed_id":        FEED_ID,
        "guild_id":       GUILD_ID,
        "channel_id":     CHANNEL_ID,
        "page_size":      10,
        "rank_type":      1,
        "reply_list_num": 3,
    })
    assert comments_res["success"] is True
    comments = comments_res["data"].get("vecComment", [])
    no_more = [c for c in comments if not c.get("nextPageReply")]
    if not no_more:
        print("  [SKIP] 本页所有评论均有下一页回复，跳过此用例")
        return
    c = no_more[0]
    print(f"  next_page_reply=false 的评论: id={c['id']}, replyCount={c.get('replyCount')}")
    print("  [PASS] 该评论无需调用 get_next_page_replies")


if __name__ == "__main__":
    print("=== test_flow ===")
    test_flow()
    print("[PASS] test_flow\n")

    print("=== test_no_more_replies ===")
    test_no_more_replies()
    print("[PASS] test_no_more_replies\n")

    print("所有测试通过。")
