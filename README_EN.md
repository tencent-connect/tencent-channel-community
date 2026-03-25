# tencent-channel-community

<p align="center">
  <img src="https://grouppro.gtimg.cn/wupload/xy/qq_channel/common_pic/kRjatyOL.png" alt="tencent-channel-community" width="120">
</p>

<p align="center">
  <strong>🏠 All-in-one Tencent Channel Community Management Skill</strong>
</p>

<p align="center">
  <a href="./README.md">简体中文</a> | English
</p>
<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.1-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License">
</p>

---

## 📖 Introduction

**tencent-channel-community** is a full-featured Tencent Channel community management skill that covers channel creation and administration, member operations, post publishing, content moderation, and more, enabling AI assistants to manage Tencent Channel communities efficiently.

🔗 **Official Website**: [https://connect.qq.com/ai](https://connect.qq.com/ai)

---

## ✨ Features

### 📌 Channel Management

- **Create Channels** - Create public or private themed channels with preview support
- **Channel Settings** - View or update channel profile, avatar, name, and description
- **Member Management** - View joined channels, channel members, and sub-channel lists, with member search by nickname
- **Search** - Search channels, posts, and authors
- **Sharing** - Get channel and post share links
- **Admin Actions** - Join channels with verification pre-check, mute members, or remove members (admin permission required)

### 📰 Content Management (Posts)

- **Browse Posts** - Browse channel homepage posts or posts in a specific sub-channel with pagination support
- **Post Details** - View post details, comments, and replies, with standalone post share-link retrieval
- **Publishing & Editing** - Create, edit, and delete posts, including image and video posts
- **Interactions** - Comment, reply, and like content
- **Operations Tools** - Content inspection and Q&A auto-reply tools

---

## 🚀 Quick Start

### Requirements

- **Python** >= 3.10
- **Node.js** (required by mcporter)
- **Token**: Obtain it from [https://connect.qq.com/ai](https://connect.qq.com/ai)

### Installation

Get the one-click installation command from [https://connect.qq.com/ai](https://connect.qq.com/ai)


---

## 📚 Usage Examples

### Create a Channel
![Create a Channel](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E5%88%9B%E5%BB%BA%E9%A2%91%E9%81%93.png)

### Get Joined Channels
![Get Joined Channels](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E8%8E%B7%E5%8F%96%E6%88%91%E5%8A%A0%E5%85%A5%E7%9A%84%E9%A2%91%E9%81%93.png)

### Query Channel Profile
![Query Channel Profile](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E6%9F%A5%E8%AF%A2%E9%A2%91%E9%81%93%E8%B5%84%E6%96%99.png)

### Member Management
![Member Management](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E6%88%90%E5%91%98%E7%AE%A1%E7%90%86.png)

### Get the Latest 5 Posts
![Get the Latest 5 Posts](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E8%8E%B7%E5%8F%96%E6%9C%80%E6%96%B0%E7%9A%845%E6%9D%A1%E5%B8%96%E5%AD%90.png)

### Query and Summarize Posts
![Query and Summarize Posts](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E6%9F%A5%E8%AF%A2%E5%B8%96%E5%AD%90%E5%B9%B6%E6%80%BB%E7%BB%93.png)

### Publish an Image Post
![Publish an Image Post](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E5%8F%91%E8%A1%A8%E5%B8%A6%E5%9B%BE%E5%B8%96%E5%AD%90.png)

### Like and Comment
![Like and Comment](https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/example/%E7%82%B9%E8%B5%9E%E5%B9%B6%E8%AF%84%E8%AE%BA.png)

---

## 🔧 Available Tools

### Channel Management Tools

| Tool | Description |
|------|-------------|
| `verify` | Verify the token and MCP connectivity |
| `get_my_join_guild_info` | Get the list of channels joined by the current account |
| `get_guild_info` | Get channel profile information |
| `get_guild_member_list` | Get the channel member list with pagination support |
| `guild_member_search` | Search channel members by nickname |
| `get_guild_channel_list` | Get the list of sub-channels |
| `get_user_info` | Get member profile information |
| `search_guild_content` | Search channels, posts, authors, or all content |
| `get_guild_share_url` | Get the channel share link |
| `get_join_guild_setting` | View channel join settings and verification mode |
| `preview_theme_private_guild` | Preview channel creation without actually creating it |
| `create_theme_private_guild` | Create a public or private themed channel |
| `join_guild` | Join a channel |
| `modify_member_shut_up` | Mute or unmute a member |
| `kick_guild_member` | Remove a member from the channel |
| `upload_guild_avatar` | Update the channel avatar |
| `update_guild_info` | Update the channel name and description |
| `push_qq_msg` | Send a QQ message to yourself |

### Content Management Tools

| Tool | Description |
|------|-------------|
| `get-guild-feeds` | Get channel homepage posts (hot, latest, or most relevant) |
| `get-channel-timeline-feeds` | Get posts from a specified sub-channel |
| `get-feed-detail` | Get post details |
| `get-feed-comments` | Get post comments |
| `get-next-page-replies` | Get the next page of replies |
| `get-feed-share-url` | Get the share short link for a specified post |
| `get-search-guild-feed` | Search posts by keyword |
| `publish-feed` | Publish a new post (text, image, or video) |
| `alter-feed` | Edit a post |
| `del-feed` | Delete a post |
| `do-comment` | Add or delete a comment |
| `do-reply` | Add or delete a reply |
| `do-like` | Like or unlike a comment or reply |
| `do-feed-prefer` | Like or unlike a post |
| `upload-image` | Upload media files (automatically used by `publish-feed`) |
| `auto-clean-channel-feeds` | Run content inspection scans |
| `channel-qa-responder` | Q&A auto-reply |

---

## ⚠️ Notes

### Permission Notes
All operations use the permissions of the user associated with the current token.

---

## 📁 Project Structure

```
tencent-channel-community/
├── SKILL.md                    # AI skill description
├── scripts/
│   ├── token/
│   │   ├── setup.sh            # Token setup
│   │   └── verify.sh           # Token verification
│   ├── manage/
│   │   ├── read/               # Channel read operations
│   │   └── write/              # Channel write operations
│   └── feed/
│       ├── read/               # Content read operations
│       ├── write/              # Content write operations
│       └── operation/          # Operations tools
├── references/
│   ├── manage-guild.md         # Channel management reference
│   ├── manage-member.md        # Member management reference
│   └── feed-reference.md       # Content management reference
├── README.md
└── README_EN.md
```

---

## 🤝 Feedback & Community

Join our Tencent Channel community for support and discussion:

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
