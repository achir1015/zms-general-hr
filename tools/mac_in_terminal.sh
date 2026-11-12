#!/bin/bash
# 從 SSH 觸發：在 Mac 的「終端機」視窗執行 build_macos.sh（簽章需要已登入使用者的鑰匙圈）。
# 結果寫在 build-mac.log，結束時最後一行為 EXIT=<代碼>。
cd "$(dirname "$0")/.."
DIR="$(pwd)"
rm -f build-mac.log
osascript <<EOF
tell application "Terminal"
  do script "cd '$DIR' && caffeinate -i bash tools/build_macos.sh > build-mac.log 2>&1; echo EXIT=\$? >> build-mac.log; exit"
end tell
EOF
echo "已在終端機啟動 macOS 建置"
