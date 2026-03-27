# 内容管理（feed）参考文档

本文档用于说明腾讯频道社区 skill 中 **内容管理（feed）** 域的鉴权方式、调用约定、核心规则、参数 Schema 与运营能力说明。

## 适用场景

| 场景 | 推荐工具组 | 说明 |
|------|------------|------|
| 浏览频道主页帖子 | feed.read | 获取热门 / 最新 / 最相关帖子 |
| 浏览指定版块帖子 | feed.read | 获取某个子频道的帖子时间线 |
| 查看帖子详情、评论、回复 | feed.read | 读取内容，不产生写操作 |
| 搜索帖子 | feed.read | 按关键词搜索指定频道内帖子 |
| 查看互动消息通知 | feed.read | 获取帖子被评论、被点赞、被回复、被@等互动消息 |
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
- 用户说”热门帖子” / “最热的帖”时，必须传 `get_type=1`。
- 用户说”最新帖子”时，必须传 `get_type=2`。
- 用户说”**全部**” / “所有帖子” / “按时间” / 未明确指定排序时，必须传 `get_type=2`（最新序）。
- 不确定时默认使用 `get_type=2`。
- `get_type=2` 时 `sort_option` 不填则自动默认 `1`（发布时间序）。
- **翻页时必须保持相同的 `get_type`（和 `sort_option`）**：`feed_attach_info` 游标与排序模式绑定，翻页请求中切换 `get_type` 会导致返回错误列表。例如用户查看热门帖子翻下一页，`get_type` 必须仍然传 `1`，即使用户没有再次提到"热门"。
- `get-channel-timeline-feeds` **仅用于获取指定版块（子频道）的帖子**，需要同时提供 `guild_id` 和 `channel_id`。
- 当用户只说“获取频道的帖子”而没有指定具体版块时，应使用 `get-guild-feeds`，不要改用 `get-channel-timeline-feeds`。
- `get-guild-feeds` 返回后端错误（如 retCode `20047`）时，说明该频道可能未开启帖子功能或暂无帖子数据，应如实告知“该频道暂无帖子数据”，**不要**自行切换到其他工具重试。
- 搜索帖子时，如使用 `get-search-guild-feed` 或 `search_guild_content` 的帖子范围，向用户展示结果时应补充帖子所属频道名称与频道分享短链。

### 发帖与上传规则

- **发帖前置规则（重要）**：发帖前必须确认 `guild_id`（频道ID）。若上下文中没有 `channel_id`（版块ID），必须先调用 `get_guild_channel_list` 获取版块列表（接口返回所有类型版块），**自行排除**语音频道、文字消息频道、分类分组等非帖子类型版块，在剩余帖子类版块中找到名为「帖子广场」的版块，将其作为默认**「全部」版块**（严禁对用户提及「帖子广场」），直接使用该版块的 `channel_id` 发帖，无需询问用户；只有当用户明确要求发到其他具体版块时，才展示其余帖子类版块列表供用户选择。仅当用户身份是频道作者（当前对话或上下文中已知）或用户明确要求"全局发帖"时，才可省略 `guild_id` 和 `channel_id`（两者均传 0）。

- **短贴 vs 长贴选择规则（agent 决策）**：
  - 正文 ≤ 1000 加权字 → 默认发**短贴**（`feed_type=1`），无需标题，直接发；
  - 正文 > 1000 加权字 → 必须发**长贴**（`feed_type=2`），同时主动向用户索取标题；
  - 用户明确要求「长贴/图文帖」→ 切换 `feed_type=2`，先向用户索取标题再发帖；
  - **禁止**在用户未提供 `title` 的情况下擅自以 `feed_type=2` 发帖。

- **内容数量限制（发帖 / 改帖均适用）**：
  - 短贴（`feed_type=1`）正文 **≤ 1000 加权字**；超出时提示改用长贴（`feed_type=2`）
  - 长贴（`feed_type=2`）正文 **≤ 10000 加权字**
  - 短贴（`feed_type=1`）图片 **≤ 18 张**，视频 **≤ 1 个**
  - 长贴（`feed_type=2`）图片 **≤ 50 张**，视频 **≤ 5 个**
  - 评论 / 回复图片 **≤ 1 张**
  - 超出限制时 skill 在调用 MCP 前即返回错误，不会发起上传。

- 发帖的唯一正确方式是调用 `publish-feed` skill 脚本，**严禁绕开脚本直接调用底层 MCP `publish_feed` 工具**，否则会产生不合规的 jsonFeed 结构导致发帖失败或内容异常。
- **发帖前的频道确认流程**：
  - 用户提供了 `guild_id` 和 `channel_id` → 直接在指定频道板块下发帖。
  - 用户**未提供** `guild_id` / `channel_id` → **必须先询问用户**：「是发到指定频道，还是以作者身份全局发帖？」
    - 用户选择指定频道 → 调 `get_my_join_guild_info` 获取频道列表，让用户选择，再调 `get_guild_channel_list` 获取板块，确认后发帖。
    - 用户选择全局发帖 → 不传 `guild_id` / `channel_id`（或传 0）直接发帖。
  - **严禁**在用户未明确说明的情况下自行判断走全局发帖路径。
- 发图帖的正确方式是：给 `publish-feed` 传 `file_paths`（本地文件路径列表），skill 内部会自动完成上传全流程。
- **禁止**手动先调用 `upload-image`，再自行拼装 `images` 参数，除非明确知道 `images` 的字段格式；字段名必须是 `url`，不是 `picUrl`。
- `upload-image` 包含完整三步上传流程（申请 → 分片 HTTP 上传 → 状态同步），一次调用完成；**但通常不需要直接调用**。
- `publish-feed` 只需传入业务参数，如 `guild_id`、`channel_id`、`title`、`content`、`feed_type`、`file_paths`；底层结构由 skill 自动生成，**禁止手动构造**。
- `images` 参数仅适用于 **已拥有 CDN URL** 的场景。
- `libsliceupload` 是 **可执行程序**（Go 编译产物），不是 `.so` / `.dylib` 动态库；**禁止**使用 `ctypes`、`dlopen`、`CDLL` 等方式加载。
- 上传依赖不存在时，skill 会返回 `needs_confirm: true`；确认后调用 `upload_image.py` 的 `action=install_deps` 自动从 CDN 安装。
- 发布视频帖时，skill 会自动用 `ffmpeg` 截取首帧作为封面。若检测到 `ffmpeg` 未安装，**skill 会自动安装**（macOS: `brew install ffmpeg`，Linux: `apt-get install -y ffmpeg`），无需 AI 或用户手动操作；Windows 不支持自动安装，会返回错误并提示手动下载。安装过程耗时较长（首次约数分钟），属正常现象，告知用户耐心等待即可。

### @用户的唯一正确流程（全局强制）

> 适用于 `publish-feed`、`alter-feed`、`do-comment`、`do-reply` 所有涉及 @ 的操作。

**两步缺一不可：**

1. **先查 `tiny_id`**：调用 `guild_member_search` 或 `get_guild_member_list`，找到目标用户的 `tiny_id`（字段名 `uint64Tinyid`）和昵称（`memberName` / `nick`）。
2. **再传 `at_users`**：将查到的值填入对应写操作工具的 `at_users` 参数，格式 `[{"id": "<tiny_id>", "nick": "<昵称>"}]`。

**严禁的错误做法：**

| 错误做法 | 后果 |
|---------|------|
| 在 `content` 正文里写 `@张三` | 只是纯文字，用户**不会收到任何 at 通知** |
| `at_users[].id` 填 QQ 号、猜测值 | @ 节点指向无效用户，**实际未 at 到任何人** |
| 不传 `at_users`，仅在 `content` 里提及昵称 | 同第一条，无系统级 at 效果 |

### 帖子长度与拆分规则

> **单贴容量上限**：
> - 正文：短贴 ≤ **1000 加权字**，长贴 ≤ **10000 加权字**（汉字 / 中文标点 / 全角符号 = 1 字，英文 / 数字 / 半角符号 = 0.5 字）
> - 图片：短贴 ≤ **18 张**，长贴 ≤ **50 张**
> - 视频：短贴 ≤ **1 个**，长贴 ≤ **5 个**
>
> **AI 必须在调用 skill 前自行判断是否超限**，超限时先按下方规则处理，不得直接调用让 skill 报错。

- 正文 **> 1000 且 ≤ 10000 加权字**：发**长贴**（`feed_type=2`），向用户索取标题后发帖（见上方「短贴 vs 长贴选择规则」）。
- 内容超出单贴容量上限（正文 > 10000 加权字 / 图片 > 50 张 / 视频 > 5 个）时：
  1. **严禁自行拆分后直接批量发布**，必须先向用户说明超出情况，并询问是否拆分为多条帖子发布。
  2. 用户同意拆分后，向用户说明具体拆分方案，至少包含：预计拆分条数、每条帖子的标题或内容摘要，以及每条分配的媒体数量（每条正文 ≤ 10000 加权字、图片 ≤ 50 张、视频 ≤ 5 个）。
  3. 取得用户对方案的**明确确认**后，才能依次调用 `publish-feed` 发布各条帖子。
  4. 用户拒绝拆分或要求修改方案时，应根据用户反馈调整后再次确认，不得强行继续。

### 分享链接与对外展示规则

- **帖子列表**（`get-guild-feeds`、`get-channel-timeline-feeds`）**不自动补取帖子分享短链**。
- `get-feed-detail` **会自动补取**帖子分享短链，返回结果中已包含 `share_url` 字段，无需额外调用 `get-feed-share-url`。
- 仅当帖子列表结果中需要某条帖子的分享链接时，才需要调用 `get-feed-share-url` 工具（见下方"读取类"章节）。
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

获取指定版块（子频道）的帖子列表，按最新回复时间排序，支持翻页。

> ⚠️ **注意拼写**：本工具的翻页字段名为 **`feed_attch_info`**（少一个 `a`），与 `get-guild-feeds` 的 `feed_attach_info` **不同**，翻页时请严格使用本工具返回的字段名，勿互换。

```bash
echo '{"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>"}' | python3 scripts/feed/read/get_channel_timeline_feeds.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 版块（子频道）ID |
| `count` | integer | 否 | 拉取帖子个数，默认 20，最大 50 |
| `sort_option` | integer | 否 | 排序：1=发布时间序（默认），2=评论时间序 |
| `feed_attch_info` | string | 否 | 翻页透传字段（⚠️ 少一个 `a`，与 `get-guild-feeds` 不同） |

### get-feed-detail

获取指定帖子的完整详情。

```bash
echo '{"feed_id":"B_xxx"}' | python3 scripts/feed/read/get_feed_detail.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `guild_id` | string | 否 | 频道 ID，建议填写以加速查询 |
| `channel_id` | string | 否 | 版块 ID，建议填写以加速查询 |
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
| `guild_id` | string | 否 | 频道 ID；建议填写，不填时后端以 "0" 代替 |
| `channel_id` | string | 否 | 版块 ID |
| `page_size` | integer | 否 | 每页评论数量，默认 20，最大 20 |
| `rank_type` | integer | 否 | 评论排序：1=时间正序，2=时间倒序 |
| `attach_info` | string | 否 | 翻页透传字段 |
| `ext_info` | object | 否 | 公共扩展透传字段，翻页时原样填入 |

**replies_preview 字段说明**：每条评论返回的 `replies_preview` 列表中，每条回复包含以下链式操作字段（不展示给用户，但后续写操作必须透传）：

| 字段 | 用途 |
|------|------|
| `reply_id` | 删除该回复时传入 `del_feed`；**回复该回复时**传入 `do_reply` 的 `target_reply_id` |
| `author_id` | **回复该回复时**传入 `do_reply` 的 `target_user_id` |
| `target_reply_id` | 该回复本身所回复的上级回复 ID（若存在） |
| `target_user_id` | 该回复本身所回复的上级用户 ID（若存在） |
| `create_time_raw` | 回复时间秒级时间戳，`do_reply` 链式操作备用 |

### get-next-page-replies

获取指定评论下的下一页回复列表。首次调用传 `get-feed-comments` 返回评论中的 `attach_info`，后续继续传本接口返回的 `attach_info`，直到 `has_more=false`。

```bash
echo '{"feed_id":"<FEED_ID>","comment_id":"<COMMENT_ID>","attach_info":"<ATTACH_INFO>","guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>"}' | python3 scripts/feed/read/get_next_page_replies.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `comment_id` | string | 是 | 评论 ID |
| `attach_info` | string | 是 | 翻页游标 |
| `guild_id` | string | **是** | 频道 ID |
| `channel_id` | string | **是** | 版块 ID |
| `page_size` | integer | 否 | 每页回复数量，默认 20，最大 50 |

### get-search-guild-feed

按关键词搜索指定频道内的帖子，支持翻页。

```bash
echo '{"guild_id":"<GUILD_ID>","query":"关键词"}' | python3 scripts/feed/read/search_guild_feeds.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `query` | string | 是 | 搜索关键词 |
| `cookie` | string | 否 | 翻页透传字段（base64 编码） |
| `search_type` | object | 否 | 搜索类型配置：`type`（0=all,1=消息,2=帖子）、`feed_type`（0=默认,1=最新） |

### get-feed-share-url

获取指定帖子的分享短链。返回可直接分享的帖子短链 URL。

> **注意**：本工具获取的是**帖子**分享链接，**频道**分享链接请使用 `get_guild_share_url`。

```bash
echo '{"feed_id":"<FEED_ID>","guild_id":"<GUILD_ID>"}' | python3 scripts/feed/read/get_feed_share_url.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 否 | 版块（子频道）ID |

### get-notices

获取用户的互动消息列表，包括帖子被点赞/表态、评论被点赞、回复被点赞、帖子收到评论、评论收到回复、被@等通知，支持翻页。

```bash
echo '{"page_num":20}' | python3 scripts/feed/read/get_notices.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page_num` | integer | 否 | 请求数量，表示期望返回的通知条数，默认 20 |
| `attach_info` | string | 否 | 翻页透传字段，首次请求不填，后续翻页填上一次响应返回的 attach_info |
| `guild_id` | string | 否 | 频道 ID，用于获取某个频道内的消息通知，传 0 表示查询全局消息 |

**通知类型说明**：

| 类型值 | 含义 |
|--------|------|
| 1 | 顶/表态我的帖子 |
| 2 | 点赞我的评论 |
| 3 | 点赞我的回复 |
| 4 | 帖子收到评论 |
| 5 | 评论收到回复 |
| 6 | 在帖子评论区被@ |

**返回结构**：每条通知（StNotice）包含：
- `type`：通知类型描述
- `psv_feed`：被动 feed（互动内容，如评论、回复），含帖子 ID、发表者、内容文本、时间、图片等
- `origine_feed`：原贴 feed（被互动的原始帖子），可能为空（如系统消息）
- `patton_info`：样式文案信息（互动描述文案、引用内容文案）

## 写入类

### publish-feed

发表新帖子。支持短贴（`feed_type=1`，无标题）和长贴（`feed_type=2`，有标题）。只需传业务参数，底层字段由 skill 内部自动生成。

```bash
echo '{"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>","content":"你好","feed_type":1}' | python3 scripts/feed/write/publish_feed.py
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 版块 ID；未指定时先调 `get_guild_channel_list`，只保留帖子类版块，取其中「帖子广场」版块（对用户称「全部」版块）的 `channel_id` 作为默认，直接发帖，无需询问；用户明确指定其他版块时才填对应值 |
| `title` | string | 否 | 帖子标题，长贴必填 |
| `content` | string | 否 | 帖子正文（纯文本） |
| `feed_type` | integer | 否 | 1=短贴（默认），2=长贴 |
| `images` | array | 否 | 图片列表，每项包含 `url`、`width`、`height` 等（已有 CDN URL 时使用）；⚠️ 字段名为 `url`，与 `do-comment`/`do-reply` 的 `picUrl` **不同** |
| `file_paths` | array | 否 | 本地**图片**路径列表（jpg/png 等），自动上传至 CDN；⚠️ **严禁传视频文件**，视频用 `video_paths` |
| `video_paths` | array | 否 | 本地**视频**路径列表（mp4/mov 等），自动上传至 CDN；⚠️ **严禁传图片文件**，图片用 `file_paths`；每项可含 `cover_path` 指定封面图片路径 |
| `at_users` | array | 否 | 正文中被 @ 的用户列表，每项含 `id`（用户ID，tinyId 格式）和 `nick`（昵称）；**需先通过 `guild_member_search` 或 `get_guild_member_list` 获取目标用户的 `tiny_id` 和 `nick`，不可直接使用 QQ 号或文本猜测**；示例：`[{"id":"144115219800577368","nick":"张三"}]` |
| `on_upload_error` | string | 否 | 上传失败策略：`abort`（默认，中止）/ `skip`（跳过失败文件继续发帖） |

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
| `channel_id` | string | 是 | 版块 ID |
| `feed_type` | integer | 是 | 帖子类型：1=短贴（无标题），2=长贴（有标题） |
| `title` | string | 否 | 修改后的标题，长贴（`feed_type=2`）时可填 |
| `content` | string | 否 | 修改后的正文 |
| `at_users` | array | 否 | 正文中被 @ 的用户列表，每项含 `id`（用户ID，tinyId 格式）和 `nick`（昵称）；**需先通过 `guild_member_search` 或 `get_guild_member_list` 获取目标用户的 `tiny_id` 和 `nick`，不可直接使用 QQ 号或文本猜测**；示例：`[{"id":"144115219800577368","nick":"张三"}]` |
| `file_paths` | array | 否 | 替换帖子图片：本地图片路径列表，自动上传至 CDN；与 `clear_images` 不可同时使用 |
| `video_paths` | array | 否 | 替换帖子视频：本地视频路径列表，自动上传至 CDN；与 `clear_videos` 不可同时使用 |
| `clear_images` | boolean | 否 | `true` 时删除帖子所有图片，默认 `false` |
| `clear_videos` | boolean | 否 | `true` 时删除帖子所有视频，默认 `false` |
| `on_upload_error` | string | 否 | 上传失败策略：`abort`（默认，中止）/ `skip`（跳过失败文件继续改帖） |

### del-feed

删除帖子。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `create_time` | integer | 是 | 帖子发表时间 |
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 版块 ID |

### do-comment

发表 / 删除评论。`comment_type`：`0`=自己删除评论，`1`=发表评论，`2`=帖主删除他人评论。

> ⚠️ **工具选择规则**：用户说"评论帖子"、"回复帖子"、"在帖子下留言"等，目标是**帖子本身**时，使用本工具（`do-comment`）。**禁止**先去拉取评论列表再用 `do-reply` 回复评论——那会改变操作层级，变成回复评论而非回复帖子。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feed_id` | string | 是 | 帖子 ID |
| `feed_create_time` | integer | 是 | 帖子发表时间 |
| `comment_type` | integer | 是 | 操作类型：0 / 1 / 2 |
| `content` | string | 否 | 评论内容（发表时必填）；⚠️ **禁止在 content 中手动拼写 `@用户名` 文本**，这只是纯文字不产生系统 at 效果，需要 at 用户请使用 `at_users` 参数 |
| `images` | array | 否 | 评论图片列表（最多 1 张）；每项字段：`picId`、`picUrl`、`imageMD5`、`width`、`height` 等；⚠️ 字段名为 **`picUrl`**，与 `publish-feed` 的 `url` **不同** |
| `comment_id` | string | 否 | 评论 ID（删除时必填） |
| `comment_author_id` | string | 否 | 评论作者 ID（删除时必填） |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 版块 ID，建议填写 |

### do-reply

发表 / 删除回复。`reply_type`：`0`=自己删除回复，`1`=发表回复，`2`=帖主删除他人回复。

> ⚠️ **工具选择规则**：本工具**仅用于**回复已有的**评论或回复**（需提供 `comment_id`）。若用户目标是帖子本身（"回复帖子"、"评论这个帖子"），应使用 `do-comment`，**不得**为了凑 `comment_id` 而先拉评论再调本工具。

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
| `content` | string | 否 | 回复内容（发表时必填）；⚠️ **禁止在 content 中手动拼写 `@用户名` 文本**，这只是纯文字不产生系统 at 效果；at 用户用 `at_users` 参数，回复某条回复用 `target_user_id` + `target_user_nick`（系统自动插入「回复 @xxx」节点） |
| `images` | array | 否 | 回复图片列表（最多 1 张）；每项字段：`picId`、`picUrl`、`imageMD5`、`width`、`height` 等；⚠️ 字段名为 **`picUrl`**，与 `publish-feed` 的 `url` **不同** |
| `reply_id` | string | 否 | 回复 ID（删除时必填） |
| `target_reply_id` | string | **条件必填** | 被回复的回复 ID；**回复某条回复时必须填写**，否则楼层嵌套关系丢失，UI 无法正确显示「回复 @xxx」。从 `get_feed_comments` 的 `replies_preview[].reply_id` 或 `get_next_page_replies` 的 `replies[].id` 获取 |
| `target_user_id` | string | **条件必填** | 被回复人用户 ID；**回复某条回复时必须填写**（与 `target_reply_id` 配套）。从 `replies_preview[].author_id` 或 `get_next_page_replies` 的 `replies[].author_id` 获取 |
| `target_user_nick` | string | 否 | 被回复人昵称，与 `target_user_id` 配合使用，系统自动在内容前插入 @昵称 节点 |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 版块 ID，建议填写 |

### do-like

评论或回复点赞 / 取消点赞。`like_type`：`3`=点赞评论，`4`=取消点赞评论，`5`=点赞回复，`6`=取消点赞回复。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `like_type` | integer | 是 | 点赞类型：3 / 4 / 5 / 6 |
| `feed_id` | string | 是 | 帖子 ID |
| `feed_author_id` | string | 是 | 帖子作者 ID |
| `feed_create_time` | integer | 是 | 帖子发表时间 |
| `guild_id` | string | 否 | 频道 ID，建议填写 |
| `channel_id` | string | 否 | 版块 ID，建议填写 |
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
| `channel_id` | string | 否 | 版块 ID，建议填写 |

### upload-image

帖子富媒体上传（申请 → 分片 HTTP 上传 → 状态同步），一次调用完成。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 是 | 子频道 ID |
| `file_path` | string | 是 | 本地文件路径 |
| `business_type` | integer | 否 | 1002=图片/视频缩略图（默认），**1003=视频主体**，1004=文件；⚠️ 发视频帖必须传 1003，传 1002 会导致 slice N failed |
| `file_name` | string | 否 | 文件名；不填时从路径提取 |
| `width` | integer | 否 | 宽度（像素） |
| `height` | integer | 否 | 高度（像素） |

## 运营类

### auto-clean-channel-feeds

扫描帖子供 AI 判断违规，配合 `del-feed` 删除。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `channel_id` | string | 否 | 版块 ID；不填则扫描整个频道 |
| `scan_interval` | integer | 否 | 扫描时间窗口（分钟），默认 60 |
| `max_feeds` | integer | 否 | 最多返回帖子数，默认 50，最大 200 |

### channel-qa-responder

频道问答自动回复，支持 `dry_run` 演习模式。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `bot_user_id` | string | 是 | Bot 用户 ID（tiny_id） |
| `channel_id` | string | 否 | 版块 ID |
| `scan_count` | integer | 否 | 拉取帖子数量，默认 20，最大 100 |
| `max_refs` | integer | 否 | 每条回复最多引用参考帖子数，默认 3，最大 5 |
| `dry_run` | boolean | 否 | 演习模式，默认 `false` |

## 问题定位

| 现象 / 错误 | 处理方式 |
|-------------|----------|
| `get-guild-feeds` 返回 retCode `20047` | 说明该频道可能未开启帖子功能或暂无帖子数据；如实告知用户“该频道暂无帖子数据”，不要切换其他工具重试 |
| 上传流程返回 `needs_confirm: true` | 缺少 `libsliceupload` 依赖；确认后通过 `upload_image.py` 的 `action=install_deps` 自动安装 |
| 帖子列表 / 详情中没有分享链接 | 属于预期行为；帖子**列表**默认不自动补取帖子分享短链，如需链接请调用 `get-feed-share-url`；**帖子详情**（`get-feed-detail`）则已自动补取，返回结果含 `share_url` 字段 |
| 发图帖失败且你正在手动拼 `images` | 优先改为给 `publish-feed` 传 `file_paths`；如必须传 `images`，字段名必须是 `url` 而不是 `picUrl` |
| 视频帖上传报 `slice N failed` | 根本原因：`business_type` 传了 1002（图片）而非 1003（视频）。服务端用图片 schema 校验视频内容，在某分片触发格式校验失败。发视频帖必须传 `business_type=1003` |
