# 频道操作（manage-guild）

覆盖频道生命周期（创建 / 查询 / 修改 / 搜索 / 加入）及通用工具（自检 / QQ 通知）。

---

## 一、脚本路由表

| 用户意图 | 脚本 | 关键约束 | 缺参补齐 |
|---------|------|---------|---------|
| 校验 token / 连通性 | `verify_qq_ai_connect_token.py` | 仅探测，不查业务数据 | 无 |
| 预览创建频道 | `preview_theme_private_guild.py` | 只预览不创建 | 缺 `image_path` → 问用户 |
| 创建公开 / 私密频道 | `create_theme_private_guild.py` | 未指定私密则默认公开；名称 ≤15 字；公开频道名称仅中英数 | 缺 `image_path` → 问用户 |
| 查看我的频道列表 | `get_my_join_guild_info.py` | 返回三类：我创建的 / 我管理的 / 我加入的 | 无 |
| 查看频道资料 | `get_guild_info.py` | — | 缺 `guild_id` → 先 `get_my_join_guild_info` |
| 查看子频道（版块）列表 | `get_guild_channel_list.py` | 只查版块，不查帖子 | 缺 `guild_id` → 先 `get_my_join_guild_info` |
| 搜频道 / 搜帖子 / 搜作者 | `search_guild_content.py` | `scope`：`channel`（默认）/ `feed` / `author` / `all` | 无 |
| 获取频道分享链接 | `get_guild_share_url.py` | 只处理频道分享，不处理帖子分享 | 缺 `guild_id` → 先查频道 |
| 解析频道分享链接 | `get_share_info.py` | 仅限 `pd.qq.com` 域名的频道分享链接 | 无 |
| 查看频道加入设置（验证方式 / 问题） | `get_join_guild_setting.py` | 只查设置，不加入 | 缺 `guild_id` → 先搜索或查频道 |
| 加入频道 | `join_guild.py` | 内部自动预检加入设置；需要验证时返回提示而非报错（见「加入频道规则」） | 缺 `guild_id` → 先搜索或查频道 |
| 修改频道头像 | `upload_guild_avatar.py` | 需要本地图片路径 | 缺 `guild_id` → 先查频道 |
| 修改频道名称 / 简介 | `update_guild_info.py` | 可只改名称或只改简介 | 缺 `guild_id` → 先查频道 |
| 给自己发 QQ 通知 | `push_qq_msg.py` | `dry_run=true` 时只返回预览 | 无 |
| **帖子类任务** | **转 `feed-reference.md`** | 不应走 manage | — |
| **成员类任务**（查成员 / 禁言 / 踢人） | **转 `manage-member.md`** | 不应在此文件处理 | — |

> 脚本位于 `scripts/manage/read/` 或 `scripts/manage/write/`。

---

## 二、分流误区

- ❌ 用户说"看频道有哪些帖子" → 不要留在 manage，**转 `feed-reference.md`**
- ❌ 用户说"查成员 / 禁言 / 踢人" → **转 `manage-member.md`**
- ❌ 用户说"找某个频道" → 区分场景：
  - 搜索未知频道 → `search_guild_content(scope=channel)`
  - 查看自己已加入的频道 → `get_my_join_guild_info`
- ❌ `get_my_join_guild_info` 和 `search_guild_content` 混淆 → 前者查"我的频道"，后者搜索平台上的任意频道

---

## 三、认证与配置

- **Token 获取**：`https://connect.qq.com/ai`
- **凭证链路**：`get_token() → .env → mcporter`
  - 默认 `.env` 路径：`~/.openclaw/.env`
  - 默认 mcporter 服务名：`tencent-channel-mcp`（可通过 `TENCENT_CHANNEL_MCPORTER_SERVICE` 覆盖）
- **禁止** 在业务 stdin JSON 中传 `token`
- 所有 manage 工具通过 **stdin JSON** 传入业务参数
- `guild_id` 等标识符推荐用 **字符串** 传参，避免大整数精度问题

> **时间戳可读化**：所有返回数据中的已知时间戳字段（`joinTime`、`createTime`、`shutupExpireTime`、`timeStamp` 及其 snake_case / uint32 变体）会自动附带 `{字段名}_human` 后缀的可读值（北京时间 `YYYY-MM-DD HH:MM:SS`）。禁言相关时间戳为 `0` 时显示 `"无禁言"`。向用户展示时间时直接使用 `_human` 字段，无需自行转换原始时间戳。

### 配置 token

```bash
bash scripts/token/setup.sh '<token>'
# token 以 - 开头时：
bash scripts/token/setup.sh -- '-xxx...'
```

> 不要把包含真实 token 的命令回显给模型。

### 自检

```bash
bash scripts/token/verify.sh
```

重点关注：`valid`、`tokenSource`、`userProfileProbeOk`、`likelyTokenAuthFailure`、`diagnosis`。当 `likelyTokenAuthFailure=true` 时，引导到平台重新换票。

### mcporter 手动配置（备用）

```bash
mcporter config add tencent-channel-mcp \
  "https://graph.qq.com/mcp_gateway/open_platform_agent_mcp/mcp" \
  --header "Authorization=Bearer <token>" \
  --transport http --scope home
```

| 提示 / 错误 | 处理 |
|-------------|------|
| `ERROR:mcporter_not_found` | 先安装 Node.js，再 `npm install -g mcporter` |
| `mcporterOk: false` | `~/.openclaw/.env` 通常已写入，可继续使用；或手动 `mcporter config add` |
| MCP 鉴权失败（retCode `8011`） | 到 `https://connect.qq.com/ai` 重新获取 token → 重新 `setup.sh` → `verify.sh` |

---

## 四、频道创建与资料规则

- `create_theme_private_guild` 内部流程固定：**预上传头像 → 创建频道 → 补取分享链接**
- `community_type` / `visibility`：`public`（公开）或 `private`（私密）；**都未传或为空时默认公开**
- 仅当用户明确要求私密频道时传 `private` / `私密` / `2`
- 只提供 `theme` 时自动补齐名称和简介；用户显式提供时优先用户输入
- 频道名称 ≤ **15 个字**（中文、英文字母、数字各算 1 个字）
- **公开频道** 名称只能含中文、英文字母和数字，不允许特殊符号、空格、emoji；**私密频道** 无此限制
- `update_guild_info` 仅校验名称长度与简介长度；**修改资料时不做"公开频道仅中英数"的本地判断**
- 频道简介 ≤ **300 个字符**
- 创建 / 修改频道资料时自动检查 `sec_rets` / `secRets`；命中返回 `code=403`，透传服务端原始 JSON
- 补取分享链接失败时 **不回滚频道**，在返回结果中给出告警

---

## 五、加入频道规则

`join_guild.py` 内部自动调用 `get_join_guild_setting` 预检，AI **无需**手动分两步调用。

### JoinGuildType 枚举（来源：cmd0x908e.proto）

| 值 | 枚举名 | 含义 | 脚本行为 |
|----|--------|------|---------|
| 1 | `JOIN_GUILD_TYPE_DIRECT` | 直接加入 | 直接加入 |
| 2 | `JOIN_GUILD_TYPE_ADMIN_AUDIT` | 管理员验证 | 返回提示，需用户提供 `join_guild_comment`（附言） |
| 3 | `JOIN_GUILD_TYPE_DISABLE` | 不允许加入 | 直接报错：「当前频道不允许被加入」 |
| 4 | `JOIN_GUILD_TYPE_QUESTION` | 回答单个问题 | 返回问题，需用户回答后填入 `join_guild_comment` |
| 5 | `JOIN_GUILD_TYPE_QUESTION_WITH_ADMIN_AUDIT` | 回答问题 + 管理员审批 | 返回问题，需用户回答后填入 `join_guild_comment` |
| 6 | `JOIN_GUILD_TYPE_MULTI_QUESTION` | 回答多个问题 | 返回问题列表，需用户回答后填入 `join_guild_answers` |
| 7 | `JOIN_GUILD_TYPE_QUIZ` | 通过测试题 | 返回选择题列表（含选项、最少答题数、最少答对数），需用户作答后填入 `join_guild_answers` |

### 脚本处理流程

脚本 **始终** 先预检加入设置，再根据实际验证类型校验 AI 传参的合法性：

1. **预检失败**（网络异常等）→ fallback 直接尝试加入，不阻断主流程
2. **不允许加入**（`DISABLE`）→ `fail("当前频道不允许被加入")`
3. **直接加入**（`UNKNOWN` / `DIRECT` / 无设置）→ 直接加入，返回结果 + 分享链接
4. **需要附言**（`ADMIN_AUDIT` / `QUESTION` / `QUESTION_WITH_ADMIN_AUDIT`）：
   - 传了 `join_guild_answers` 却没传 `join_guild_comment` → **fail：参数类型错误**
   - 未传 `join_guild_comment` → 返回 `action=need_verification`，提示 AI 向用户收集附言
   - 已传 `join_guild_comment` → 提交加入请求
5. **需要答案**（`MULTI_QUESTION` / `QUIZ`）：
   - 传了 `join_guild_comment` 却没传 `join_guild_answers` → **fail：参数类型错误**
   - 未传 `join_guild_answers` → 返回 `action=need_verification`，提示 AI 向用户收集答案
   - 已传 `join_guild_answers` → **校验答案数量**（与频道设置的问题数匹配）→ 不匹配则 **fail** → 匹配则提交加入请求
6. AI 收到 `need_verification` 后，应将问题 / 验证要求展示给用户，收集后 **再次调用** `join_guild.py` 并传入对应参数

### ⚠️ 硬规则

- 脚本会 **始终预检** 加入设置并校验传参——即使 AI 传了 `join_guild_answers` 或 `join_guild_comment`，也会先检查参数是否与频道实际验证类型匹配，**不匹配直接报错**
- 收到 `action=need_verification` 时，**必须**先将问题/验证要求展示给用户、收集到附言或答案后，才能再次调用 `join_guild`
- **禁止**在未获得用户提供的 `join_guild_comment` 或 `join_guild_answers` 的情况下重复调用 `join_guild`
- **禁止**自行编造附言或答案代替用户作答

---

## 六、查询与搜索规则

- `get_my_join_guild_info` 返回按角色分类的三类频道：`created_guilds`（频道主）、`managed_guilds`（管理员）、`joined_guilds`（成员）；用户说"我的频道"时展示 **全部三类**
- 前 **10** 个频道自动补取分享短链，超过 10 个不自动补链
- `search_guild_content` 支持 `scope`：`channel`（默认）/ `feed` / `author` / `all`，同时支持中文别名。⚠️ 此处 `author`（作者）指「频道创作者 / 频道作者」，是同一身份概念；**不是**帖子的发布人（帖子作者），也**不是**频道的创建人（频道主）
- 搜频道结果 ≤10 时自动补取资料和短链；>10 时仅返回 `guild_id` 列表 + 提示
- 搜帖子返回后，默认补充频道名称与分享短链，展示时包含帖子所属频道信息
- 频道分享链接固定短链格式
- `get_guild_info`、`upload_guild_avatar`、`update_guild_info`、`join_guild` 成功后自动附带 `share_url`

---

## 七、工具入参 Schema

### verify_qq_ai_connect_token

无参数，用于连通性探测。

### preview_theme_private_guild

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image_path` | string | 是 | 本地头像图片路径 |
| `theme` | string | 否 | 频道主题 |
| `guild_name` | string | 否 | 频道名称（显式提供时优先） |
| `guild_profile` | string | 否 | 频道简介（显式提供时优先） |
| `community_type` | string | 否 | `public` / `private` / `公开` / `私密` / `1` / `2`；不传默认公开 |
| `visibility` | string | 否 | `community_type` 的别名；默认公开 |
| `create_src` | string | 否 | 创建来源，默认 `pd-mcp` |

### create_theme_private_guild

参数与 `preview_theme_private_guild` 相同。内部流程：`upload_guild_avatar_pre` → `create_guild` → 补取分享短链。补取失败不回滚，在 `data.share.shareWarning` 给出告警，`data.share.url` 为可用的分享短链。

### get_my_join_guild_info

无必填参数。返回按角色分类的三类频道：

| 字段 | 说明 |
|------|------|
| `created_guilds` / `created_guilds_count` | 我创建的频道（`role="频道主"`） |
| `managed_guilds` / `managed_guilds_count` | 我管理的频道（`role="管理员"`） |
| `joined_guilds` / `joined_guilds_count` | 我加入的频道（`role="成员"`） |
| `total_count` | 三类之和 |

每个频道含 `guildUserInfo.uint32Role`（`0`=成员、`1`=管理员、`2`=频道主），映射为 `msgGuildInfo.role`。

> 用户说"我的频道"时展示**全部三类**；仅当明确说"我创建的"或"我管理的"时才只展示对应分类。

### get_guild_info

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

### get_guild_channel_list

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

### search_guild_content

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 是 | 搜索关键词 |
| `scope` | string | 否 | `channel` / `3`=频道（默认）、`feed` / `4`=帖子、`author` / `5`=作者（频道创作者）、`all` / `1`=全部；支持中文别名（`频道`/`帖子`/`作者`/`全部`） |
| `rank_type` | string | 否 | 默认 `CHANNEL_RANK_TYPE_SMART` |
| `session_info` | string | 否 | 翻页上下文 |
| `disable_correction_query` | boolean | 否 | 是否关闭搜索纠错，默认 `false` |

### get_guild_share_url

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

固定返回短链。只处理**频道分享**，不处理帖子分享。

### get_share_info

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 分享链接（短链或长链均可） |

解析频道分享链接，返回对应的频道信息。短链直接传入，长链脚本自动提取 `inviteCode` / `contentID`。

**路由判断**：符合以下任一格式的链接才是腾讯频道分享链接，应调用本工具：
- 短链：`https://pd.qq.com/s/<code>`（路径以 `/s/` 开头）
- 长链：`https://pd.qq.com/...?...&inviteCode=<code>`（query 参数中含 `inviteCode`）

不满足上述格式的链接（包括 `pd.qq.com` 下的其他页面）均不应调用本工具。

返回 `shareGuildInfo`（含 `guildId` + `guildName`）。如需获取频道详细资料（头像、简介、成员数等），可用返回的 `guildId` 再调用 `get_guild_info`。

### get_join_guild_setting

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

返回该频道的加入设置（`joinType`、`question`、`quiz` 等）。通常 **不需要** 单独调用——`join_guild.py` 内部已自动预检。仅在需要单独查看频道加入设置时使用。

### join_guild

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `join_guild_answers` | array | 否 | 加频道验证答案，每项含 `question`（频道设置的问题）和 `answer`（提交的答案） |
| `join_guild_comment` | string | 否 | 加频道附言（管理员审核类频道必填） |

脚本内部自动预检加入设置（详见「五-b、加入频道规则」）：
- 无需验证 → 直接加入并返回结果
- 需要验证且未传答案/附言 → 返回 `action=need_verification` 提示结构（含问题列表），AI 据此向用户收集信息后二次调用
- 已传答案/附言 → 直接提交加入请求

### upload_guild_avatar

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `image_path` | string | 是 | 本地头像图片路径 |

### update_guild_info

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `guild_name` | string | 否 | 新频道名称（≤15 字） |
| `guild_profile` | string | 否 | 新频道简介（≤300 字符） |

脚本自动对名称和简介做 base64 编码。**不做"公开频道仅中英数"的本地校验**（资料接口无法判断频道类型）。成功后仍检查 `sec_rets`；命中返回 `code=403`。

### push_qq_msg

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_name` | string | 是 | 任务名称 |
| `status` | string | 是 | `success` / `failed` / `partial` |
| `detail` | string | 否 | 任务详情 |
| `dry_run` | boolean | 否 | `true` 时只返回预览 |


