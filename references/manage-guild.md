# 频道管理（manage-guild）

> **参数用 `tencent-channel-cli schema manage.<action>` 查，示例用 `--help` 看。本文档只写 schema 不体现的规则。**

## 意图→命令速查

| 意图 | 命令 | 注意 |
|------|------|------|
| 我的频道列表 | `get-my-join-guild-info` | 返回三类：created / managed / joined |
| 频道资料 | `get-guild-info` | 缺 guild_id → 先查我的频道 |
| 子版块列表 | `get-guild-channel-list` | 只查版块，不查帖子 |
| 跨频道搜索频道/帖子/作者 | `search-guild-content` | scope: channel(默认) / feed / author / all；搜帖子用 scope=feed，频道内搜帖子用 feed 域 `search-guild-feeds` |
| 频道分享链接 | `get-guild-share-url` | 仅频道链接，帖子链接用 feed 域 |
| 解析分享链接 | `get-share-info` | 仅限 pd.qq.com 域名链接 |
| 加入频道 | `join-guild` | 内部自动预检，见下文 |
| 修改头像 | `upload-guild-avatar` | 需本地图片路径 |
| 修改名称/简介 | `update-guild-info` | 可只改其一 |
| 创建频道 | `create-theme-private-guild` | 未指定私密则默认公开 |
| 创建/删除/修改版块 | `create-channel` / `delete-channel` / `modify-channel` | delete 不可逆，高风险 |
| **帖子类任务** | **→ feed-reference.md** | |
| **成员类任务** | **→ manage-member.md** | |

### 分流误区

- "看频道有哪些帖子" → **feed-reference.md**，不是 manage
- "查成员/禁言/踢人" → **manage-member.md**
- "找频道"区分：搜未知频道 → `search-guild-content`，查已加入 → `get-my-join-guild-info`
- **帖子搜索**区分：跨频道全局搜索帖子 → `search-guild-content scope=feed`；已知频道内搜索帖子 → feed 域 `search-guild-feeds`

## 频道创建规则

- `community_type`：`public`（默认）或 `private`，仅用户明确要求时传 `private`
- 频道名称 ≤15 字；公开频道仅中英数，私密无限制；简介 ≤300 字符
- 需 `theme` 或 `guild_name` 至少其一
- 补取分享链接失败不回滚频道，在返回中给出告警

## 加入频道规则

`join-guild` 内部自动预检加入设置，**无需**手动分两步。

| JoinGuildType | 含义 | AI 行为 |
|---------------|------|---------|
| 1 (DIRECT) | 直接加入 | 自动完成 |
| 2 (ADMIN_AUDIT) | 管理员验证 | 返回 `need_verification` → 向用户收集附言 `join_guild_comment` → 再次调用 |
| 3 (DISABLE) | 不允许 | 报错 |
| 4/5 (QUESTION*) | 回答问题 | 返回问题 → 收集答案填入 `join_guild_comment` → 再次调用 |
| 6 (MULTI_QUESTION) | 多题 | 返回问题列表 → 收集 `join_guild_answers`(⚡JSON) → 再次调用 |
| 7 (QUIZ) | 测试题 | 返回选择题 → 收集 `join_guild_answers`(⚡JSON) → 再次调用 |

> **收到 `need_verification` 必须先展示问题给用户、收集答案后才能再次调用。禁止自行编造答案。**

## 查询规则

- `get-my-join-guild-info` 返回 `created_guilds` / `managed_guilds` / `joined_guilds` 三类，用户说"我的频道"展示全部；前 10 个自动补取分享短链
- `search-guild-content` 的 `author` scope 搜的是「频道创作者」，**不是**帖子发布人也**不是**频道主；搜频道结果 ≤10 自动补取资料和短链

## 陷阱（schema 不体现）

- **频道号 ≠ guild_id**：用户可见的频道号（如 `pd20589127`）是展示层标识，不能当作 `guild_id` 使用。获取真实 guild_id 的方式：通过 `get-share-info` 解析分享链接，或从 `get-my-join-guild-info` 返回中提取
- `get-share-info` 仅限 `pd.qq.com` 域名链接
- `join-guild` 的 `join_guild_answers` 和 `join_guild_comment` 仅 stdin JSON 可传
