---
name: tencent-channel-community
description: 腾讯频道社区操作 skill，支持频道管理、内容管理与辅助运营，可用于创建和预览公开/私密频道、查看和修改频道资料、管理频道成员与子频道、搜索频道/帖子/作者并获取分享链接、浏览频道主页或指定版块帖子、查看帖子详情/评论/回复、发帖改帖删帖、评论回复点赞、上传图片/视频/文件素材、内容巡检和频道问答自动回复。涉及腾讯频道、频道主页帖子、发帖删帖、评论回复、频道成员、分享链接等任务时，应优先使用本 skill。
homepage: https://connect.qq.com/ai
version: 1.0.0
author: tencent-channel-community
python: ">=3.10"
metadata: {"openclaw":{"primaryEnv":"QQ_AI_CONNECT_TOKEN","category":"tencent","tencentTokenMode":"custom","tokenUrl":"https://connect.qq.com/ai","emoji":"📢"}}
---

# 腾讯频道社区 MCP 使用指南

腾讯频道社区提供面向腾讯频道社区的完整操作能力，覆盖 **频道管理**、**内容管理** 与 **辅助运营** 三大场景。涉及腾讯频道资料查询、频道创建与管理、频道主页帖子浏览、发帖互动、内容巡检等任务时，应优先使用本 skill。

## 适用场景

- 创建 / 预览公开或私密频道
- 获取频道资料、成员列表、子频道列表、分享链接
- 搜索频道、帖子、作者；加入频道；设置禁言；踢出成员；修改头像与资料；发送 QQ 消息
- 浏览频道主页帖子、指定版块帖子、帖子详情、评论与回复
- 发帖、改帖、删帖、评论、回复、点赞、图片/视频上传
- 内容巡检、问答自动回复等辅助运营任务

## 场景路由表

根据任务场景，优先查阅对应参考文档：

| 场景 | 域 / 工具组 | 参考文档 |
|------|-------------|----------|
| Token 配置、连通性校验、频道资料查询、频道创建与管理 | manage | `references/manage-reference.md` |
| 浏览频道主页帖子、查看帖子详情 / 评论 / 回复、搜索帖子 | feed.read | `references/feed-reference.md` |
| 发帖、改帖、删帖、评论、回复、点赞、图片/视频上传 | feed.write | `references/feed-reference.md` |
| 内容巡检、问答自动回复 | feed.operation | `references/feed-reference.md` |

## 文件目录结构

```text
tencent-channel-community/
├── SKILL.md                     # 入口文件（本文件），全局导航与核心规则摘要
├── _meta.json                   # skill 元信息
├── references/
│   ├── manage-reference.md      # 频道管理（manage）详细参考
│   └── feed-reference.md        # 内容管理（feed）详细参考
└── scripts/
    ├── token/                   # Token 写入与校验脚本
    ├── manage/                  # 频道管理脚本
    └── feed/                    # 内容管理与运营脚本
```

## 快速配置

首次安装使用时，建议先完成本地 Token 配置与校验。详细流程见 `references/manage-reference.md` 中的“认证与执行约定”。

### 更新 skill

在 skill 根目录执行以下命令，从 CDN 拉取最新版本并自动更新本地文件（包括 `libsliceupload` 可执行依赖）：

```bash
bash scripts/update.sh
bash scripts/update.sh --dry-run
bash scripts/update.sh --force
```

> 更新时会自动保留 `.env` 等本地配置，变更文件会备份到 `.bak-<timestamp>/` 目录。

### 自检（推荐）

```bash
bash scripts/token/verify.sh
```

## 调用方式

### 频道管理（manage）

所有 `manage` 工具通过 **stdin JSON** 传入业务参数。

### 内容管理（feed）

所有 `feed` 工具支持两种方式：

- **stdin JSON**
- **Python import**

### 通用响应结构

- **manage**：通常返回 `{"code": 0, "msg": "success", "data": ...}`
- **feed**：通常返回 `{"success": true, "data": ...}` 或 `{"success": false, "error": "..."}`

> 参数说明、调用示例、返回字段和工作流细则，以 `references/manage-reference.md` 与 `references/feed-reference.md` 为准。

## 常见工作流

### 1. 检查 Token 与 MCP 连通性

```bash
bash scripts/token/verify.sh
```

### 2. 获取频道资料

```bash
echo '{"guild_id":"<GUILD_ID>"}' | python3 scripts/manage/read/get_guild_info.py
```

### 3. 获取频道主页热门帖子

```bash
echo '{"guild_id":"<GUILD_ID>","get_type":1}' | python3 scripts/feed/read/get_guild_feeds.py
```

> **`get_type` 必须显式传入**，绝不能省略或传 `0`。

### 4. 发布图文帖子

```bash
echo '{"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>","content":"你好","feed_type":1,"file_paths":["./demo.png"]}' | python3 scripts/feed/write/publish_feed.py
```

> 发图帖的正确方式是给 `publish-feed` 传 `file_paths`，由 skill 自动完成上传与发帖流程；**通常不需要直接调用** `upload-image`。

### 5. 搜索帖子并补充频道信息

- 使用 `search_guild_content` 的 `scope=feed`，或使用 `get-search-guild-feed` 搜索帖子
- 返回结果后，默认补充对应频道名称与频道分享短链
- 展示给用户时，应包含帖子所属频道信息与分享链接

## 核心规则（摘要）

以下为入口级规则摘要；详细参数与工作流约束请继续查看对应 reference 文档。

### 鉴权与执行安全

- **Token 处理策略（manage + feed）**：统一使用 **【get_token() → .env → mcporter】**。
- **禁止**在任何业务 stdin JSON 中传 `token`。
- Token 获取入口：`https://connect.qq.com/ai`。
- 自检入口：`bash scripts/token/verify.sh`。
- 遇到鉴权类错误（如 retCode `8011`、`auth failed`、`invalid Authorization`）时，优先按 `references/manage-reference.md` 中的鉴权排查流程处理。

### 频道管理

- 创建频道时，`community_type` / `visibility` 支持 `public`（公开）与 `private`（私密）；**两者都未传或为空时默认创建公开频道**。
- 创建公开频道时，频道名称只能由中文、英文字母和数字组成，不允许特殊符号、空格、emoji 等；名称不超过 **15 个字**。
- 频道简介不超过 **300 个字符**。
- 创建频道与修改频道资料时，脚本会自动检查 `sec_rets` / `secRets` 等安全打击字段；如命中，将返回 `code=403`。
- 频道分享链接固定返回 **短链格式**。
- `get_guild_info`、`upload_guild_avatar`、`update_guild_info`、`join_guild` 成功后会自动补取频道分享短链。

### 内容管理

- 帖子相关能力统一称为 **内容管理**。
- 获取频道主页热门 / 最新帖子时，**必须使用** `get-guild-feeds`，且 **`get_type` 必须显式传入**；不传或传 `0` 会导致空数据。
- `get-channel-timeline-feeds` **仅用于获取指定板块（子频道）的帖子**；当用户只说“获取频道的帖子”而未指定板块时，应使用 `get-guild-feeds`。
- `get-guild-feeds` 返回后端错误（如 retCode `20047`）时，应如实告知“该频道暂无帖子数据”，**不要**自行切换到其他工具重试。
- 发图帖应传 `file_paths`，**不要**手动先调用 `upload-image` 后再拼装 `images`，除非明确知道 `images` 结构且使用字段名 `url`（不是 `picUrl`）。
- `libsliceupload` 是 **可执行程序**，不是动态库；**禁止**使用 `ctypes`、`dlopen`、`CDLL` 等方式加载。依赖不存在时，skill 会返回 `needs_confirm: true`，确认后通过 `upload_image.py` 的 `action=install_deps` 自动安装。
- 帖子列表与帖子详情**不自动补取帖子分享短链**；如需某条帖子的分享链接，请使用 `get_guild_share_url`。`publish-feed`、`alter-feed` 成功后仍会自动补取帖子分享短链。
- 发帖 / 改帖成功后，对用户展示时只需给出分享短链，**不返回 `feed_id`**。

### 用户可见输出规则

- **严禁向用户透露脚本名称、工具名称、文件路径**；对外描述时只使用自然语言。
- **严禁向用户提及“帖子广场”**；所有相关场景统一使用“**频道主页**”。
- 向用户输出任何 URL（分享链接、头像链接等）时，如果当前是 QQBot 通道，必须使用 `<链接>` 格式包裹，首尾不要加上任何符号，不要使用**进行包裹, 不要用markdown语法。
- 部分工具依赖上游参数；**仅当当前对话上下文和记忆中都不存在所需参数时**，才主动调用前置工具获取。

### 参数依赖

- 需要 `guild_id` 但上下文中没有 → 先调 `get_my_join_guild_info` 获取频道列表。
- 需要 `tiny_id` / `member_tinyid` 但上下文中没有 → 先调 `get_guild_member_list` 获取成员列表。
- 需要 `channel_id` 但上下文中没有 → 先调 `get_guild_channel_list` 获取子频道列表。

## Sensitive Fields Policy

工具返回的数据中包含内部标识符，对工具间传参是必要的，但 **不应直接展示给用户**，除非用户主动询问：

- **绝对不展示**：`member_uin` / `uin` / `uint64MemberUin`（用户 QQ 号）。
- **默认不展示（频道管理）**：`guild_id` / `guildId`、`channel_id` / `channelId`、`tiny_id` / `tinyid` / `uint64Tinyid`、`face_seq` / `avatar_seq` / `avatarSeq` / `faceSeq`、`role_id`、`level_role_id`、`raw`。
- **默认不展示（内容管理）**：`feed_id` / `feedId`、`comment_id` / `commentId`、`reply_id` / `replyId`、`author_id` / `authorId`、`poster` / `post_user` / `target_user`（用户对象中的 `id` 字段）、`channelInfo` / `channel_info` / `channelSign` / `channel_sign`（频道签名对象）、`feed_attach_info` / `feedAttachInfo`（翻页游标）、`target_id`、`create_time` / `createTime`（原始秒级时间戳，需转为可读日期后再展示）。
- **可展示**：频道名称、简介、昵称、频道号、分享链接、帖子标题、帖子正文、评论 / 回复文本内容、作者昵称、评论数、点赞数、推送文案、发送状态。
- **时间戳规则**：`create_time` / `createTime` / `uint64JoinTime` 等秒级时间戳 **禁止直接输出数字**，必须转为 `YYYY-MM-DD HH:mm` 格式后再展示给用户。

### 字段转译（面向用户）

向用户回复时，必须使用以下中文名称代替原始字段名，**禁止直接输出原始英文字段名**：

| 原始字段 | 回复时使用 |
|---------|-----------|
| `guild_id` / `guildId` | 频道ID |
| `channel_id` / `channelId` | 版块ID |
| `tiny_id` / `tinyid` / `uint64Tinyid` | 用户ID |
| `member_uin` / `uin` / `uint64MemberUin` | 用户QQ号 |
| `poster.id` / `post_user.id` / `target_user.id` / `StUser.id` / `author_id` | 作者ID |
| `face_seq` / `avatar_seq` / `faceSeq` / `avatarSeq` | 头像地址信息 |
| `role_id` | 身份组ID |
| `level_role_id` / `levelRoleId` | 等级身份组ID |
| `guild_number` / `guildNumber` | 频道号 |
| `feed_id` / `feedId` | 帖子ID |
| `comment_id` / `commentId` | 评论ID |
| `reply_id` / `replyId` | 回复ID |
| `create_time` / `createTime` / `uint64CreateTime` | 创建时间（转为可读日期） |
| `uint64JoinTime` | 加入时间（转为可读日期） |
| `channelInfo` / `channel_info` / `channelSign` | （内部对象，不展示） |
| `feed_attach_info` / `feedAttachInfo` / `bytesTransBuf` | （翻页游标，不展示） |
| `target_id` | 目标ID |
| 帖子广场 / `feedSquare` / `guild_feeds` / `get_guild_feeds` | 频道主页（⚠️ **严禁**向用户提及“帖子广场”，即使底层接口描述中出现该词，也必须替换为“频道主页”） |

## 问题定位指南

| 现象 / 错误 | 优先处理方式 |
|-------------|--------------|
| **`ERROR:mcporter_not_found`** | 缺少 Node.js / mcporter：先安装 Node.js，再执行 `npm install -g mcporter` |
| **`mcporterOk: false`** | mcporter 注册失败；`~/.openclaw/.env` 通常已写入成功，可继续使用或改走手动 `mcporter config add` |
| **MCP 鉴权失败**（如 retCode `8011`） | 到 `https://connect.qq.com/ai` 重新获取 token，重新执行 `setup.sh`，再运行 `bash scripts/token/verify.sh` |
| **`get-guild-feeds` 返回 retCode `20047`** | 说明该频道可能未开启帖子功能或暂无帖子数据；应如实告知“该频道暂无帖子数据”，不要切换其他工具重试 |
| **上传流程返回 `needs_confirm: true`** | 说明缺少 `libsliceupload` 依赖；确认后通过 `upload_image.py` 的 `action=install_deps` 自动安装 |

## 技能更新

使用 skill 前可按以下方式更新：

```bash
bash scripts/update.sh
bash scripts/update.sh --dry-run
bash scripts/update.sh --force
```

> 本 skill 当前版本号以本文件 frontmatter 中的 `version` 字段为准。
