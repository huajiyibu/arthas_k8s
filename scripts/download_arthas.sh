#!/bin/bash
# 下载并解压 Arthas 工具到 <项目根>/arthas/arthas/arthas
# 用法：bash scripts/download_arthas.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"     # scripts 的上一级 = 项目根
DEST="$ROOT/arthas/arthas"                    # 工具父目录（config.py 默认 ARTHAS_PARENT_DIR）
URL="https://github.com/alibaba/arthas/releases/latest/download/arthas-bin.zip"
TMP="$(mktemp -d)"

echo "下载 Arthas: $URL"
curl -fL -o "$TMP/arthas-bin.zip" "$URL"

echo "解压到 $DEST"
mkdir -p "$DEST"
unzip -o "$TMP/arthas-bin.zip" -d "$DEST" >/dev/null

# 统一整理成 $DEST/arthas
BOOT="$(find "$DEST" -name arthas-boot.jar | head -n1)"
if [ -n "$BOOT" ]; then
  BOOT_DIR="$(dirname "$BOOT")"
  if [ "$BOOT_DIR" != "$DEST/arthas" ]; then
    rm -rf "$DEST/arthas"
    mv "$BOOT_DIR" "$DEST/arthas"
  fi
fi

rm -rf "$TMP"

if [ -f "$DEST/arthas/arthas-boot.jar" ]; then
  echo "完成 ✅ Arthas 工具位于: $DEST/arthas"
else
  echo "⚠️ 未找到 arthas-boot.jar，请检查解压结果：$DEST"
fi
