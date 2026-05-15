#!/bin/bash
# verify_references.sh — 从 Markdown 中提取源码引用并验证存在性
# 用法: bash scripts/verify_references.sh [章节文件.md]

set -euo pipefail

BOOK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_ROOT="$(cd "$BOOK_ROOT/../../.." && pwd)/src"

TOTAL=0; OK=0; FAIL=0

# 提取 src/...ts 或 src/...tsx 路径
extract_paths() {
  grep -oP 'src/[A-Za-z0-9_/.-]+\.(ts|tsx)' "$1" 2>/dev/null | sort -u
}

# 提取反引号符号名 InterfaceName.methodName
extract_symbols() {
  grep -oP '`([A-Z][A-Za-z0-9]+)\.([a-z][A-Za-z0-9]+)`' "$1" 2>/dev/null | sort -u
}

verify_file() {
  local md="$1"
  echo "=== $md ==="

  local count=0 found=0 missed=0
  while IFS= read -r path; do
    count=$((count + 1))
    if [ -f "$SRC_ROOT/$path" ]; then
      found=$((found + 1))
    else
      missed=$((missed + 1))
      echo "  FAIL: $path"
    fi
  done < <(extract_paths "$md")

  TOTAL=$((TOTAL + count))
  OK=$((OK + found))
  FAIL=$((FAIL + missed))
  echo "  检查: $count 引用, $found 通过, $missed 失败"
}

# 主逻辑
if [ $# -gt 0 ]; then
  for f in "$@"; do verify_file "$f"; done
else
  for f in "$BOOK_ROOT"/volume-*/*.md "$BOOK_ROOT"/appendix/*.md; do
    [ -f "$f" ] && verify_file "$f"
  done
fi

echo ""
echo "=============================="
echo "总计引用: $TOTAL"
echo "通过:     $OK"
echo "失败:     $FAIL"
[ "$FAIL" -eq 0 ] && echo "✓ 全部通过" || echo "✗ 有失败项"
[ "$FAIL" -eq 0 ]
