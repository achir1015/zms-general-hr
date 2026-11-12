#!/bin/bash
# 建置 iPhone／iPad 版 .ipa（Ad Hoc：已註冊的裝置可安裝；GitHub Pages 安裝頁用）
# 必須在 Mac 的「終端機」視窗執行（簽章要用已解鎖的鑰匙圈）；遠端請用 tools/ios_in_terminal.sh。
# 環境變數：SKIP_FLET=1 只重新封存與簽章（沿用 build/flutter）
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
TEAM=7BN6XJ59KP
VER=$(.venv/bin/python -c "import hr; print(hr.APP_VERSION)")
IFS=. read -r A B C <<< "$VER"
NUM=$((A * 10000 + B * 100 + C))
echo "== 版本 ${VER}（build ${NUM}）"

if [ -z "${SKIP_FLET:-}" ]; then
  rm -rf build dist-ios
  # flet 產生 Flutter 專案並編譯；最後的簽章／匯出步驟若失敗，下面改用 xcodebuild 完成
  .venv/bin/flet build ipa --build-version "$VER" --build-number "$NUM" \
    --deep-linking-scheme zmshr --deep-linking-host connect \
    --ios-team-id "$TEAM" --ios-export-method release-testing -o dist-ios --yes || echo "== flet build ipa 未完成，改用 xcodebuild"
fi

IOS=build/flutter/ios
[ -d "$IOS" ] || { echo "找不到 $IOS"; exit 1; }
if ls dist-ios/*.ipa >/dev/null 2>&1; then
  echo "== flet 已產生 .ipa"
else
  if ! command -v pod >/dev/null; then rm -f "$IOS/Podfile" "$IOS/Podfile.lock"; fi   # 沒有 CocoaPods：改用 Swift Package Manager
  ARCH=build/ios-archive/Runner.xcarchive
  rm -rf build/ios-archive
  # 沒有 CocoaPods 時直接用 Xcode 專案（外掛都是 Swift Package）；有 CocoaPods 才用 workspace
  if command -v pod >/dev/null; then SRC=(-workspace "$IOS/Runner.xcworkspace"); else SRC=(-project "$IOS/Runner.xcodeproj"); fi
  xcodebuild "${SRC[@]}" -scheme Runner -configuration Release -destination 'generic/platform=iOS' \
    -archivePath "$ARCH" archive DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Automatic -allowProvisioningUpdates \
    | grep -E "error:|warning: .*sign|ARCHIVE|Signing Identity|Provisioning Profile" | tail -25
  [ -d "$ARCH" ] || { echo "封存失敗"; exit 1; }
  cat > build/export.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>release-testing</string>
  <key>teamID</key><string>$TEAM</string>
  <key>signingStyle</key><string>automatic</string>
  <key>compileBitcode</key><false/>
</dict></plist>
EOF
  mkdir -p dist-ios
  xcodebuild -exportArchive -archivePath "$ARCH" -exportPath dist-ios -exportOptionsPlist build/export.plist \
    -allowProvisioningUpdates | tail -10
fi
IPA=$(ls dist-ios/*.ipa | head -1)
OUT="dist-ios/ZMSGeneralHR-$VER-ios.ipa"
[ "$IPA" = "$OUT" ] || mv "$IPA" "$OUT"
shasum -a 256 "$OUT"; du -h "$OUT"
echo "BUILD_DONE"
