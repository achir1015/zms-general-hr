#!/bin/bash
# 從 SSH 觸發：在 Mac 的「終端機」視窗執行 build_ios.sh（簽章需要已登入使用者的鑰匙圈）。
# 結果寫在 build-ios.log，結束時最後一行為 EXIT=<代碼>。
cd "$(dirname "$0")/.."
DIR="$(pwd)"
rm -f build-ios.log
osascript <<EOF
tell application "Terminal"
  do script "cd '$DIR' && ${SKIP_FLET:+SKIP_FLET=1 }caffeinate -i bash tools/build_ios.sh > build-ios.log 2>&1; echo EXIT=\$? >> build-ios.log; exit"
end tell
EOF
echo "已在終端機啟動 iOS 建置"
