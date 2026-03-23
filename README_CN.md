# tencent-channel-community

<p align="center">
  <img src="https://grouppro.gtimg.cn/wupload/xy/qq_channel/common_pic/kRjatyOL.png" alt="tencent-channel-community" width="120">
</p>

<p align="center">
  <strong>🏠 一站式腾讯频道社区管理技能</strong>
</p>

<p align="center">
  简体中文 | <a href="./README.md">English</a>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License">
</p>


---

## 📖 简介

**tencent-channel-community** 是一款全功能的腾讯频道社区管理技能，涵盖频道创建与管理、成员管理、帖子发布、内容审核等完整能力，让 AI 助手能够高效地帮助你管理腾讯频道社区。

🔗 **官方网站**: [https://connect.qq.com/ai](https://connect.qq.com/ai)

---

## ✨ 功能特性

### 📌 频道管理

- **创建频道** - 创建公开或私密主题频道，支持预览创建效果
- **频道设置** - 查看/修改频道资料、头像、名称、简介
- **成员管理** - 查看已加入的频道、频道成员、子频道列表
- **搜索功能** - 搜索频道、帖子、作者
- **分享功能** - 获取频道分享链接
- **管理操作** - 加入频道、禁言/踢人（需管理员权限）

### 📰 内容管理（帖子）

- **浏览帖子** - 浏览频道主页或指定板块的帖子列表，支持翻页
- **帖子详情** - 查看帖子详情、评论与回复
- **发布编辑** - 发帖、改帖、删帖（支持带图发帖）
- **互动功能** - 评论、回复、点赞
- **运营工具** - 内容巡检、问答类自动回复

---

## 🚀 快速开始

### 环境要求

- **Python** >= 3.10
- **Node.js**（mcporter 需要）
- **Token**：从 [https://connect.qq.com/ai](https://connect.qq.com/ai) 获取

### 安装方式

#### 方式一：ClawHub（推荐）

```bash
npx clawhub install tencent-channel-community
```

#### 方式二：SkillHub

```bash
npx skillhub install tencent-channel-community
```

#### 方式三：GitHub

```bash
git clone https://github.com/anthropics/skill-tencent-channel-community.git
cd skill-tencent-channel-community
```

#### 方式四：官方 CDN

```bash
bash scripts/update.sh
```

### Token 配置

1. 从 [https://connect.qq.com/ai](https://connect.qq.com/ai) 获取 Token

2. 写入 Token：
```bash
bash scripts/token/setup.sh '<your-token>'
```

3. 验证连接：
```bash
bash scripts/token/verify.sh
```

### 更新技能包

```bash
# 交互式更新（下载 → 对比 → 确认 → 备份 → 覆盖）
bash scripts/update.sh

# 仅展示差异，不实际更新
bash scripts/update.sh --dry-run

# 跳过确认直接更新
bash scripts/update.sh --force
```

> 💡 更新时自动保留 `.env` 等本地配置，变更文件会备份到 `.bak-<timestamp>/` 目录。

---

## 📚 使用示例

### 频道管理示例

```bash
# 获取已加入的频道列表
python3 scripts/manage/read/get_my_join_guild_info.py

# 获取频道资料
echo '{"guild_id":"<频道ID>"}' | python3 scripts/manage/read/get_guild_info.py

# 获取频道成员列表
echo '{"guild_id":"<频道ID>","get_num":50}' | python3 scripts/manage/read/get_guild_member_list.py

# 搜索频道
echo '{"keyword":"游戏","scope":"channel"}' | python3 scripts/manage/read/search_guild_content.py

# 创建公开主题频道
echo '{"theme":"游戏社区","name":"我的游戏频道","intro":"欢迎加入！"}' | python3 scripts/manage/write/create_theme_private_guild.py
```

### 内容管理示例

```bash
# 获取频道主页热门帖子
echo '{"guild_id":"<频道ID>","get_type":1}' | python3 scripts/feed/read/get_guild_feeds.py

# 获取最新帖子
echo '{"guild_id":"<频道ID>","get_type":2,"sort_option":1}' | python3 scripts/feed/read/get_guild_feeds.py

# 获取帖子详情
echo '{"guild_id":"<频道ID>","feed_id":"<帖子ID>"}' | python3 scripts/feed/read/get_feed_detail.py

# 发布文字帖子
echo '{"guild_id":"<频道ID>","channel_id":"<板块ID>","title":"你好","content":"我的第一篇帖子！","feed_type":1}' | python3 scripts/feed/write/publish_feed.py

# 发布带图帖子
echo '{"guild_id":"<频道ID>","channel_id":"<板块ID>","title":"分享图片","content":"看看这个！","feed_type":1,"file_paths":["/path/to/image.jpg"]}' | python3 scripts/feed/write/publish_feed.py
```

---

## 🔧 可用工具

### 频道管理工具

| 工具名 | 说明 |
|--------|------|
| `verify` | 校验 Token 和 MCP 连通性 |
| `get_my_join_guild_info` | 获取当前账号已加入的频道列表 |
| `get_guild_info` | 获取频道资料 |
| `get_guild_member_list` | 获取频道成员列表（支持分页） |
| `get_guild_channel_list` | 获取子频道列表 |
| `get_user_info` | 获取成员资料 |
| `search_guild_content` | 搜索频道、帖子、作者或全部 |
| `get_guild_share_url` | 获取频道分享链接 |
| `preview_theme_private_guild` | 预览创建频道（不实际创建） |
| `create_theme_private_guild` | 创建公开/私密主题频道 |
| `join_guild` | 加入频道 |
| `modify_member_shut_up` | 禁言/解禁成员 |
| `kick_guild_member` | 踢出频道成员 |
| `upload_guild_avatar` | 修改频道头像 |
| `update_guild_info` | 修改频道名称和简介 |
| `push_qq_msg` | 发送 QQ 消息给自己 |

### 内容管理工具

| 工具名 | 说明 |
|--------|------|
| `get-guild-feeds` | 获取频道主页帖子（热门/最新/最相关） |
| `get-channel-timeline-feeds` | 获取指定板块帖子 |
| `get-feed-detail` | 获取帖子详情 |
| `get-feed-comments` | 获取帖子评论 |
| `get-next-page-replies` | 获取下一页回复 |
| `get-search-guild-feed` | 按关键词搜索帖子 |
| `publish-feed` | 发布新帖子（文字/图片） |
| `alter-feed` | 修改帖子 |
| `del-feed` | 删除帖子 |
| `do-comment` | 发表/删除评论 |
| `do-reply` | 发表/删除回复 |
| `do-like` | 评论或回复点赞/取消点赞 |
| `do-feed-prefer` | 帖子点赞/取消点赞 |
| `upload-image` | 上传媒体文件（publish-feed 自动调用） |
| `auto-clean-channel-feeds` | 内容巡检扫描 |
| `channel-qa-responder` | 问答自动回复 |

---

## ⚠️ 注意事项

### 权限说明

- **管理操作**（禁言、踢人、修改频道设置）需要 **管理员权限**
- 技能会自动校验权限，非管理员无法执行管理操作

### 频道名称规则

- 最多 **15 个字**（中文、英文字母、数字各算 1 个字）
- **公开频道**：名称只能由中文、英文字母和数字组成（不允许特殊符号、空格、emoji）
- **私密频道**：无字符限制

### 频道简介规则

- 最多 **300 个字符**

### Token 问题排查

| 错误提示 | 解决方案 |
|----------|----------|
| `ERROR:mcporter_not_found` | 先安装 Node.js，再执行 `npm install -g mcporter` |
| `mcporterOk: false` | mcporter 注册失败；`.env` 通常已成功，可继续使用 |
| 鉴权错误（如 `retCode 8011`） | 到 [connect.qq.com/ai](https://connect.qq.com/ai) 重新获取 Token 后重新执行 `setup.sh` |

---

## 📁 项目结构

```
tencent-channel-community/
├── SKILL.md                    # AI 技能说明文件
├── scripts/
│   ├── update.sh               # 技能更新脚本
│   ├── token/
│   │   ├── setup.sh            # Token 写入
│   │   └── verify.sh           # Token 校验
│   ├── manage/
│   │   ├── read/               # 频道读取操作
│   │   └── write/              # 频道写入操作
│   └── feed/
│       ├── read/               # 内容读取操作
│       ├── write/              # 内容写入操作
│       └── operation/          # 运营工具
├── references/
│   ├── skill-intro.md          # 功能介绍
│   ├── manage-reference.md     # 频道管理参考
│   └── feed-reference.md       # 内容管理参考
└── README.md
```

---

## 🤝 反馈与社区

加入我们的腾讯频道社区，获取支持和参与讨论：

🔗 **[腾讯AI互联开发社区](https://pd.qq.com/s/1sly18j1i?b=9)**

---

## 📄 许可证

许可证：MIT

---

## 👥 作者

**Tencent**

---

<p align="center">
  Made with ❤️ for 腾讯频道社区
</p>
