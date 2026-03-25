# 成员管理（manage-member）

覆盖频道成员的查询、个人资料、禁言与踢人操作。

---

## 一、脚本路由表

| 用户意图 | 脚本 | 关键约束 | 缺参补齐 |
|---------|------|---------|---------|
| 查看成员列表 / 找管理员 / 获取 tiny_id | `get_guild_member_list.py` | 需要 `guild_id`；支持分页 | 缺 `guild_id` → 先 `get_my_join_guild_info`（见 `manage-guild.md`） |
| 按昵称搜索成员 | `guild_member_search.py` | 需要 `guild_id` + `keyword` | 缺 `guild_id` → 先 `get_my_join_guild_info`（见 `manage-guild.md`） |
| 查自己的资料 / 指定成员资料 | `get_user_info.py` | 查个人资料，不替代成员列表 | 缺成员 ID → 优先 `get_guild_member_list` |
| 禁言 / 解禁 | `modify_member_shut_up.py` | `time_stamp=0` 表示解除禁言 | 缺 `tiny_id` → 先 `get_guild_member_list` |
| 踢成员 | `kick_guild_member.py` | 支持单个 / 批量 | 缺 `tiny_id` → 先 `get_guild_member_list` |
| **频道类任务**（创建 / 查频道 / 修改资料等） | **转 `manage-guild.md`** | 不应在此文件处理 | — |
| **帖子类任务**（查帖子 / 发帖 / 评论等） | **转 `feed-reference.md`** | 不应走 manage | — |

> 脚本位于 `scripts/manage/read/` 或 `scripts/manage/write/`。

---

## 二、分流误区

- ❌ 只是想找成员 ID → 不要先用 `get_user_info`，**优先** `get_guild_member_list`
- ❌ 按昵称找人 → 不要翻遍成员列表，**优先** `guild_member_search`
- ❌ `get_user_info` 和 `get_guild_member_list` 混淆 → `get_user_info` 查个人资料（可不传 `guild_id`），`get_guild_member_list` 查频道成员列表并获取 `tiny_id`
- ❌ 禁言时 `time_stamp` 传了时长 → 必须传 **绝对 Unix 时间戳**（`当前时间戳 + 时长秒数`），`0` = 立即解禁

---

## 三、认证与配置

- **凭证链路**：`get_token() → .env → mcporter`（与 manage-guild 相同）
- **禁止** 在业务 stdin JSON 中传 `token`
- 所有 manage 工具通过 **stdin JSON** 传入业务参数
- `guild_id`、`tiny_id`、`member_tinyid` 等标识符推荐用 **字符串** 传参，避免大整数精度问题

> 首次配置 token 见 `manage-guild.md` 的"认证与配置"章节。

---

## 四、工具入参 Schema

### get_guild_member_list

查询频道成员列表（包含真人和 AI 成员），支持分页。翻页时传上次返回的 `next_page_token`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `get_num` | integer | 否 | 每页成员数提示，默认 `20`，最大 `50`（实际返回数由远端 API 决定，可能超过该值） |
| `get_type` | string | 否 | `GET_ALL`（默认）= 全部成员；`GET_ROBOT` = **仅**查机器人列表（用户明确要求"看看有哪些机器人"时才用） |
| `sort_type` | string | 否 | 排序方式，默认 `ROLE_AND_JOIN_TIME`，一般不需要改 |
| `next_page_token` | string | 否 | 翻页令牌，原样传回上一页返回的值 |

**返回结构**：

| 字段 | 说明 |
|------|------|
| `owners` | 频道主列表（通常 1 人） |
| `admins` | 管理员列表（含 AI 成员，如频小星） |
| `members` | 普通成员列表 |
| `total_fetched` | 本页返回数（**非频道总人数**，总人数用 `get_guild_info`） |
| `has_more` / `next_page_token` | 是否有下一页 / 翻页令牌 |

每个成员含 `role`（`"频道主"` / `"管理员"` / `"成员"`）、`bytesMemberName`（昵称）、`uint64Tinyid`、`uint64JoinTime`。AI 成员额外含 `isAi: true`。

> **时间戳可读化**：返回中的时间戳字段（`joinTime` / `uint32_join_time`、`shutupExpireTime` / `uint32_shutup_expire_time` 等）会自动附带 `{字段名}_human` 可读值（北京时间），禁言时间戳为 `0` 时显示 `"无禁言"`。向用户展示时直接使用 `_human` 字段即可。

#### 分页调用示例

**第一次调用**（不传 `next_page_token`）：

```json
{ "guild_id": "123456" }
```

返回：

```json
{
  "owners": [...],
  "admins": [...],
  "members": [...],
  "total_fetched": 20,
  "has_more": true,
  "next_page_token": "eyJzdGFydF9p...",
  "next_page_token_hint": "下一页请传入 next_page_token 参数，值为上面的 next_page_token 原样传回"
}
```

**第二次调用**（传回上一次返回的 `next_page_token`）：

```json
{ "guild_id": "123456", "next_page_token": "eyJzdGFydF9p..." }
```

返回：

```json
{
  "owners": [...],
  "admins": [...],
  "members": [...],
  "total_fetched": 15,
  "has_more": false
}
```

> **注意**：`next_page_token` 是脚本编码后的不透明令牌，**必须原样传回**，不要尝试解析或修改其内容。当 `has_more` 为 `false` 时，表示所有成员已拉取完毕，不再返回 `next_page_token`。

### get_user_info

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 否 | 有=频道内资料；无=全局资料 |
| `member_tinyid` | string | 否 | 无=查自己；有=查指定成员 |

组合：`{}` → 自己全局 / `{guild_id}` → 自己频道内 / `{guild_id, member_tinyid}` → 他人频道内 / `{member_tinyid}` → 指定成员无频道上下文

**返回字段**（均在 `msgUserInfo` 内）：

| 字段 | 说明 |
|------|------|
| `bytesNickName` | 昵称 |
| `uint32Gender` | 性别（1=男，2=女） |
| `bytesCountry` / `bytesProvince` / `bytesCity` | 所在地（国家/省/市） |
| `uint64MemberTinyid` | 成员 tinyid |
| `isGuildAuthor` | 是否频道创作者（有值=是频道创作者，不返回=非创作者）；需传 `guild_id` 才有意义 |

### modify_member_shut_up

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `tiny_id` | string | 是 | 成员 tinyid |
| `time_stamp` | string | 是 | **禁言到期的绝对 Unix 时间戳**（非时长）；`0` = 立即解禁 |

> 如需禁言 7 天，计算：`当前时间戳 + 7×86400`。

### kick_guild_member

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `member_tinyid` | string | 否 | 单个成员 tinyid |
| `member_tinyids` | string[] | 否 | 多个成员 tinyid |

### guild_member_search

按昵称关键词搜索频道内成员，支持分页。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `guild_id` | string | 是 | 频道 ID |
| `keyword` | string | 是 | 搜索关键词（匹配成员昵称） |
| `num` | integer | 否 | 每页数量，默认 `20`，最大 `50` |
| `pos` | string | 否 | 翻页位置，首次不传，翻页时传上次返回的 `next_pos` |

**返回结构**：

| 字段 | 说明 |
|------|------|
| `members` | 匹配的成员列表，每项含 `nickname`、`tinyid`、`joinTime` |
| `match_count` | 本次匹配的成员数 |
| `has_more` / `next_pos` | 翻页信息 |


