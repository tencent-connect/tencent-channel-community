---
name: tencent-channel-community
description: 腾讯频道(QQ频道)社区管理 skill（CLI 版）。频道创建/设置/搜索/加入/退出，成员管理/禁言/踢人，帖子发布/编辑/删除/搜索，评论/回复/点赞，版块管理，分享链接解析，频道私信，加入设置管理，内容巡检，问答自动回复。涉及腾讯频道、频道帖子、频道成员相关任务时应优先使用。  
homepage: https://connect.qq.com/ai
version: 1.1.1  
metadata: {"openclaw":{"emoji":"📢"}}
---

所有操作通过 `tencent-channel-cli <domain> <action>` 调用。两种传参模式：

- **stdin JSON**：`echo '{"guild_id":"123"}' | tencent-channel-cli manage get-guild-info`
- **CLI flag**：`tencent-channel-cli manage get-guild-info --guild-id 123`

## 场景路由

根据用户意图关键词，读取对应参考文档：

- `**references/manage-guild.md`** — 频道、版块、创建频道、修改频道、头像、搜索频道、搜索作者、全局搜索帖子、加入频道、频道分享链接、解析分享链接、加入设置、修改加入设置、私信、发私信、退出频道
- `**references/manage-member.md`** — 成员、禁言、踢人、搜索成员、个人资料
- `**references/feed-reference.md`** — 帖子、评论、回复、点赞、发帖、改帖、删帖、帖子分享链接、互动消息、@用户、内容巡检、问答自动回复

> 「帖子」「评论」「回复」「帖子分享链接」→ feed-reference.md；「频道分享链接」→ manage-guild.md。
> 帖子搜索有两种：跨频道全局搜索（`search-guild-content scope=feed`）→ manage-guild.md；频道内搜索（`search-guild-feeds`）→ feed-reference.md。

## 全局硬规则

1. **@用户**：必须先 `guild-member-search` 或 `get-guild-member-list` 查到 `tiny_id`，填入 `at_users`（`id`=tiny_id, `nick`=昵称）。**严禁**在 content 中手写 `@昵称`，严禁用 QQ 号或猜测值
2. **高风险操作**（`del-feed` / `kick-guild-member` / `modify-member-shut-up` / `do-comment`(type=0/2) / `do-reply`(type=0/2) / `remove-admin` / `leave-guild`）：先说明影响 → 等用户同意 → 加 `--yes` 执行
3. **URL 输出**：必须用 `<链接>` 包裹（如 `<https://pd.qq.com/s/xxx>`），不用 markdown 语法
4. **鉴权失败**（retCode `8011` 或"未登录"错误）：提示用户执行 `tencent-channel-cli token setup` 重新配置凭证

## 链接识别

用户消息含 `pd.qq.com/s/<code>` 或 `pd.qq.com/...?inviteCode=<code>` → 先 `tencent-channel-cli manage get-share-info` 解析，再按意图继续。其他链接不走解析。

## 参数查询

参数定义和示例通过 CLI 实时查询（返回机器可解析的 JSON，比 --help 更适合 agent）：

- `tencent-channel-cli schema <domain>.<action>` — flags 的 name / type / required / enum / default / desc + 示例

## 环境与认证

**最低 CLI 版本：1.0.2**

```bash
tencent-channel-cli --version          # 未安装或版本 < 1.0.2 → npm install -g tencent-channel-cli
tencent-channel-cli token verify       # 未登录 → tencent-channel-cli token setup（交互式输入凭证）或 tencent-channel-cli token setup '<凭证>' （直接传入）
tencent-channel-cli doctor             # 自检连通性
```

> tencent-channel-cli 不存在时必须先提示安装，禁止执行任何 tencent-channel-cli 命令。
> CLI 版本低于 **1.0.2** 时，需要执行 `npm install -g tencent-channel-cli` 升级后再继续，禁止使用旧版本执行命令。

## 更新检测

通过 HEAD 请求（不下载文件）读取响应头，判断 Skill 和 CLI 是否有新版本：

```bash
curl -sI -L https://connect.qq.com/skills/tencent-channel-community.zip
# 检查 x-cos-meta-tcc-version     → Skill 最新版本（与本文件 frontmatter version 比对）
# 检查 x-cos-meta-tcc-cli-version → 最新 CLI 版本（与 tencent-channel-cli --version 比对）
```

SKILL有新版本时，从以下渠道获取更新：

- CDN：[https://connect.qq.com/skills/tencent-channel-community.zip](https://connect.qq.com/skills/tencent-channel-community.zip)
- GitHub：[https://github.com/tencent-connect/tencent-channel-community](https://github.com/tencent-connect/tencent-channel-community)
- ClawHub：[https://clawhub.ai/tencent-adm/tencent-channel-community](https://clawhub.ai/tencent-adm/tencent-channel-community)

## 敏感字段策略

工具输出已统一为语义化字段名，按以下策略决定是否向用户展示。

### 1. 绝对不展示


| 字段                                       | 原因           |
| ---------------------------------------- | ------------ |
| `member_uin` / `uin` / `uint64MemberUin` | 用户 QQ 号，隐私敏感 |


### 2. 内部链式字段（不展示，但不得丢弃）

agent 在多步骤操作中必须透传这些字段，**不向用户展示，也不得在清洗时丢弃**：


| 字段                                                                          | 来源命令                                                                                                        | 用于哪些写操作                                                                   |
| --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `feed_id`                                                                   | 所有 feed 读取命令                                                                                                | `get-feed-detail` / `do-comment` / `do-reply` / `del-feed` / `alter-feed` |
| `create_time_raw`                                                           | 所有 feed 读取命令                                                                                                | `do-comment` / `do-reply` / `del-feed` / `alter-feed`                     |
| `author_id`（帖子级）                                                            | `get-guild-feeds` / `get-channel-timeline-feeds` / `get-feed-detail` / `search-guild-feeds` / `get-notices` | `do-comment` / `del-feed`                                                 |
| `comment_id`                                                                | `get-feed-comments`                                                                                         | `do-reply` / `do-like`（评论点赞）                                              |
| `author_id`（评论级）                                                            | `get-feed-comments`                                                                                         | `do-reply`                                                                |
| `create_time_raw`（评论级）                                                      | `get-feed-comments`                                                                                         | `do-reply`                                                                |
| `reply_id`                                                                  | `get-feed-comments`.`replies_preview` / `get-next-page-replies`                                             | `del-feed`（删除回复）/ `do-reply`（回复某条回复）                                      |
| `target_reply_id`                                                           | `get-feed-comments`.`replies_preview` / `get-next-page-replies`                                             | `do-reply`（回复某条回复时**必须**传入，否则楼层关系丢失）                                      |
| `target_user_id`                                                            | `get-feed-comments`.`replies_preview` / `get-next-page-replies`                                             | `do-reply`                                                                |
| `attach_info` / `feed_attach_info` / `feed_attch_info` / `next_page_cookie` | 各翻页命令                                                                                                       | 翻页时原样传回对应命令                                                               |


### 3. 默认不展示（除非用户明确要求）

**频道管理类：**`guild_id`、`channel_id`、`tiny_id`、`face_seq` / `avatar_seq`、`role_id`、`level_role_id`、`raw`

**内容管理类：**`feed_id`、`comment_id`、`reply_id`、`author_id`、`channelInfo` / `channelSign`、`create_time_raw`

> 向用户提及上述概念时，使用以下中文名：`guild_id`→频道ID、`channel_id`→版块ID、`tiny_id`→用户ID、`feed_id`→帖子ID、`comment_id`→评论ID、`reply_id`→回复ID

### 4. 时间戳

- 内容管理命令：`create_time` 已格式化为北京时间（`YYYY-MM-DD HH:MM:SS`），直接展示；`create_time_raw` 为原始秒级时间戳，仅供链式操作使用，不展示
- 频道管理命令：原始秒级字段（如 `joinTime`、`shutupExpireTime`）自动附带 `{字段名}_human` 可读值，向用户展示 `_human` 字段，不展示原始时间戳；禁言时间戳为 `0` 时显示"无禁言"

### 5. 特殊名称规则

- **严禁向用户提及"帖子广场"**，统一显示为 **"频道主页"**

## 快捷命令

当匹配下列意图时，优先使用快捷命令。一次调用替代多次 tool_call，提高处理速度。


| 意图           | 命令                                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------- |
| 搜索频道并加入      | `tencent-channel-cli manage search-and-join --keyword "<关键词>" --json`                                 |
| 在频道内发帖       | `tencent-channel-cli feed quick-publish --content "<内容>" --json`                                      |
| 搜索帖子并评论      | `tencent-channel-cli feed search-and-comment --guild-id <ID> --query "<关键词>" --content "<评论>" --json` |
| 删帖并禁言        | `tencent-channel-cli feed delete-and-mute --guild-id <ID> --query "<关键词>" --json`                     |
| 获取最新帖子详情并且总结 | `tencent-channel-cli feed latest-feeds-detail --json`                                                 |
| 获取热门帖子详情并且总结 | `tencent-channel-cli feed hot-feeds-detail --json`                                                    |


快捷命令是多轮交互：返回 `status: "waiting"` 时**不要放弃改用单命令**，按返回的 `resume_command` 中的模板填写 `--pick <INDEX>` 或 `--set key=value` 后执行即可（`--resume-id` 全程不变）。

`latest-feeds-detail` 和`hot-feeds-detail` 默认返回的是帖子详情，需要再自行进行总结

### 交互协议示例

```
# Step 1: 发起快捷命令
tencent-channel-cli feed quick-publish --content "测试帖子" --json
# → {"data":{"status":"waiting","id":"s-abc12345","step":"1/5","pending":{"type":"pick","hint":"选择要发帖的频道","options":[...],"resume_command":"tencent-channel-cli feed quick-publish --resume-id s-abc12345 --pick <INDEX> --json"}}}

# Step 2: 选择选项后 resume
tencent-channel-cli feed quick-publish --resume-id s-abc12345 --pick 0 --json
# → {"data":{"status":"waiting",...}} 或 {"data":{"status":"done","result":{...}}}
```

> **重要**：所有快捷命令调用必须加 `--json` flag。`status: "done"` 表示完成，`status: "waiting"` 表示需要继续交互。

