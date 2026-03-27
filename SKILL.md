---
name: tencent-channel-community
description: 腾讯频道社区操作 skill,支持频道管理、内容管理与辅助运营,可用于创建和预览公开/私密频道、查看和修改频道资料、管理频道成员与子频道、搜索频道/帖子/作者并获取分享链接、浏览频道主页或指定版块帖子、查看帖子详情/评论/回复、查看互动消息通知、发帖改帖删帖、评论回复点赞、上传图片/视频/文件素材、内容巡检和频道问答自动回复。涉及腾讯频道、频道主页帖子、发帖删帖、评论回复、互动消息、频道成员、分享链接等任务时,应优先使用本 skill。
homepage: https://connect.qq.com/ai
version: 1.0.2
author: tencent-channel-community
python: ">=3.10"
metadata: {"openclaw":{"primaryEnv":"QQ_AI_CONNECT_TOKEN","category":"tencent","tencentTokenMode":"custom","tokenUrl":"https://connect.qq.com/ai","emoji":"📢"}}
bind_mcp_methods:
  # feed · read
  - get_guild_feeds
  - get_channel_timeline_feeds
  - get_feed_detail
  - get_feed_comments
  - get_next_page_replies
  - get_search_guild_feed
  - get_feed_share_url
  - get_interact_notice
  # feed · write
  - publish_feed
  - alter_feed
  - del_feed
  - do_comment
  - do_reply
  - do_like
  - do_feed_prefer
  # feed · operation
  - channel-qa-responder
  - auto-clean-channel-feeds
  # manage · read
  - get_guild_info
  - get_my_join_guild_info
  - get_user_info
  - get_guild_member_list
  - guild_member_search
  - get_guild_channel_list
  - search_guild_content
  - get_join_guild_setting
  - get_share_info
  # manage · write
  - join_guild
  - kick_guild_member
  - modify_member_shut_up
  - update_guild_info
  - upload_guild_avatar
  - create_guild
  - push_qq_msg
---

# 腾讯频道社区使用指南

腾讯频道社区提供面向腾讯频道社区的完整操作能力,覆盖 **频道管理**、**内容管理** 与 **辅助运营** 三大场景, 使用前必须先根据场景路由表读取对应的参考文档。

## 场景路由表

根据用户意图,查阅对应参考文档:

| 用户意图 | 参考文档 |
|---------|----------|
| Token 配置、连通性校验 | `references/manage-guild.md` |
| 创建频道、频道资料查询 / 修改、频道版块列表、搜索频道 / 作者、加入频道、分享链接、解析分享链接、给自己发送QQ通知 | `references/manage-guild.md` |
| 查看成员列表、查询频道内的机器人、搜索成员、查个人资料、禁言 / 解禁、踢成员 | `references/manage-member.md` |
| 浏览频道主页 / 指定版块帖子、帖子详情 / 评论 / 回复、搜索帖子、查看互动消息通知 | `references/feed-reference.md` |
| 发帖、改帖、删帖、评论、回复、点赞、富媒体上传、在帖子/评论/回复中 @用户 | `references/feed-reference.md` |
| 内容巡检、问答自动回复 | `references/feed-reference.md` |

> **分流提醒**:用户说"看频道有哪些帖子"、"获取帖子"等,应转 `feed-reference.md`,不要停留在 manage。

## 快速决策

以下规则用于快速决策：

### 链接识别

用户消息中包含链接时：

| 特征 | 判定 | 建议动作 |
|------|------|---------|
| `pd.qq.com/s/<code>` 短链 | 频道分享链接 | 先调用 `get_share_info` 解析，再按用户意图继续 |
| `pd.qq.com/...?inviteCode=<code>` 长链 | 频道分享链接 | 先调用 `get_share_info` 解析，再按用户意图继续 |
| 其他链接 | 非频道分享链接 | 不走解析流程 |

## 首次使用

1. 到 `https://connect.qq.com/ai` 获取 Token
2. 运行配置脚本:`bash scripts/token/setup.sh '<token>'`
3. 自检:`bash scripts/token/verify.sh`

详细流程见 `references/manage-guild.md` 的"认证与配置"。

## 关键硬规则

以下规则全局生效,不遵守会导致执行错误:

1. **禁止** 在任何业务 stdin JSON 中传 `token`(避免泄露)
2. **严禁** 向用户透露脚本名称、工具名称、文件路径
3. 向用户输出 URL 时,如当前是 QQBot 通道,必须使用 `<链接>` 格式包裹,不加额外符号,不用 markdown 语法
4. **@用户的唯一正确方式**：任何涉及 @ 用户的操作（发帖、改帖、评论、回复），必须先调用 `guild_member_search` 或 `get_guild_member_list` 查到目标用户的 `tiny_id`（字段 `uint64Tinyid`），再将其填入对应工具的 `at_users` 参数（`id` 字段填 `tiny_id`，`nick` 字段填昵称）。**严禁**在 `content` 正文中手动拼写 `@昵称` 文本——这只是纯文字，不产生任何系统级 at 通知效果；**严禁**使用 QQ 号、猜测值或任何非 `tiny_id` 的值填入 `at_users[].id`。
5. 禁止直接跳过脚本的方式调用MCP接口

## 敏感字段策略

脚本输出已统一为语义化字段名，按以下策略决定是否向用户展示。

### 1. 绝对不展示

| 字段 | 原因 |
|------|------|
| `member_uin` / `uin` / `uint64MemberUin` | 用户 QQ 号，隐私敏感 |

### 2. 内部链式字段（不展示，但不得丢弃）

agent 在多步骤操作中必须透传这些字段，**不向用户展示，也不得在清洗时丢弃**：

| 字段 | 来源接口 | 用于哪些写操作 |
|------|---------|--------------|
| `feed_id` | 所有 feed 读取接口 | `get_feed_detail` / `do_comment` / `do_reply` / `del_feed` / `alter_feed` |
| `create_time_raw` | 所有 feed 读取接口 | `do_comment` / `do_reply` / `del_feed` / `alter_feed` |
| `author_id`（帖子级）| `get_guild_feeds` / `get_channel_timeline_feeds` / `get_feed_detail` / `search_guild_feeds` / `get_notices` | `do_comment` / `del_feed` |
| `comment_id` | `get_feed_comments` | `do_reply` / `do_like`（评论点赞）|
| `author_id`（评论级）| `get_feed_comments` | `do_reply` |
| `create_time_raw`（评论级）| `get_feed_comments` | `do_reply` |
| `reply_id` | `get_feed_comments`.`replies_preview` / `get_next_page_replies` | `del_feed`（删除回复）/ `do_reply`（回复某条回复）|
| `target_reply_id` | `get_feed_comments`.`replies_preview` / `get_next_page_replies` | `do_reply`（回复某条回复时**必须**传入，否则楼层关系丢失）|
| `target_user_id` | `get_feed_comments`.`replies_preview` / `get_next_page_replies` | `do_reply` |
| `attach_info` / `feed_attach_info` / `feed_attch_info` / `next_page_cookie` | 各翻页接口 | 翻页时原样传回对应接口 |

### 3. 默认不展示（除非用户明确要求）

**频道管理类：**`guild_id`、`channel_id`、`tiny_id`、`face_seq` / `avatar_seq`、`role_id`、`level_role_id`、`raw`

**内容管理类：**`feed_id`、`comment_id`、`reply_id`、`author_id`、`channelInfo` / `channelSign`、`create_time_raw`

> 向用户提及上述概念时，使用以下中文名：`guild_id`→频道ID、`channel_id`→版块ID、`tiny_id`→用户ID、`feed_id`→帖子ID、`comment_id`→评论ID、`reply_id`→回复ID

### 4. 时间戳

- 内容管理脚本：`create_time` 已格式化为北京时间（`YYYY-MM-DD HH:MM:SS`），直接展示；`create_time_raw` 为原始秒级时间戳，仅供链式操作使用，不展示
- 频道管理脚本：原始秒级字段（如 `joinTime`、`shutupExpireTime`）自动附带 `{字段名}_human` 可读值，向用户展示 `_human` 字段，不展示原始时间戳；禁言时间戳为 `0` 时显示"无禁言"

### 5. 特殊名称规则

- **严禁向用户提及"帖子广场"**，统一显示为 **"频道主页"**
