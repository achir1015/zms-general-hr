#!/bin/bash
# 建置 macOS 版：dist-mac/資料助秘之一般公司人事薪資差勤.app 與 dist-mac/ZMSGeneralHR-<版本>-mac.dmg
# 用法（在 Mac 上）：bash tools/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
PY=.venv/bin/python
VER=$($PY -c "import hr; print(hr.APP_VERSION)")
NAME="資料助秘之一般公司人事薪資差勤"
BUNDLE_ID="com.achir.zmsgeneralhr"
echo "== 版本 $VER"

bash tools/prepare_mariadb_mac.sh

rm -rf build-mac dist-mac build
mkdir -p build-mac dist-mac

# 圖示 PNG → icns
SET=build-mac/icon.iconset; mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s assets/icon.png --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) assets/icon.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o build-mac/icon.icns

echo "== flet pack"
.venv/bin/flet pack main.py -y -n ZMSGeneralHR -i build-mac/icon.icns --distpath dist-mac \
  --add-data assets:assets --add-data hr/schema.sql:hr \
  --hidden-import edge_tts --hidden-import pymysql --hidden-import qrcode --hidden-import qrcode.image.pil \
  --product-name "$NAME" --product-version "$VER" --bundle-id "$BUNDLE_ID" --copyright "© 2026 吳玉柱"

APP=dist-mac/ZMSGeneralHR.app
[ -d "$APP" ] || { echo "找不到 $APP"; ls dist-mac; exit 1; }

echo "== 內附 MariaDB"
cp -R packaging/mariadb-mac "$APP/Contents/Resources/mariadb"

PL="$APP/Contents/Info.plist"
pb() { /usr/libexec/PlistBuddy -c "$1" "$PL" 2>/dev/null || true; }
pb "Delete :CFBundleDisplayName"; pb "Add :CFBundleDisplayName string $NAME"
pb "Set :CFBundleName $NAME"
pb "Set :CFBundleShortVersionString $VER"; pb "Set :CFBundleVersion $VER"
pb "Delete :LSMinimumSystemVersion"; pb "Add :LSMinimumSystemVersion string 11.0"
pb "Delete :LSApplicationCategoryType"; pb "Add :LSApplicationCategoryType string public.app-category.business"
pb "Delete :NSHumanReadableCopyright"; pb "Add :NSHumanReadableCopyright string 系統開發：吳玉柱 先生 與 Claude AI Opus 5.5"
pb "Delete :NSLocalNetworkUsageDescription"
pb "Add :NSLocalNetworkUsageDescription string 連到區域網路上的會計系統（拋轉傳票）或 MariaDB 進銷存資料庫"
pb "Delete :NSAppleEventsUsageDescription"
pb "Add :NSAppleEventsUsageDescription string 在桌面建立本系統的替身"

FINAL="dist-mac/$NAME.app"
rm -rf "$FINAL"; mv "$APP" "$FINAL"
# 專用簽章鑰匙圈（~/Developer/zms-signing，密碼檔不進 git）：先解鎖，SSH 下也能簽
SIGN_KC="$HOME/Library/Keychains/zms-signing.keychain-db"
if [ -f "$SIGN_KC" ] && [ -f "$HOME/Developer/zms-signing/kc.pass" ]; then
  security unlock-keychain -p "$(cat "$HOME/Developer/zms-signing/kc.pass")" "$SIGN_KC"
fi
# 簽章：鑰匙圈有「Developer ID Application」憑證就正式簽章＋強化執行階段（可公證）；沒有就 ad-hoc
IDENT=$(security find-identity -v -p codesigning | grep -o '"Developer ID Application: [^"]*"' | head -1 | tr -d '"' || true)
if [ -n "$IDENT" ]; then
  echo "== 簽章（${IDENT}）"
  ENT=packaging/mac-entitlements.plist
  # 由內而外：先簽 MariaDB 的函式庫與執行檔，再簽主程式與整個 App
  find "$FINAL/Contents/Resources" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 |
    xargs -0 -I{} codesign --force --timestamp --options runtime -s "$IDENT" "{}"
  find "$FINAL/Contents/Resources" -type f -perm +111 ! -name "*.dylib" ! -name "*.so" -print0 |
    while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q Mach-O; then codesign --force --timestamp --options runtime -s "$IDENT" "$f"; fi
    done
  codesign --force --timestamp --options runtime --entitlements "$ENT" -s "$IDENT" "$FINAL/Contents/MacOS/ZMSGeneralHR"
  codesign --force --timestamp --options runtime --entitlements "$ENT" -s "$IDENT" "$FINAL"
else
  echo "== 簽章（ad-hoc；找不到 Developer ID 憑證）"
  codesign --force --deep -s - "$FINAL"
fi
codesign --verify --deep --strict "$FINAL" && echo "簽章 OK"

# 公證：先用 xcrun notarytool store-credentials 建好鑰匙圈設定檔（預設名稱 zms-notary）
NOTARY="${NOTARY_PROFILE:-zms-notary}"
notarize() {   # $1＝要送的檔案（.zip 或 .dmg）
  xcrun notarytool submit "$1" --keychain-profile "$NOTARY" --wait --timeout 60m | tee build-mac/notary.txt
  grep -q "status: Accepted" build-mac/notary.txt || {
    ID=$(grep -m1 "  id:" build-mac/notary.txt | awk '{print $2}')
    [ -n "$ID" ] && xcrun notarytool log "$ID" --keychain-profile "$NOTARY" || true
    echo "公證失敗"; exit 1; }
}
CAN_NOTARIZE=""
if [ -n "$IDENT" ] && xcrun notarytool history --keychain-profile "$NOTARY" >/dev/null 2>&1; then CAN_NOTARIZE=1; fi
if [ -n "$CAN_NOTARIZE" ]; then
  echo "== 公證 App"
  ditto -c -k --keepParent "$FINAL" build-mac/app.zip
  notarize build-mac/app.zip
  xcrun stapler staple "$FINAL"
elif [ -n "$IDENT" ]; then
  echo "== 略過公證（沒有 notarytool 設定檔 ${NOTARY}）"
fi

echo "== DMG"
STAGE=build-mac/dmg; rm -rf "$STAGE"; mkdir -p "$STAGE"
ditto "$FINAL" "$STAGE/$NAME.app"
ln -s /Applications "$STAGE/應用程式"
SIZE_MB=$(( $(du -sm "$STAGE" | cut -f1) + 60 ))
DMG="dist-mac/ZMSGeneralHR-$VER-mac.dmg"
rm -f "$DMG"
for i in 1 2 3; do
  hdiutil create -volname "$NAME $VER" -srcfolder "$STAGE" -ov -format UDZO -size ${SIZE_MB}m "$DMG" && break
  echo "hdiutil 重試 $i"; sleep 5
done
if [ -n "$IDENT" ]; then codesign --force --timestamp -s "$IDENT" "$DMG"; fi
if [ -n "$CAN_NOTARIZE" ]; then
  echo "== 公證 DMG"
  notarize "$DMG"
  xcrun stapler staple "$DMG"
  spctl -a -vv -t install "$DMG" 2>&1 | head -3
  spctl -a -vv "$FINAL" 2>&1 | head -3
fi
shasum -a 256 "$DMG"
du -h "$DMG"
echo "BUILD_DONE"
