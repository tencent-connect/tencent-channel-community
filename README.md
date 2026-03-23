# tencent-channel-community

<p align="center">
  <img src="https://grouppro.gtimg.cn/wupload/xy/qq_channel/common_pic/kRjatyOL.png" alt="tencent-channel-community" width="120">
</p>

<p align="center">
  <strong>🏠 One-stop Tencent Channel Community Management Skill</strong>
</p>

<p align="center">
  <a href="./README_CN.md">简体中文</a> | English
</p>
<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License">
</p>


---

## 📖 Introduction

**tencent-channel-community** is a comprehensive skill for managing Tencent Channel (腾讯频道) communities. It provides full-featured channel management and content operations capabilities, enabling AI agents to create channels, manage members, publish posts, moderate content, and more.

🔗 **Official Website**: [https://connect.qq.com/ai](https://connect.qq.com/ai)

---

## ✨ Features

### 📌 Channel Management

- **Create Channels** - Create public or private theme channels with preview support
- **Channel Settings** - View and modify channel profile, avatar, name, and description
- **Member Management** - View joined channels, member lists, and sub-channel lists
- **Search** - Search channels, posts, and authors
- **Share** - Generate channel share links
- **Moderation** - Join channels, mute members, kick members (with proper permissions)

### 📰 Content Management (Posts)

- **Browse Posts** - View channel homepage or board-specific post lists with pagination
- **Post Details** - View post details, comments, and replies
- **Create & Edit** - Publish, modify, and delete posts (supports images)
- **Engagement** - Comment, reply, and like posts
- **Operations** - Content moderation and Q&A auto-reply capabilities

---

## 🚀 Quick Start

### Prerequisites

- **Python** >= 3.10
- **Node.js** (required for mcporter)
- **Token** from [https://connect.qq.com/ai](https://connect.qq.com/ai)

### Installation

#### Option 1: ClawHub (Recommended)

```bash
npx clawhub install tencent-channel-community
```

#### Option 2: SkillHub

```bash
npx skillhub install tencent-channel-community
```

#### Option 3: GitHub

```bash
git clone https://github.com/anthropics/skill-tencent-channel-community.git
cd skill-tencent-channel-community
```

#### Option 4: Official CDN

```bash
bash scripts/update.sh
```

### Token Setup

1. Get your token from [https://connect.qq.com/ai](https://connect.qq.com/ai)

2. Set up the token:
```bash
bash scripts/token/setup.sh '<your-token>'
```

3. Verify the connection:
```bash
bash scripts/token/verify.sh
```

### Update Skill

```bash
# Interactive update (download → diff → confirm → backup → overwrite)
bash scripts/update.sh

# Preview changes only (dry run)
bash scripts/update.sh --dry-run

# Force update without confirmation
bash scripts/update.sh --force
```

> 💡 Updates automatically preserve local configurations (e.g., `.env`). Changed files are backed up to `.bak-<timestamp>/` directory.

---

## 📚 Usage

### Channel Management Examples

```bash
# Get joined channels
python3 scripts/manage/read/get_my_join_guild_info.py

# Get channel info
echo '{"guild_id":"<GUILD_ID>"}' | python3 scripts/manage/read/get_guild_info.py

# Get channel members
echo '{"guild_id":"<GUILD_ID>","get_num":50}' | python3 scripts/manage/read/get_guild_member_list.py

# Search channels
echo '{"keyword":"gaming","scope":"channel"}' | python3 scripts/manage/read/search_guild_content.py

# Create a public theme channel
echo '{"theme":"Gaming Community","name":"My Gaming Channel","intro":"Welcome!"}' | python3 scripts/manage/write/create_theme_private_guild.py
```

### Content Management Examples

```bash
# Get hot posts from channel homepage
echo '{"guild_id":"<GUILD_ID>","get_type":1}' | python3 scripts/feed/read/get_guild_feeds.py

# Get latest posts
echo '{"guild_id":"<GUILD_ID>","get_type":2,"sort_option":1}' | python3 scripts/feed/read/get_guild_feeds.py

# Get post details
echo '{"guild_id":"<GUILD_ID>","feed_id":"<FEED_ID>"}' | python3 scripts/feed/read/get_feed_detail.py

# Publish a text post
echo '{"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>","title":"Hello","content":"My first post!","feed_type":1}' | python3 scripts/feed/write/publish_feed.py

# Publish a post with images
echo '{"guild_id":"<GUILD_ID>","channel_id":"<CHANNEL_ID>","title":"Photo Share","content":"Check this out!","feed_type":1,"file_paths":["/path/to/image.jpg"]}' | python3 scripts/feed/write/publish_feed.py
```

---

## 🔧 Available Tools

### Channel Management Tools

| Tool | Description |
|------|-------------|
| `verify` | Verify token and MCP connection |
| `get_my_join_guild_info` | Get list of joined channels |
| `get_guild_info` | Get channel profile |
| `get_guild_member_list` | Get channel member list (supports pagination) |
| `get_guild_channel_list` | Get sub-channel list |
| `get_user_info` | Get member profile |
| `search_guild_content` | Search channels, posts, authors, or all |
| `get_guild_share_url` | Get channel share link |
| `preview_theme_private_guild` | Preview channel creation (dry run) |
| `create_theme_private_guild` | Create public/private theme channel |
| `join_guild` | Join a channel |
| `modify_member_shut_up` | Mute/unmute members |
| `kick_guild_member` | Kick members from channel |
| `upload_guild_avatar` | Update channel avatar |
| `update_guild_info` | Update channel name and description |
| `push_qq_msg` | Send QQ notification to yourself |

### Content Management Tools

| Tool | Description |
|------|-------------|
| `get-guild-feeds` | Get channel homepage posts (hot/latest/relevant) |
| `get-channel-timeline-feeds` | Get board-specific posts |
| `get-feed-detail` | Get post details |
| `get-feed-comments` | Get post comments |
| `get-next-page-replies` | Get next page of replies |
| `get-search-guild-feed` | Search posts by keyword |
| `publish-feed` | Publish new post (text/images) |
| `alter-feed` | Edit post |
| `del-feed` | Delete post |
| `do-comment` | Add/delete comment |
| `do-reply` | Add/delete reply |
| `do-like` | Like/unlike comment or reply |
| `do-feed-prefer` | Like/unlike post |
| `upload-image` | Upload media (auto-called by publish-feed) |
| `auto-clean-channel-feeds` | Content moderation scanning |
| `channel-qa-responder` | Q&A auto-reply |

---

## ⚠️ Important Notes

### Permissions

- **Management operations** (mute, kick, modify channel settings) require **administrator permissions**
- The skill automatically validates permissions before executing management operations

### Channel Name Rules

- Maximum **15 characters** (Chinese, English letters, and numbers each count as 1)
- **Public channels**: Only Chinese, English letters, and numbers allowed (no special characters, spaces, or emojis)
- **Private channels**: No character restrictions

### Channel Description

- Maximum **300 characters**

### Token Issues

| Error | Solution |
|-------|----------|
| `ERROR:mcporter_not_found` | Install Node.js first, then run `npm install -g mcporter` |
| `mcporterOk: false` | mcporter registration failed; `.env` usually works, you can continue |
| Auth error (e.g., `retCode 8011`) | Get a new token from [connect.qq.com/ai](https://connect.qq.com/ai) and run `setup.sh` again |

---

## 📁 Project Structure

```
tencent-channel-community/
├── SKILL.md                    # AI instruction file
├── scripts/
│   ├── update.sh               # Skill update script
│   ├── token/
│   │   ├── setup.sh            # Token setup
│   │   └── verify.sh           # Token verification
│   ├── manage/
│   │   ├── read/               # Channel read operations
│   │   └── write/              # Channel write operations
│   └── feed/
│       ├── read/               # Content read operations
│       ├── write/              # Content write operations
│       └── operation/          # Operational tools
├── references/
│   ├── skill-intro.md          # Feature introduction
│   ├── manage-reference.md     # Channel management reference
│   └── feed-reference.md       # Content management reference
└── README.md
```

---

## 🤝 Feedback & Community

Join our Tencent Channel community for support and discussions:

🔗 **[Tencent AI Connect Developer Community](https://pd.qq.com/s/1sly18j1i?b=9)**

---

## 📄 License

License: MIT

---

## 👥 Author

**Tencent**

---

<p align="center">
  Made with ❤️ for Tencent Channel Community
</p>
