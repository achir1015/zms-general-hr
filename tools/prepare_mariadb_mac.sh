#!/bin/bash
# 準備 macOS 版內附的 MariaDB 10.11.18（與 Windows 版同版本）：
# Homebrew 已不再為 Intel Mac 提供新版預編譯包，改從 ghcr.io 下載 10.11.18 的 sonoma（x86_64）bottle，
# 只取需要的程式，把 OpenSSL、PCRE2 動態庫一起放進 lib/，改成相對路徑後重新 ad-hoc 簽章。
# Apple 晶片 Mac 透過 Rosetta 2 執行（整個 App 是 x86_64）。
#
# 用法：bash tools/prepare_mariadb_mac.sh   → packaging/mariadb-mac/{bin,lib,share/mysql}
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="packaging/mariadb-mac"
VER="10.11.18"
DIGEST="2569a78044d5f5cc1abc6a0020bc27a9753364ea9fb162b2196ad87600eb2c05"   # 10.11.18.sonoma（x86_64）
WORK="$(mktemp -d)"
BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /usr/local)"

if [ -x "$OUT/bin/mariadbd" ]; then echo "已存在：$OUT"; exit 0; fi

echo "下載 MariaDB $VER bottle…"
curl -sSL -H "Authorization: Bearer QQ==" -o "$WORK/mariadb.tar.gz" \
  "https://ghcr.io/v2/homebrew/core/mariadb/10.11/blobs/sha256:$DIGEST"
echo "$DIGEST  $WORK/mariadb.tar.gz" | shasum -a 256 -c -
tar xzf "$WORK/mariadb.tar.gz" -C "$WORK"
SRC="$WORK/mariadb@10.11/$VER"

rm -rf "$OUT"; mkdir -p "$OUT/bin" "$OUT/lib" "$OUT/share"
for b in mariadbd mariadb-install-db my_print_defaults resolveip mariadb mariadb-admin mariadb-dump; do
  cp "$SRC/bin/$b" "$OUT/bin/"
done
cp -R "$SRC/share/mysql" "$OUT/share/mysql"
# 只留英文與中文錯誤訊息
( cd "$OUT/share/mysql" && for d in */; do case "$d" in english/|chinese/|charsets/) ;; *) rm -rf "$d";; esac; done )
cp "$SRC/COPYING" "$SRC/README.md" "$OUT/" 2>/dev/null || true

# 動態庫
for lib in "$BREW_PREFIX/opt/openssl@3/lib/libssl.3.dylib" "$BREW_PREFIX/opt/openssl@3/lib/libcrypto.3.dylib" \
           "$BREW_PREFIX/opt/pcre2/lib/libpcre2-8.0.dylib"; do
  cp -L "$lib" "$OUT/lib/"; chmod u+w "$OUT/lib/$(basename "$lib")"
done
for f in "$OUT"/lib/*.dylib; do
  install_name_tool -id "@loader_path/$(basename "$f")" "$f" 2>/dev/null
  for dep in $(otool -L "$f" | tail -n +2 | awk '{print $1}' | grep -E "openssl|pcre2" || true); do
    install_name_tool -change "$dep" "@loader_path/$(basename "$dep")" "$f" 2>/dev/null
  done
done
for f in "$OUT"/bin/*; do
  file "$f" | grep -q "Mach-O" || continue
  chmod u+w "$f"
  for dep in $(otool -L "$f" | tail -n +2 | awk '{print $1}' | grep -E "HOMEBREW|openssl|pcre2" || true); do
    install_name_tool -change "$dep" "@executable_path/../lib/$(basename "$dep")" "$f" 2>/dev/null
  done
done
# install-db 的預設 basedir 是 Homebrew 佔位字串，程式啟動時一律傳 --basedir
for f in "$OUT"/lib/*.dylib "$OUT"/bin/*; do
  file "$f" | grep -q "Mach-O" && codesign -f -s - "$f" 2>/dev/null
done
rm -rf "$WORK"
echo "完成：$OUT（$(du -sh "$OUT" | cut -f1)）"
otool -L "$OUT/bin/mariadbd" | tail -n +2 | grep -v "/usr/lib\|/System" || true
