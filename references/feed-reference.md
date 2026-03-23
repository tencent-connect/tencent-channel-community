# 内容管理（feed）参考文档

本文档用于说明腾讯频道社区 skill 中 **内容管理（feed）** 域的鉴权方式、调用约定、核心规则、参数 Schema 与运营能力说明。

## 适用场景

| 场景 | 推荐工具组 | 说明 |
|------|------------|------|
| 浏览频道主页帖子 | feed.read | 获取热门 / 最新 / 最相关帖子 |
| 浏览指定版块帖子 | feed.read | 获取某个子频道的帖子时间线 |
| 查看帖子详情、评论、回复 | feed.read | 读取内容，不产生写操作 |
| 搜索帖子 | feed.read | 按关键词搜索指定频道内帖子 |
| 发帖、改帖、删帖 | feed.write | 执行真实写入，请谨慎调用 |
| 评论、回复、点赞 | feed.write | 包含帖子、评论、回复交互 |
| 富媒体上传 | feed.write | 图片 / 视频 / 文件上传，通常由发帖流程自动完成 |
| 运营辅助 | feed.operation | 内容巡检、问答自动回复 |

## 鉴权与调用约定

- 与 **频道管理（manage）** 相同：统一使用 **【get_token() → .env → mcporter】**。
- 默认 `.env` 路径：`~/.openclaw/.env`。
- **禁止**在 stdin JSON 中包含 `token` 字段；若传入将直接报错退出。
- 所有 `feed` 工具支持两种方式：
  - **stdin JSON**
  - **Python import**
- 涉及 `guild_id`、`channel_id`、`uint64_member_tinyid`、`bot_user_id` 等 **uint64 / 标识符** 参数时，建议始终按 **字符串** 传递，避免精度丢失。
- `get_type`、`count`、`sort_option`、`page_size`、`feed_type`、`scan_interval` 等枚举 / 计数 / 时间窗口参数，继续使用数值类型。

## 返回格式

```json
{"success": true, "data": { ... }}
```

或：

```json
{"success": false, "error": "错误信息"}
```

## 核心规则

### 通用约束

- 帖子相关的所有能力统称为 **内容管理**；向用户描述时统一使用该名称。
- `scripts/feed/read/` 下的脚本只做查询，不产生写操作。
- `scripts/feed/write/` 下的脚本执行真实写入，请谨慎调用。
- `scripts/feed/operation/` 下的脚本为辅助运营工具，部分支持 `dry_run` 模式。

### 帖子列表与搜索规则

- 获取频道主页热门 / 最新 / 最相关帖子时，**必须使用** `get-guild-feeds`，而不是 `get-channel-timeline-feeds`。
- **`get_type` 参数必须显式传入**，绝不能省略或传 `0`；不传或传 `0` 会导致后端返回空数据（`totalFeedsCount=0`）。
  - `1` = 热门
  - `2` = 最新
  - `3` = 最相关
- 用户说“热门帖子” / “最热的帖”时，必须传 `get_type=1`。
- 用户说“最新帖子”时，必须传 `get_type=2`；此时还需要传 `sort_option`。
- 不确定时默认使用 `get_type=2`（最新）。
- 如果直接调用 MCP 的 `get_guild_feeds` 工具，也必须显式传 `getType=1` 或 `getType=2`，不可省略。
- `get-channel-timeline-feeds` **仅用于获取指定板块（子频道）的帖子**，需要同时提供 `guild_id` 和 `channel_id`。
- 当用户只说“获取频道的帖子”而没有指定具体板块时，应使用 `get-guild-feeds`，不要改用 `get-channel-timeline-feeds`。
- `get-guild-feeds` 返回后端错误（如 retCode `20047`）时，说明该频道可能未开启帖子功能或暂无帖子数据，应如实告知“该频道暂无帖子数据”，**不要**自行切换到其他工具重试。
- 搜索帖子时，如使用 `get-search-guild-feed` 或 `search_guild_content` 的帖子范围，向用户展示结果时应补充帖子所属频道名称与频道分享短链。

### 发帖与上传规则

- 发图帖的正确方式是：给 `publish-feed` 传 `file_paths`（本地文件路径列表），skill 内部会自动完成上传全流程。
- **禁止**手动先调用 `upload-image`，再自行拼装 `images` 参数，除非明确知道 `images` 的字段格式；字段名必须是 `url`，不是 `picUrl`。
- `upload-image` 包含完整三步上传流程（申请 → 分片 HTTP 上传 → 状态同步），一次调用完成；**但通常不需要直接调用**。
- `publish-feed` 只需传入业务参数，如 `guild_id`、`channel_id`、`title`、`content`、`feed_type`、`file_paths`；底层结构由 skill 自动生成，**禁止手动构造**。
- `images` 参数仅适用于 **已拥有 CDN URL** 的场景。
- `libsliceupload` 是 **可执行程序**（Go 编译产物），不是 `.so` / `.dylib` 动态库；**禁止**使用 `ctypes`、`dlopen`、`CDLL` 等方式加载。
- 上传依赖不存在时，skill 会返回 `needs_confirm: true`；确认后调用 `upload_image.py` 的 `action=install_deps` 自动从 CDN 安装。

### 分享链接与对外展示规则

- 帖子列表与帖子详情 **不再自动补取帖子分享短链**。
- 如需某条帖子的分享链接，请使用 `get_guild_share_url` 工具。
- `publish-feed`、`alter-feed` 成功后仍会自动补取帖子分享短链。
- **发帖 / 改帖成功后**，脚本自动返回帖子分享短链；对用户展示时只需给出分享短链，**不返回 `feed_id`**。

## 读取类

### get-guild-feeds

获取频道主页帖子列表，支持热门、最新、最相关模式与翻页。

> **重要**：`get_type` 必须显式传入（`1 / 2 / 3`），不可省略或传 `0`。

```bash
echo '{"guild_id":"<GUILD_ID>","get_type":1}' | python3 scripts/feed/read/get_guild_feeds.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 否 | 频道 ID；与 `guild_number` 二选一必填 |
| `guild_number` | string | 否 | 频道号，没有 `guild_id` 时可用 |
| `count` | integer | 否 | 拉取帖子个数，默认 20，最大 50 |
| `get_type` | integer | 是 | 1=热门，2=最新，3=最相关 |
| `sort_option` | integer | 否 | `get_type=2` 时必填：1=发布时间序，2=评论时间序 |
| `feed_attach_info` | string | 否 | 翻页透传字段，首次不填，后续填上一次返回值 |

### get-channel-timeline-feeds

获取指定板块（子频道）的帖子列表，按最新回复时间排序，支持翻页。

```bash
echo '{"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>"}' | python3 scripts/feed/read/get_channel_timeline_feeds.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 板块（子频道）ID |
| `count` | integer | 否 | 拉取帖子个数，默认 20，最大 50 |
| `sort_option` | integer | 否 | 排序：1=发布时间序（默认），2=评论时间序 |
| `feed_attch_info` | string | 否 | 翻页透传字段（字段名保持与现有工具一致） |

### get-feed-detail

获取指定帖子的完整详情。

```bash
echo '{"feed_id":"B_xxx"}' | python3 scripts/feed/read/get_feed_detail.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `guild_id` | string | 否 | 频道 ID，建议填写以加速查询 |
| `channel_id` | string | 否 | 板块 ID，建议填写以加速查询 |
| `author_id` | string | 否 | 帖子作者 ID，建议填写 |
| `create_time` | integer | 否 | 帖子发表时间（秒级时间戳），建议填写 |

### get-feed-comments

获取指定帖子的评论列表，支持翻页。当评论的 `has_more_replies=true` 时，可调用 `get-next-page-replies` 加载更多回复。

```bash
echo '{"feed_id":"<FEED_ID>","guild_id":"<GUILD_ID>"}' | python3 scripts/feed/read/get_feed_comments.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 否 | 板块 ID |
| `page_size` | integer | 否 | 每页评论数量，默认 20，最大 20 |
| `rank_type` | integer | 否 | 评论排序：1=时间正序，2=时间倒序 |
| `attach_info` | string | 否 | 翻页透传字段 |
| `ext_info` | object | 否 | 公共扩展透传字段，翻页时原样填入 |

### get-next-page-replies

获取指定评论下的下一页回复列表。首次调用传 `get-feed-comments` 返回评论中的 `attach_info`，后续继续传本接口返回的 `attach_info`，直到 `has_more=false`。

```bash
echo '{"feed_id":"<FEED_ID>","comment_id":"<COMMENT_ID>","attach_info":"<ATTACH_INFO>"}' | python3 scripts/feed/read/get_next_page_replies.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `comment_id` | string | 是 | 评论 ID |
| `attach_info` | string | 是 | 翻页游标 |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 板块 ID，建议填写 |
| `page_size` | integer | 否 | 每页回复数量，默认 20，最大 50 |

### get-search-guild-feed

按关键词搜索指定频道内的帖子，支持翻页。

```bash
echo '{"uint64_member_tinyid":"<MEMBER_TINYID>","guild_id":"<GUILD_ID>","query":"关键词"}' | python3 scripts/feed/read/search_guild_feeds.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `uint64_member_tinyid` | string | 是 | 发起搜索的用户 ID（tiny_id） |
| `guild_id` | string | 是 | 频道 ID |
| `query` | string | 是 | 搜索关键词 |
| `cookie` | string | 否 | 翻页透传字段（base64 编码） |
| `search_type` | object | 否 | 搜索类型配置：`type`（0=all,1=消息,2=帖子）、`feed_type`（0=默认,1=最新） |

## 写入类

### publish-feed

发表新帖子。支持短贴（`feed_type=1`，无标题）和长贴（`feed_type=2`，有标题）。只需传业务参数，底层字段由 skill 内部自动生成。

```bash
echo '{"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>","content":"你好","feed_type":1}' | python3 scripts/feed/write/publish_feed.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 板块 ID |
| `title` | string | 否 | 帖子标题，长贴必填 |
| `content` | string | 否 | 帖子正文（纯文本） |
| `feed_type` | integer | 否 | 1=短贴（默认），2=长贴 |
| `images` | array | 否 | 图片列表，每项包含 `url`、`width`、`height` 等 |
| `file_paths` | array | 否 | 本地图片路径列表，自动上传至 CDN |
| `on_upload_error` | string | 否 | 上传失败策略：`abort`（默认）/ `skip` |

### alter-feed

修改帖子标题或正文。

```bash
echo '{"feed_id":"<FEED_ID>","create_time":<UNIX_TIMESTAMP>,"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>","title":"新标题"}' | python3 scripts/feed/write/alter_feed.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `create_time` | integer | 是 | 帖子发表时间（秒级时间戳） |
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 板块 ID |
| `title` | string | 否 | 修改后的标题 |
| `content` | string | 否 | 修改后的正文 |

### del-feed

删除帖子。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `create_time` | integer | 是 | 帖子发表时间 |
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 板块 ID |

### do-comment

发表 / 删除评论。`comment_type`：`0`=自己删除评论，`1`=发表评论，`2`=帖主删除他人评论。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `feed_create_time` | integer | 是 | 帖子发表时间 |
| `comment_type` | integer | 是 | 操作类型：0 / 1 / 2 |
| `content` | string | 否 | 评论内容（发表时必填） |
| `images` | array | 否 | 评论图片列表 |
| `comment_id` | string | 否 | 评论 ID（删除时必填） |
| `comment_author_id` | string | 否 | 评论作者 ID（删除时必填） |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 板块 ID，建议填写 |

### do-reply

发表 / 删除回复。`reply_type`：`0`=自己删除回复，`1`=发表回复，`2`=帖主删除他人回复。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `feed_author_id` | string | 是 | 帖子作者 ID |
| `feed_create_time` | integer | 是 | 帖子发表时间 |
| `comment_id` | string | 是 | 所属评论 ID |
| `comment_author_id` | string | 是 | 评论作者 ID |
| `comment_create_time` | integer | 是 | 评论发表时间 |
| `reply_type` | integer | 是 | 操作类型：0 / 1 / 2 |
| `replier_id` | string | 是 | 回复人用户 ID |
| `content` | string | 否 | 回复内容（发表时必填） |
| `reply_id` | string | 否 | 回复 ID（删除时必填） |
| `target_reply_id` | string | 否 | 被回复的回复 ID |
| `target_user_id` | string | 否 | 被回复人用户 ID |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 板块 ID，建议填写 |

### do-like

评论或回复点赞 / 取消点赞。`like_type`：`3`=点赞评论，`4`=取消点赞评论，`5`=点赞回复，`6`=取消点赞回复。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `like_type` | integer | 是 | 点赞类型：3 / 4 / 5 / 6 |
| `feed_id` | string | 是 | 帖子 ID |
| `feed_author_id` | string | 是 | 帖子作者 ID |
| `feed_create_time` | integer | 是 | 帖子发表时间 |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 板块 ID，建议填写 |
| `comment_id` | string | 否 | 评论 ID（`like_type=3/4/5/6` 时必填） |
| `comment_author_id` | string | 否 | 评论作者 ID（`like_type=3/4/5/6` 时必填） |
| `reply_id` | string | 否 | 回复 ID（`like_type=5/6` 时必填） |
| `reply_author_id` | string | 否 | 回复作者 ID（`like_type=5/6` 时必填） |

### do-feed-prefer

帖子点赞 / 取消点赞。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `action` | integer | 是 | 1=点赞，3=取消点赞 |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 板块 ID，建议填写 |

### upload-image

帖子富媒体上传（申请 → 分片 HTTP 上传 → 状态同步），一次调用完成。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 子频道 ID |
| `file_path` | string | 是 | 本地文件路径 |
| `business_type` | integer | 否 | 1002=图片（默认），1003=视频，1004=文件 |
| `file_name` | string | 否 | 文件名；不填时从路径提取 |
| `width` | integer | 否 | 宽度（像素） |
| `height` | integer | 否 | 高度（像素） |

## 运营类

### auto-clean-channel-feeds

扫描帖子供 AI 判断违规，配合 `del-feed` 删除。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 否 | 板块 ID；不填则扫描整个频道 |
| `scan_interval` | integer | 否 | 扫描时间窗口（分钟），默认 60 |
| `max_feeds` | integer | 否 | 最多返回帖子数，默认 50，最大 200 |

### channel-qa-responder

频道问答自动回复，支持 `dry_run` 演习模式。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `bot_user_id` | string | 是 | Bot 用户 ID（tiny_id） |
| `channel_id` | string | 否 | 板块 ID |
| `scan_count` | integer | 否 | 拉取帖子数量，默认 20，最大 100 |
| `max_refs` | integer | 否 | 每条回复最多引用参考帖子数，默认 3，最大 5 |
| `dry_run` | boolean | 否 | 演习模式，默认 `false` |

## 问题定位

| 现象 / 错误 | 处理方式 |
|-------------|----------|
| `get-guild-feeds` 返回 retCode `20047` | 说明该频道可能未开启帖子功能或暂无帖子数据；如实告知用户“该频道暂无帖子数据”，不要切换其他工具重试 |
| 上传流程返回 `needs_confirm: true` | 缺少 `libsliceupload` 依赖；确认后通过 `upload_image.py` 的 `action=install_deps` 自动安装 |
| 帖子列表 / 详情中没有分享链接 | 属于预期行为；帖子列表与详情默认不自动补取帖子分享短链，如需链接请调用 `get_guild_share_url` |
| 发图帖失败且你正在手动拼 `images` | 优先改为给 `publish-feed` 传 `file_paths`；如必须传 `images`，字段名必须是 `url` 而不是 `picUrl` |
