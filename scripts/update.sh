#!/usr/bin/env bash
# 从 CDN 拉取最新的 tencent-channel-community 技能包并更新本地文件。
#
# 用法（在 skill 根目录执行）：
#   bash scripts/update.sh
#
# 可选参数：
#   --dry-run   仅下载并展示差异，不实际覆盖
#   --force     跳过确认直接更新
#
# 更新逻辑：
#   1. 从 CDN 下载最新 skill zip 和 libsliceupload zip 到临时目录
#   2. 解压并对比本地文件差异（skill 文件 + 二进制依赖）
#   3. 备份将要被覆盖的文件（.bak-<timestamp>）
#   4. 用 CDN 版本覆盖本地文件（保留 .env、token 配置）
#
# CDN 地址：
CDN_URL="https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/tencent-channel-community.zip"
# libsliceupload 二进制依赖 CDN 地址：
LIBSLICE_CDN_URL="https://qqchannel-profile-1251316161.file.myqcloud.com/qq-ai-connect/references/libsliceupload.zip"
# zip 内顶层目录名：
ZIP_TOP_DIR="tencent-channel-community"

set -eo pipefail

# ── 定位 skill 根目录 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 参数解析 ──
DRY_RUN=false
FORCE=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --force)   FORCE=true ;;
    -h|--help)
      cat <<'EOF'
用法:
  bash scripts/update.sh [--dry-run] [--force]

选项:
  --dry-run   仅下载并展示变更文件列表，不实际更新
  --force     跳过确认提示直接更新

说明:
  从 CDN 下载最新技能包和 libsliceupload 依赖，对比本地差异后覆盖更新。
  更新时会自动保留以下内容：
    - .env / .env.* 配置文件
    - __pycache__/ 缓存目录
EOF
      exit 0
      ;;
    *)
      echo "未知参数: $arg" >&2
      exit 1
      ;;
  esac
done

# ── 检查依赖 ──
if ! command -v curl &>/dev/null; then
  echo "❌ 错误: 需要 curl，请先安装" >&2
  exit 1
fi
if ! command -v unzip &>/dev/null; then
  echo "❌ 错误: 需要 unzip，请先安装" >&2
  exit 1
fi

# ── 创建临时目录 ──
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ZIP_FILE="$TMP_DIR/tencent-channel-community.zip"
EXTRACT_DIR="$TMP_DIR/extracted"

echo "📦 正在从 CDN 下载最新技能包..."
echo "   URL: $CDN_URL"

HTTP_CODE=$(curl -sL -w "%{http_code}" -o "$ZIP_FILE" "$CDN_URL")
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "❌ 下载失败 (HTTP $HTTP_CODE)" >&2
  exit 1
fi

ZIP_SIZE=$(wc -c < "$ZIP_FILE" | tr -d ' ')
echo "✅ 下载完成 ($(( ZIP_SIZE / 1024 ))KB)"

# ── 解压 ──
echo ""
echo "📂 正在解压..."
mkdir -p "$EXTRACT_DIR"
unzip -q -o "$ZIP_FILE" -d "$EXTRACT_DIR"

CDN_ROOT="$EXTRACT_DIR/$ZIP_TOP_DIR"
if [[ ! -d "$CDN_ROOT" ]]; then
  echo "❌ 错误: zip 包内未找到 $ZIP_TOP_DIR/ 目录" >&2
  exit 1
fi

# ── 读取版本信息 ──
LOCAL_VERSION="unknown"
CDN_VERSION="unknown"
if [[ -f "$SKILL_ROOT/_meta.json" ]]; then
  LOCAL_VERSION=$(python3 -c "import json; print(json.load(open('$SKILL_ROOT/_meta.json')).get('version','unknown'))" 2>/dev/null || echo "unknown")
fi
if [[ -f "$CDN_ROOT/_meta.json" ]]; then
  CDN_VERSION=$(python3 -c "import json; print(json.load(open('$CDN_ROOT/_meta.json')).get('version','unknown'))" 2>/dev/null || echo "unknown")
fi

echo ""
echo "📋 版本信息:"
echo "   本地版本: $LOCAL_VERSION"
echo "   CDN 版本: $CDN_VERSION"

# ── 对比差异 ──
echo ""
echo "🔍 正在对比文件差异..."

# 需要保留不覆盖的文件/目录模式
PRESERVE_PATTERNS=(
  ".env"
  ".env.*"
  "__pycache__"
  "*.pyc"
)

# 收集 CDN 包中的文件列表（相对路径）
CDN_FILES=()
while IFS= read -r -d '' f; do
  CDN_FILES+=("${f#$CDN_ROOT/}")
done < <(find "$CDN_ROOT" -type f -print0 | sort -z)

CHANGED_FILES=()
NEW_FILES=()
UNCHANGED_FILES=()

for rel_path in "${CDN_FILES[@]}"; do
  local_file="$SKILL_ROOT/$rel_path"
  cdn_file="$CDN_ROOT/$rel_path"

  if [[ ! -f "$local_file" ]]; then
    NEW_FILES+=("$rel_path")
  elif ! diff -q "$local_file" "$cdn_file" &>/dev/null; then
    CHANGED_FILES+=("$rel_path")
  else
    UNCHANGED_FILES+=("$rel_path")
  fi
done

# 检测本地有但 CDN 没有的文件（可能被删除的）
LOCAL_ONLY_FILES=()
while IFS= read -r -d '' f; do
  rel_path="${f#$SKILL_ROOT/}"
  # 跳过保留的文件模式
  skip=false
  for pat in "${PRESERVE_PATTERNS[@]}"; do
    case "$rel_path" in
      $pat|*/$pat|*__pycache__*|*.pyc) skip=true; break ;;
    esac
  done
  # 跳过 libsliceupload 目录（由独立 CDN 管理）
  case "$rel_path" in
    scripts/feed/libsliceupload/*) skip=true ;;
  esac
  $skip && continue

  cdn_file="$CDN_ROOT/$rel_path"
  if [[ ! -f "$cdn_file" ]]; then
    LOCAL_ONLY_FILES+=("$rel_path")
  fi
done < <(find "$SKILL_ROOT" -type f -print0 | sort -z)

echo ""
echo "📊 差异统计:"
echo "   新增文件: ${#NEW_FILES[@]}"
echo "   变更文件: ${#CHANGED_FILES[@]}"
echo "   未变更:   ${#UNCHANGED_FILES[@]}"
echo "   本地独有: ${#LOCAL_ONLY_FILES[@]}"

if [[ ${#NEW_FILES[@]} -gt 0 ]]; then
  echo ""
  echo "   ➕ 新增:"
  for f in "${NEW_FILES[@]}"; do
    echo "      $f"
  done
fi

if [[ ${#CHANGED_FILES[@]} -gt 0 ]]; then
  echo ""
  echo "   ✏️  变更:"
  for f in "${CHANGED_FILES[@]}"; do
    echo "      $f"
  done
fi

if [[ ${#LOCAL_ONLY_FILES[@]} -gt 0 ]]; then
  echo ""
  echo "   ⚠️  本地独有 (CDN 包中不存在，不会被删除):"
  for f in "${LOCAL_ONLY_FILES[@]}"; do
    echo "      $f"
  done
fi

# ── 检查 libsliceupload 依赖差异 ──
LIBSLICE_DIR="$SKILL_ROOT/scripts/feed/libsliceupload"
LIBSLICE_ZIP="$TMP_DIR/libsliceupload.zip"
LIBSLICE_EXTRACT="$TMP_DIR/libslice_extracted"

echo ""
echo "📦 正在检查 libsliceupload 依赖更新..."

libslice_changed=()
libslice_new=()
libslice_unchanged=()
LIBSLICE_OK=false

LIBSLICE_HTTP=$(curl -sL -w "%{http_code}" -o "$LIBSLICE_ZIP" "$LIBSLICE_CDN_URL")
if [[ "$LIBSLICE_HTTP" != "200" ]]; then
  echo "⚠️  libsliceupload 下载失败 (HTTP $LIBSLICE_HTTP)，跳过依赖检查"
else
  LIBSLICE_OK=true
  mkdir -p "$LIBSLICE_EXTRACT"
  unzip -q -o "$LIBSLICE_ZIP" -d "$LIBSLICE_EXTRACT"

  for cdn_bin in "$LIBSLICE_EXTRACT"/*; do
    [[ -f "$cdn_bin" ]] || continue
    bin_name="$(basename "$cdn_bin")"
    local_bin="$LIBSLICE_DIR/$bin_name"

    if [[ ! -f "$local_bin" ]]; then
      libslice_new+=("$bin_name")
    elif ! cmp -s "$local_bin" "$cdn_bin"; then
      libslice_changed+=("$bin_name")
    else
      libslice_unchanged+=("$bin_name")
    fi
  done

  if [[ ${#libslice_new[@]} -eq 0 && ${#libslice_changed[@]} -eq 0 ]]; then
    echo "✅ libsliceupload 已是最新版本"
  else
    echo "📊 libsliceupload 差异:"
    echo "   ➕ 新增: ${#libslice_new[@]}  ✏️ 变更: ${#libslice_changed[@]}  未变更: ${#libslice_unchanged[@]}"
    for f in "${libslice_new[@]}"; do echo "      ➕ $f"; done
    for f in "${libslice_changed[@]}"; do echo "      ✏️  $f"; done
  fi
fi

# ── 判断是否有任何更新 ──
SKILL_HAS_CHANGES=false
LIBSLICE_HAS_CHANGES=false
if [[ ${#NEW_FILES[@]} -gt 0 || ${#CHANGED_FILES[@]} -gt 0 ]]; then
  SKILL_HAS_CHANGES=true
fi
if [[ ${#libslice_new[@]} -gt 0 || ${#libslice_changed[@]} -gt 0 ]]; then
  LIBSLICE_HAS_CHANGES=true
fi

if ! $SKILL_HAS_CHANGES && ! $LIBSLICE_HAS_CHANGES; then
  echo ""
  echo "✅ 当前已是最新版本，无需更新。"
  exit 0
fi

# ── Dry-run 模式 ──
if $DRY_RUN; then
  echo ""
  echo "🏃 Dry-run 模式，不执行实际更新。"
  exit 0
fi

# ── 确认更新 ──
if ! $FORCE; then
  echo ""
  printf "❓ 是否确认更新？(y/N) "
  read -r answer
  if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "已取消。"
    exit 0
  fi
fi

# ── 备份 ──
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$SKILL_ROOT/.bak-$TIMESTAMP"
echo ""
echo "💾 正在备份变更文件到 $BACKUP_DIR ..."

mkdir -p "$BACKUP_DIR"
backup_count=0

# 备份将要被覆盖的 skill 文件
for rel_path in "${CHANGED_FILES[@]}"; do
  local_file="$SKILL_ROOT/$rel_path"
  backup_file="$BACKUP_DIR/$rel_path"
  mkdir -p "$(dirname "$backup_file")"
  cp "$local_file" "$backup_file"
  ((backup_count++))
done

# 备份将要被覆盖的 libsliceupload 二进制
if [[ ${#libslice_changed[@]} -gt 0 ]]; then
  mkdir -p "$BACKUP_DIR/scripts/feed/libsliceupload"
  for f in "${libslice_changed[@]}"; do
    cp "$LIBSLICE_DIR/$f" "$BACKUP_DIR/scripts/feed/libsliceupload/$f"
    ((backup_count++))
  done
fi

echo "✅ 已备份 $backup_count 个文件"

# ── 执行 skill 文件更新 ──
update_count=0

if $SKILL_HAS_CHANGES; then
  echo ""
  echo "🚀 正在更新 skill 文件..."

  for rel_path in "${NEW_FILES[@]}" "${CHANGED_FILES[@]}"; do
    cdn_file="$CDN_ROOT/$rel_path"
    local_file="$SKILL_ROOT/$rel_path"

    # 跳过保留的文件
    skip=false
    for pat in "${PRESERVE_PATTERNS[@]}"; do
      case "$rel_path" in
        $pat|*/$pat) skip=true; break ;;
      esac
    done
    if $skip; then
      echo "   ⏭️  跳过 (保留本地): $rel_path"
      continue
    fi

    mkdir -p "$(dirname "$local_file")"
    cp "$cdn_file" "$local_file"
    ((update_count++))
    echo "   ✅ $rel_path"
  done

  # 恢复执行权限
  find "$SKILL_ROOT/scripts" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
fi

# ── 执行 libsliceupload 更新 ──
if $LIBSLICE_HAS_CHANGES && $LIBSLICE_OK; then
  echo ""
  echo "🚀 正在更新 libsliceupload 依赖..."

  mkdir -p "$LIBSLICE_DIR"
  for f in "${libslice_new[@]}" "${libslice_changed[@]}"; do
    cp "$LIBSLICE_EXTRACT/$f" "$LIBSLICE_DIR/$f"
    chmod +x "$LIBSLICE_DIR/$f"
    ((update_count++))
    echo "   ✅ $f"
  done
fi

echo ""
echo "🎉 更新完成！共更新 $update_count 个文件。"
echo ""
echo "📋 更新摘要:"
echo "   版本: $LOCAL_VERSION → $CDN_VERSION"
echo "   备份: $BACKUP_DIR"
echo ""
echo "💡 提示:"
echo "   - 如需回滚，备份文件在: $BACKUP_DIR"
echo "   - 更新后建议执行 token 校验: bash scripts/token/verify.sh"
echo "   - 如需清理备份: rm -rf $BACKUP_DIR"
