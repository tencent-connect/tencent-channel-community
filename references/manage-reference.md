# 频道管理（manage）参考文档

本文档用于说明腾讯频道社区 skill 中 **频道管理（manage）** 域的鉴权方式、调用约定、核心规则、参数 Schema、示例与错误处理。

## 适用场景

| 场景 | 推荐工具组 | 说明 |
|------|------------|------|
| Token 配置与校验 | token / manage.read | 写入 token、校验 MCP 连通性 |
| 频道创建与预览 | manage.read / manage.write | 预览创建效果、创建公开 / 私密频道 |
| 频道资料查询 | manage.read | 获取频道资料、成员、子频道、分享链接 |
| 频道资料维护 | manage.write | 修改头像、名称、简介 |
| 频道成员管理 | manage.write | 禁言、踢人 |
| 搜索与加入频道 | manage.read / manage.write | 搜索频道 / 帖子 / 作者，或加入频道 |
| QQ 通知 | manage.write | 向自己的 QQ 发送任务通知 |

## 认证与执行约定

- **Token 获取**：`https://connect.qq.com/ai`
- **凭证链路**：统一使用 **【get_token() → .env → mcporter】**。
  - 默认 `.env` 路径：`~/.openclaw/.env`
  - 第二读源：`mcporter config get`
  - 默认 mcporter 服务名：`tencent-channel-mcp`
  - 可通过环境变量 `TENCENT_CHANNEL_MCPORTER_SERVICE` 覆盖默认服务名
- **禁止**：在业务 stdin JSON 中传 `token`（避免经模型上下文泄露）；**feed** 脚本同样禁止 stdin JSON 传 `token`。
- 请求头固定使用 `Authorization: Bearer <token>`，并追加 `X-Forwarded-Method: POST`。
- MCP 地址：`https://graph.qq.com/mcp_gateway/open_platform_agent_mcp/mcp`
- 所有 `manage` 工具通过 **stdin JSON** 传入业务参数。
- 涉及 `guild_id`、`tiny_id`、`member_tinyid` 等标识符时，推荐统一使用 **字符串** 传参，避免大整数精度问题。

### OpenClaw / 非交互执行器

推荐将 token 写入 `~/.openclaw/.env`，或预先执行 `mcporter config add ...`。`manage` 与 `feed` 共用同一套凭证解析逻辑。

### mcporter 配置

**依赖**：

- **Python 3**：运行脚本、写入 `.env`
- **Node.js + mcporter**：`scripts/token/setup.sh` 会尝试注册 mcporter；若未安装，仍可从 `.env` 读取 token 使用

**方式 A：一键脚本（推荐）**

```bash
bash scripts/token/setup.sh 'bot:v1_你的token'
```

若 token 以 `-` 开头：

```bash
bash scripts/token/setup.sh -- '-xxx...'
```

**方式 B：手动注册 mcporter**

```bash
mcporter config add tencent-channel-mcp \
  "https://graph.qq.com/mcp_gateway/open_platform_agent_mcp/mcp" \
  --header "Authorization=Bearer <token>" \
  --transport http \
  --scope home
```

| 提示 / 错误 | 处理 |
|-------------|------|
| **`ERROR:mcporter_not_found`** | 先安装 Node.js，再执行 `npm install -g mcporter` |
| **`mcporterOk: false`** | `~/.openclaw/.env` 通常已成功写入，可继续使用；或改走手动 `mcporter config add` |
| 无 token 文件且未 `mcporter config add` | 执行上方方式 A / B |

> 实现上，token 解析、MCP 调用、鉴权类错误提示等集中在 `scripts/manage/common.py`。

## 快速开始

### 1. 配置 token

```bash
bash scripts/token/setup.sh '<token>'
```

> 请将 `<token>` 替换为真实值；**不要**把包含真实 token 的命令回显给模型。

### 2. 自检（推荐）

```bash
bash scripts/token/verify.sh
```

等价 Python 入口：

```bash
python3 scripts/manage/read/verify_qq_ai_connect_token.py </dev/null
```

探测方式：调用 MCP `get_user_info`，不传 `guild_id` / `member_tinyid`，用于检查“查自己在频道体系下的全局资料”是否可用。

输出不含 token 明文，重点关注字段：

- `valid`
- `tokenSource`
- `userProfileProbeOk`
- `likelyTokenAuthFailure`
- `diagnosis`

当 `likelyTokenAuthFailure=true` 时，表示高度疑似 token / 鉴权问题，应引导到平台重新换票。

## 核心规则

### 频道创建与资料规则

- `create_theme_private_guild` 的内部流程固定为：**预上传头像 → 创建频道 → 补取分享链接**。
- 用户可通过 `community_type` / `visibility` 指定 `public`（公开）或 `private`（私密）；**两者都未传或为空时默认创建公开频道**。
- 仅当用户明确要求私密频道时，再传 `private` / `私密` / `2`。
- 当只提供 `theme` 时，skill 会自动补齐名称和简介；用户显式提供时优先使用用户输入。
- 频道名称限制：**不超过 15 个字**（单个中文、单个英文字母、单个数字各算 1 个字）。
- 创建 **公开频道** 时，名称只能由中文、英文字母和数字组成，不允许特殊符号、空格、emoji 等；**私密频道** 无此字符限制。
- `update_guild_info` 仅校验名称长度与简介长度；由于资料接口无法提供社区公开 / 私密类型，**修改资料时不做“公开频道仅中英数”的本地自动判断**，合规性依赖创建阶段与后续服务端安全审核。
- 频道简介限制：**不超过 300 个字符**。
- 创建频道和修改频道资料时，脚本会自动检查 `sec_rets` / `secRets` 等安全打击字段；若命中，返回 `code=403`，并透传服务端原始 JSON 供模型解释。
- `create_theme_private_guild` 补取分享链接失败时 **不回滚频道**，而是在返回结果中给出告警信息。

### 用户 / 成员 / 搜索规则

- `get_user_info`：
  - `guild_id` 可选：有则查询 **频道内** 上下文资料；无则查询当前账号在 **频道体系下的全局** 资料
  - `member_tinyid` 可选：无则查询自己；有则查询指定成员
  - 两参数支持独立组合
- `push_qq_msg` 的 `status` 支持 `success`、`failed`、`partial`；`dry_run=true` 时只返回预览。
- 频道分享链接固定使用 **短链格式**，不存在长链模式。
- `get_guild_info`、`upload_guild_avatar`、`update_guild_info`、`join_guild` 成功后会自动在返回数据中附带 `share_url`。
- `get_my_join_guild_info` 会为前 **10** 个频道自动补取分享短链；超过 10 个时，其余频道不自动补链。
- `search_guild_content` 支持 4 种范围：
  - `channel` = 搜频道（默认）
  - `feed` = 搜帖子
  - `author` = 搜作者
  - `all` = 全部
- `search_guild_content` 的 `scope` 同时支持中文别名：`频道`、`帖子`、`作者`、`全部`。
- 搜索频道（`scope=channel`）时：
  - 结果数 **≤10**：自动补取频道资料和分享短链
  - 结果数 **>10**：仅返回结果中的 `guild_id` 列表，并附带 `share_url_hint` 提示用户指定目标频道
- 搜索帖子（`scope=feed`，或使用 `get-search-guild-feed`）返回结果后，默认应继续补充：
  1. 对结果中的 `guild_id` 调用 `get_guild_info` 获取频道名称等资料
  2. 调用 `get_guild_share_url` 生成频道分享短链
  3. 向用户展示时包含帖子所属频道名称与分享短链

## 工具入参 Schema

### verify_qq_ai_connect_token

无参数（可选 stdin JSON 业务参数会被忽略），用于连通性探测。

### preview_theme_private_guild

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image_path` | string | 是 | 本地头像图片路径 |
| `theme` | string | 否 | 频道主题 |
| `guild_name` | string | 否 | 频道名称（显式提供时优先使用） |
| `guild_profile` | string | 否 | 频道简介（显式提供时优先使用） |
| `community_type` | string | 否 | `public` / `private` / `公开` / `私密` / `1` / `2`；**不传或为空时默认为公开** |
| `visibility` | string | 否 | `community_type` 的别名；同样默认公开 |
| `create_src` | string | 否 | 创建来源，默认 `pd-mcp` |

### create_theme_private_guild

与 `preview_theme_private_guild` 相同的基础参数，另外支持以下约束说明：

- 创建流程由脚本内部自动完成：`upload_guild_avatar_pre` → `create_guild` → 补取分享短链
- 补取失败不回滚频道，在 `data.share.shareWarning` 中给出告警
- `data.share.url` 是可直接给用户的频道分享短链

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image_path` | string | 是 | 本地头像图片路径 |
| `theme` | string | 否 | 频道主题 |
| `guild_name` | string | 否 | 频道名称 |
| `guild_profile` | string | 否 | 频道简介 |
| `community_type` | string | 否 | `public` / `private` 等；**不传或为空时默认为公开** |
| `visibility` | string | 否 | `community_type` 的别名；默认公开 |
| `create_src` | string | 否 | 创建来源，默认 `pd-mcp` |

### get_my_join_guild_info

无必填参数。

### get_guild_info

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

### get_guild_member_list

**支持分页**：每页最多返回 50 个成员。翻页时将上一次返回的 `next_page_token` 原样传入即可。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `get_num` | integer | 否 | 每页成员数，默认 `20`，最大 `50` |
| `get_type` | string | 否 | 拉取类型：`GET_ALL`（默认）/ `GET_ADMIN` / `GET_ROBOT` / `GET_NORMAL_MEMBER` / `GET_OWNER_AND_ADMIN` |
| `sort_type` | string | 否 | 排序类型：`ROLE_AND_JOIN_TIME`（默认）/ `ROLE_AND_UIN` / `NO_ROLE_AND_UIN` |
| `next_page_token` | string | 否 | 翻页令牌。不传=第一页；传上次返回的 `next_page_token` 即可翻到下一页 |

**返回结构**：

成员按角色分为三个独立列表返回：

| 字段 | 说明 |
|------|------|
| `owners` | 频道主列表（通常只有 1 人） |
| `admins` | 管理员列表 |
| `members` | 普通成员列表 |
| `total_fetched` | 本页返回的成员数（**非频道总人数**） |
| `has_more` | 布尔值，`true` 表示还有下一页 |
| `next_page_token` | 仅当 `has_more=true` 时出现，下次调用原样传入即可翻页 |

每个成员对象包含 `role` 字段（`"频道主"` / `"管理员"` / `"成员"`），以及 `bytesMemberName`（成员名）、`bytesNickName`（昵称）、`uint64Tinyid`（成员 ID）、`uint64JoinTime`（加入时间戳）等。

> **重要**：`total_fetched` 表示 **本页返回的成员数量**，并非频道总人数；如需频道总人数，请使用 `get_guild_info`。

### get_user_info

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 否 | 有则在该频道内查询；无则查询当前账号在频道体系下的全局资料 |
| `member_tinyid` | string | 否 | 无则查自己；有则查指定成员 |

组合示例：

- `{}` → 查询自己全局资料
- `{guild_id}` → 查询自己在该频道内资料
- `{guild_id, member_tinyid}` → 查询他人在该频道内资料
- `{member_tinyid}` → 查询指定成员（无频道上下文，按网关语义）

### get_guild_channel_list

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

### search_guild_content

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 是 | 搜索关键词 |
| `scope` | string | 否 | 搜索范围，默认 `channel` |
| `rank_type` | string | 否 | 排序方式，默认 `CHANNEL_RANK_TYPE_SMART`（智能排序） |
| `session_info` | string | 否 | 翻页上下文，首次不填，后续填上一次返回值 |
| `disable_correction_query` | boolean | 否 | 是否关闭搜索纠错，默认 `false` |

**`scope` 可选值**：

| 值 | 中文别名 | 说明 |
|----|---------|------|
| `channel` | `频道` | 搜索频道（名称、简介等），默认值 |
| `feed` | `帖子` | 搜索帖子（标题、正文） |
| `author` | `作者` | 搜索频道内的用户 / 作者 |
| `all` | `全部` | 同时搜索频道、帖子、作者 |

### get_guild_share_url

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

固定返回短链格式，无需传 `is_short_link`。该工具只处理 **频道分享**，不处理帖子分享。返回中的 `shareInfo` 可能为空，但不影响链接可用。

### push_qq_msg

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_name` | string | 是 | 任务名称 |
| `status` | string | 是 | `success` / `failed` / `partial` |
| `detail` | string | 否 | 任务详情 |
| `dry_run` | boolean | 否 | `true` 时只返回预览结果 |

### join_guild

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |

### modify_member_shut_up

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| guild_id | string | 是 | 频道 ID |
| tiny_id | string | 是 | 成员 tinyid |
| time_stamp | string | 是 | **禁言到期的绝对时间戳**（Unix秒级时间戳，非禁言时长）。例如禁言到 2026-03-23 00:00:00 应传 `1742659200`；传 `0` 表示立即解除禁言 |

### kick_guild_member

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `member_tinyid` | string | 否 | 单个成员 tinyid |
| `member_tinyids` | string[] | 否 | 多个成员 tinyid |

### upload_guild_avatar

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `image_path` | string | 是 | 本地头像图片路径 |

### update_guild_info

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `guild_name` | string | 否 | 新的频道名称 |
| `guild_profile` | string | 否 | 新的频道简介 |

补充说明：

- 脚本会自动对名称和简介做 base64 编码
- 名称不超过 15 字，简介不超过 300 字符
- **修改名称时不做“公开频道仅中英数”的本地校验**，原因是资料接口无法可靠判断频道公开 / 私密类型
- 成功后仍会检查 `sec_rets` / `secRets`；命中时返回 `code=403` 并透传原始 JSON

## 示例

### 预览创建请求

```bash
echo '{"theme":"养虾交流","image_path":"./image.png"}' | python3 scripts/manage/read/preview_theme_private_guild.py
# 默认公开；若要私密：
# echo '{"theme":"养虾交流","image_path":"./image.png","community_type":"private"}' | python3 scripts/manage/read/preview_theme_private_guild.py
```

### 创建频道（默认公开）

```bash
echo '{"theme":"养虾交流","image_path":"./image.png"}' | python3 scripts/manage/write/create_theme_private_guild.py
```

### 创建私密频道

```bash
echo '{"theme":"养虾交流","image_path":"./image.png","community_type":"private"}' | python3 scripts/manage/write/create_theme_private_guild.py
```

### 获取频道成员列表

```bash
echo '{"guild_id":"<GUILD_ID>","get_num":100}' | python3 scripts/manage/read/get_guild_member_list.py
```

### 查询自己的资料

```bash
echo '{}' | python3 scripts/manage/read/get_user_info.py
```

### 获取子频道列表

```bash
echo '{"guild_id":"<GUILD_ID>"}' | python3 scripts/manage/read/get_guild_channel_list.py
```

### 搜索频道内容

```bash
# 搜索频道（默认）
echo '{"keyword":"关键词","scope":"channel"}' | python3 scripts/manage/read/search_guild_content.py

# 搜索帖子
echo '{"keyword":"关键词","scope":"feed"}' | python3 scripts/manage/read/search_guild_content.py

# 搜索作者
echo '{"keyword":"用户名","scope":"author"}' | python3 scripts/manage/read/search_guild_content.py
```

### 获取频道分享链接

```bash
echo '{"guild_id":"<GUILD_ID>"}' | python3 scripts/manage/read/get_guild_share_url.py
```

### 加入频道

```bash
echo '{"guild_id":"<GUILD_ID>"}' | python3 scripts/manage/write/join_guild.py
```

### 禁言成员

**⚠️ 重要**：`time_stamp` 参数是**禁言到期的绝对时间戳**，不是禁言时长。
- 如需禁言 7 天，应计算：`当前时间戳 + 7*24*3600`
- 如需禁言到特定时间（如 2026-03-30 00:00），应传该时刻的时间戳
- 传 `0` 表示立即解除禁言

```bash
echo '{"guild_id":"<GUILD_ID>","tiny_id":"<MEMBER_TINYID>","time_stamp":"<UNIX_TIMESTAMP>"}' | python3 scripts/manage/write/modify_member_shut_up.py
```

**示例**：禁言 7 天
```bash
# 假设当前时间戳为 1742572800，禁言到期时间戳为 1742572800 + 604800 = 1743177600
echo '{"guild_id":"123456","tiny_id":"789","time_stamp":"1743177600"}' | python3 scripts/manage/write/modify_member_shut_up.py
```

### 修改频道头像

```bash
echo '{"guild_id":"<GUILD_ID>","image_path":"./image.png"}' | python3 scripts/manage/write/upload_guild_avatar.py
```

### 修改频道资料

```bash
echo '{"guild_id":"<GUILD_ID>","guild_name":"新频道名称","guild_profile":"新频道简介"}' | python3 scripts/manage/write/update_guild_info.py
```

### 给自己发 QQ 消息

```bash
echo '{"task_name":"发表帖子","status":"success","detail":"帖子已发表"}' | python3 scripts/manage/write/push_qq_msg.py
```

## 返回与错误码

- 成功时通常返回：`{"code": 0, "msg": "success", "data": ...}`
- 失败时通常返回：`{"code": 非0, "msg": "...", "data": null}`

| code | 说明 |
|------|------|
| `0` | 成功 |
| `1` | 入参错误 |
| `100` | Token 缺失或无效 |
| `200` | MCP 返回错误 |
| `300` | 网络请求失败 |
