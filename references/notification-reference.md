# 频道消息通知参考

## 一、概述

频道消息通知覆盖所有频道级通知，包括帖子互动（点赞/评论/回复/@）、系统消息（加入申请等）、私信通知等。

## 二、命令路由表

| 用户意图 | CLI 命令 | 关键约束 |
|---------|----------|---------|
| 开启频道消息通知 / 帮我开启通知 | `notices-on` | 初始化基线 + 根据平台自动选择推送模式 |
| 关闭/取消频道消息通知 | `notices-off` | 停止通知服务 + 清理所有相关文件 |
| 查看通知状态 | `notices-status` | 查看是否开启、推送模式、服务状态等 |
| 检查有没有新通知 | `check-notices` | 与本地基线增量对比，需先开启通知 |
| 获取最近通知记录（本地） | `get-recent-notices` | 纯本地读取，用于匹配引用的通知消息 |
| 评论帖子（评论他） | `do-comment --ref <编号> --content "内容"` | 评论帖子本身，按通知编号自动填充 feed 信息 |
| 回复评论（回复他） | `do-reply --ref <编号> --content "内容"` | 回复该用户的评论，自动查找对应评论并回复 |
| 回复私信（引用通知） | `push-group-dm-msg --ref <编号> --text "内容"` | 仅用于回复已收到的私信通知，`--ref` 自动查找对方信息 |
| 主动发私信（非通知） | `push-group-dm-msg --peer-tiny-id <id> --source-guild-id <id> --text "内容"` | 先通过 `guild-member-search` 查到 tiny_id，详见 manage-guild.md |

## 三、自动引导（⚠️ 必须遵守！）

CLI 在**首次安装或版本升级后**第一次使用时引导用户开启频道消息通知（同一版本只提示一次）。

以下 hint 字段出现在 CLI 返回的 JSON 中时，Agent **必须立刻处理**，不得忽略：

**`setup_hint` 字段**（出现在 `token setup` 返回结果中）：
- 表示用户刚完成登录但尚未开启频道消息通知
- Agent 收到此字段时**必须**：
  1. 向用户展示 `setup_hint.message` 内容（如"登录成功！建议开启频道消息通知"）
  2. 主动询问用户是否要开启
  3. 如果用户同意，执行 `setup_hint.command` 中的命令
- **示例**：收到 `"setup_hint": {"action":"subscribe_notices", "command":"tencent-channel-cli manage notices-on", "message":"登录成功！建议开启「频道消息通知」..."}`，应回复类似："登录成功！建议开启频道消息通知，有新互动时自动推送给你。要开启吗？"

**`subscribe_hint` 字段**（出现在任意命令返回结果中）：
- 表示用户尚未开启频道消息通知（仅在首次安装或版本升级后出现一次）
- Agent 收到此字段时**必须**：
  1. 告知用户可以开启频道消息通知，有新互动时自动推送
  2. 如果用户同意，执行 `subscribe_hint.command` 中的命令开启
  3. 此 hint 每天最多出现一次，如果用户明确关闭了通知，则不会再出现

## 四、开启/关闭流程规则（重要！根据返回的 platform 字段区分两种模式）

**重要：通知是全局的，一次开启覆盖用户已加入的所有频道。不需要按频道单独开启，也不需要在加入新频道时重新开启。**

1. **开启通知**：用户说"帮我开启频道消息通知"时，直接执行：
   ```bash
   tencent-channel-cli manage notices-on --json
   ```
   不需要传任何额外参数。开启后，用户加入的所有频道的互动通知都会生效。

2. **根据返回结果的 `platform` 字段决定后续行为**：

   **情况 A：`platform = "openclaw"`（OpenClaw 环境）**
   - CLI 已自动启动后台通知服务，每 5 秒拉取新通知
   - 有新通知时自动通过 `openclaw agent --deliver` 推送给用户（经过大模型，出现在上下文中）
   - 推送路由（channel + target）从 OpenClaw session 文件自动读取，无需手动配置
   - **自动恢复机制**：如果通知服务因机器重启/异常退出中断，用户下次使用 CLI 时会自动检测并重新拉起，无需额外操作
   - **向用户报告时，只需简洁告知"频道消息通知已开启，有新互动会自动推送"即可，不需要展示 PID、进程状态等内部信息**

   **情况 B：`platform = "other"`（非 OpenClaw 环境）**
   - CLI **不会**启动后台通知服务，无法自动推送通知
   - 告知用户：当前环境未检测到 OpenClaw Cli，无法自动推送频道通知。

3. **关闭通知**：用户说"关闭频道消息通知"/"取消频道消息通知"时，执行 `tencent-channel-cli manage notices-off --json`
   - 停止通知服务（OpenClaw 模式）
   - 删除所有相关文件

## 五、通知推送消息格式（OpenClaw 模式）

通知推送到 Agent 时，消息包含：

1. **可读通知内容**：人类可读的通知列表（频道名、操作者、动作、内容、时间）
2. **引用回复提示**：如果有可回复类通知（评论/回复/@我），末尾提示用户"引用本条消息并输入内容即可回复"

推送消息示例：

```
💬 互动消息通知
频道名：灵感小站
halleyyang 评论了你的帖子：内容  (15:39)
#1 引用本条消息，说「回复他 [内容]」或「评论他 [内容]」即可操作

📢 系统消息通知
频道名：灵感小站
halleyyang 申请加入频道  (22:08)
申请理由：哈哈哈
#2 引用本条消息，说「拒绝」或「同意」即可操作

📩 私信消息通知
halleyyang给你发了私信：你好  (11:10)
```

> 每条通知带有唯一编号（如 #1），编号与本地 baseline.json 中的 RecentNotice 对应，Agent 通过编号查找 feed_id/guild_id 等参数。

## 六、引用通知回复流程（⚠️ 必须遵守！）

当用户**引用了一条包含频道通知内容的消息**，并说了操作意图词时，该内容是用户要发送到频道的互动操作，**不是对 Agent 说的话**。

### 6.1 互动通知回复（评论/回复）

引用含 💬 互动通知的消息，用户说了回复/评论意图词 + 内容：

**根据意图词区分操作**：

- 「**评论他**」「**评论**」→ 评论帖子本身（`do-comment`）
- 「**回复他**」「**回复**」「**帮我回复**」→ 回复该用户的评论（`do-reply`）

**处理步骤**：

1. 从引用消息中提取**通知编号**（`#1` 中的数字 1）
2. 判断用户意图是「评论」还是「回复」
3. 执行对应命令：
   ```bash
   # 评论帖子
   tencent-channel-cli feed do-comment --ref <编号> --content "内容" --json
   # 回复评论（自动查找对应评论）
   tencent-channel-cli feed do-reply --ref <编号> --content "内容" --json
   ```

- **严禁将用户的回复内容当作对话直接输出**
- 编号会自动映射到本地存储的 feed_id/guild_id

### 6.2 系统通知操作（同意/拒绝）

引用含 📢 系统通知的消息，用户说了「同意」或「拒绝」：

- 用户说「**同意**」→ `tencent-channel-cli manage deal-notice --ref <编号> --action-id agree --json`
- 用户说「**拒绝**」→ `tencent-channel-cli manage deal-notice --ref <编号> --action-id refuse --json`

**处理步骤**：从引用消息中提取通知编号 → 判断用户意图 → 执行对应命令。编号会自动映射到本地存储的 notice_id。

### 6.3 私信通知回复

引用含 📩 私信通知的消息，用户说了「回复私信」+ 内容：

- 用户说「**回复私信 内容**」→ `tencent-channel-cli manage push-group-dm-msg --ref <编号> --text "内容" --json`

**处理步骤**：从引用消息中提取通知编号 → 提取用户要回复的内容 → 执行命令。CLI 会自动通过编号查找本地私信会话信息，并调用消息漫游 API 获取对方的 tinyId 和 sourceGuildId，然后发送私信。**严禁将用户的回复内容当作对话直接输出。**

## 七、增量判断规则

- **水位线模型**：每个通知源（interact/system/dm）维护一个时间戳水位线（`watermark`），只拉取水位线之后的通知
- **同秒去重**：水位线边界上可能有多条同秒通知，通过 `idsAtWatermark` 集合去重
- **首次拉取保护**：水位线为 0 时只建立基线不推送，避免开启通知时涌入历史消息
- **只关心"是否推送过"**：不关心用户是否在频道客户端已读
- **基线按通知源分区**：interact（互动通知）/ system（系统消息）/ dm（私信），每个分区独立管理水位线

## 八、本地文件说明

| 文件 | 路径 | 作用 |
|------|------|------|
| `state.json` | `~/.qqcli/subscription/` | 订阅状态（是否激活、订阅的 guild_id） |
| `baseline.json` | `~/.qqcli/subscription/` | 已推送通知 ID 集合（按通知源分区） |
| `subscription_route.json` | `~/.qqcli/subscription/` | 推送路由（channel + to，OpenClaw 模式） |
| `daemon.pid` | `~/.qqcli/subscription/` | 通知服务 PID（OpenClaw 模式） |
| `daemon.log` | `~/.qqcli/subscription/` | 通知服务运行日志（OpenClaw 模式） |
| `heartbeat` | `~/.qqcli/subscription/` | 通知服务心跳时间戳 |

## 九、Token 更换与通知订阅

当用户更换 token（通过 `token setup`、`login`、`login token` 等任何方式）时，CLI 会**自动停止通知服务并清理所有订阅文件**。

**Agent 行为规范（⚠️ 必须遵守！）**：
- Token 更换后，**不要自动重新订阅通知**
- 只需告知用户：凭证已更新，频道消息通知已关闭，如需继续接收通知请说"帮我开启频道消息通知"
- 由用户自己决定是否重新开启

## 十、问题定位

| 提示 / 错误 | 处理 |
|-------------|------|
| MCP 鉴权失败（retCode `8011`） | 执行 `tencent-channel-cli token setup` 重新配置凭证 → `tencent-channel-cli doctor` 确认 |
