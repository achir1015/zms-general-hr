#!/bin/bash
# 建置 Android APK（在 Mac 上執行）：dist-android/ZMSGeneralHR-<版本>-android.apk
# 簽章金鑰 android/zmsgeneralhr.jks（第一次自動建立；不進 git，請妥善備份——遺失後舊版手機無法直接更新）
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/usr/local/bin:$PATH
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export ANDROID_HOME="$HOME/Android/sdk" ANDROID_SDK_ROOT="$HOME/Android/sdk"
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
VER=$(.venv/bin/python -c "import hr; print(hr.APP_VERSION)")
IFS=. read -r A B C <<< "$VER"
NUM=$((A * 10000 + B * 100 + C))
echo "== 版本 ${VER}（build ${NUM}）"

mkdir -p android
if [ ! -f android/zmsgeneralhr.jks ]; then
  PW=$(openssl rand -hex 16)
  keytool -genkeypair -v -keystore android/zmsgeneralhr.jks -alias zmsgeneralhr -keyalg RSA -keysize 2048 \
    -validity 10000 -storepass "$PW" -keypass "$PW" -dname "CN=吳玉柱, O=資料助秘, C=TW" >/dev/null
  printf 'storePassword=%s\nkeyAlias=zmsgeneralhr\n' "$PW" > android/signing.properties
  echo "已建立簽章金鑰 android/zmsgeneralhr.jks"
fi
PW=$(grep '^storePassword=' android/signing.properties | cut -d= -f2)

rm -rf build dist-android
.venv/bin/flet build apk --arch arm64-v8a --build-version "$VER" --build-number "$NUM" \
  --deep-linking-scheme zmshr --deep-linking-host connect \
  --android-signing-key-store "$PWD/android/zmsgeneralhr.jks" --android-signing-key-alias zmsgeneralhr \
  --android-signing-key-store-password "$PW" --android-signing-key-password "$PW" \
  -o dist-android --yes

APK=$(ls dist-android/*.apk | head -1)
OUT="dist-android/ZMSGeneralHR-$VER-android.apk"
[ "$APK" = "$OUT" ] || mv "$APK" "$OUT"
shasum -a 256 "$OUT"; du -h "$OUT"
echo "BUILD_DONE"
