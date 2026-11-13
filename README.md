# 資料助秘之一般公司人事薪資差勤
<img width="1426" height="891" alt="image" src="https://github.com/user-attachments/assets/d2118434-57c7-4b3b-a313-7cb507da9d6e" />
<img width="1429" height="891" alt="image" src="https://github.com/user-attachments/assets/d9b91d43-7b59-4ccb-9a77-7da23f65a210" />

單一公司使用的人事、排班、GPS 打卡、請假加班、薪資、勞健保退休金系統，並可把薪資與保費拋轉成
「[資料助秘之一般公司會計](https://github.com/achir1015/zms-accounting)」的傳票。
本版本給一般公司（非護理、醫療院所）使用；醫院護理排班的版本日後另外開發。

系統開發：吳玉柱 先生 與 Claude AI Opus 5.5

## 下載安裝

到 [Releases](https://github.com/achir1015/zms-general-hr/releases/latest) 下載：

| 平台 | 檔案 |
|---|---|
| Windows 10／11（64 位元） | `ZMSGeneralHR-Setup-版本.exe` |
| macOS 11 以上（MacBook Pro 等） | `ZMSGeneralHR-版本-mac.dmg` |
| Android 7.0 以上手機 | `ZMSGeneralHR-版本-android.apk` |
| iPhone（App 規劃中） | 用 Safari 開公司公告的「GPS 打卡網址」，可「加入主畫面」 |

### Windows

- 執行安裝檔，可勾選「建立桌面捷徑」；開始功能表另有「使用說明與資料資料夾」。
- 資料存放在 `%LOCALAPPDATA%\ZMSGeneralHR`，更新或解除安裝都不會刪除。

### macOS

- 打開 DMG，把「資料助秘之一般公司人事薪資差勤」拖進「應用程式」資料夾，之後可以拖到 Dock 常駐。
- 已用 Apple Developer ID 簽章並通過 Apple 公證（Notarized），可以直接開啟。
- 資料存放在 `~/Library/Application Support/ZMSGeneralHR`，更新或刪除 App 都不會刪除。

### Android 手機

- 用手機下載 APK 安裝（第一次會詢問是否允許安裝未知來源的 App，選「允許」；Play Protect 提示時選「仍要安裝」）。
- 手機 App 透過公司電腦連線：人資在電腦版「系統管理 → 手機打卡與連線」打開服務，手機相機掃畫面上的 QR Code 就會自動連上；
  外出時用「外出連線」產生的 https 網址。
- **員工帳號**一登入就是「我的打卡與假勤」：按上班／下班打卡會取得手機 GPS 定位（第一次請允許「使用位置資訊」），
  由公司電腦判斷是否在打卡範圍內；也能看自己的月班表、特休與補休餘額、請假加班申請、薪資單。
- **人資與主管帳號**的功能和電腦版相同；備份、版本更新、會計拋轉、檔案匯入匯出請在電腦版操作。
- 有新版本時，App 選單最上方會出現提示，點一下下載新的 APK 覆蓋安裝，資料不受影響。

電腦版（Windows、macOS）都內附 MariaDB 資料庫，開啟程式自動啟動、關閉程式自動停止，不必另外安裝；
程式開啟時自動檢查新版本，按「下載並安裝」即可更新。

平台順序：Windows 11 → MacBook Pro → Android → iPhone → iPad（之後的版本陸續推出）。
iPhone 目前請用瀏覽器開「GPS 打卡網頁」打卡與請假；iPhone／iPad App 為下一階段。

## 主要功能

| 類別 | 功能 |
|---|---|
| 人事 | 員工資料（身分證檢查碼、年資起算日、到離職、調薪紀錄）、部門（費用別）、員工名冊、人力統計、CSV 名冊匯入 |
| 排班 | 月班表格（選班別當畫筆點格子）、循環排班、國定假日自動排休；**與月班表管理系統（[rcw-month](https://github.com/achir1015/rcw-month)）XML 互通**、Excel（CSV）匯入匯出；**匯出到小柯班表助手（[xiaoke-shift](https://github.com/achir1015/xiaoke-shift)）**，員工在手機「⋯ → 還原班表」即可看班與設定上班鬧鐘 |
| 打卡 | 手機 GPS 打卡網頁（參考 [gps-arrival-test](https://github.com/achir1015/gps-arrival-test)：Haversine 距離、伺服器端判定、超出範圍列為待確認、OpenStreetMap 地圖）、電腦打卡、補登打卡、地址轉座標（ArcGIS／OSM） |
| 出勤 | 出勤日報與月報：遲到、早退、曠職、缺打卡、請假、停班自動判斷 |
| 請假加班 | 依勞基法、性平法、勞工請假規則內建 18 種假別（特休、補休、事假、家庭照顧、病假、生理、婚、喪、公傷、產假、產檢、陪產、育嬰留停、天災、防疫…）；每年／每月上限檢查；加班費依第 24、39 條（平日、休息日、國定假日）；每月 46 小時上限；加班換補休 |
| 特休補休 | 依年資自動產生特休（週年制或曆年制比例）、先到期先用、年度結算折發工資或遞延、補休依原費率折發、期初餘額匯入、未休特休估列 |
| 公傷 | 職災案件、公傷病假（原領工資補償以免稅項目發給、不影響全勤）、醫療與補償費用、保險給付抵充、傷病給付試算 |
| 天災疫情 | 颱風、地震、水災、疫情停班登錄：不算曠職、不扣全勤；可設定是否給薪與停班日出勤加給 |
| 薪資 | 薪資科目（應發／應扣、經常性給與、補充保費獎金、會計科目）、固定津貼、每月變動輸入、月薪計算（在職日數、請假扣薪、遲到、曠職、全勤比例、加班費、免稅額）、確認、銀行轉帳檔、薪資單列印、關帳 |
| 獎金年終 | 津貼獎金規則（月數或固定金額、在職比例、到職滿幾個月、部門）、獎金批次、非固定薪資 5% 扣繳 |
| 勞健保勞退 | 115 年官方分級表（勞保 11 級、職災 21 級、健保 58 級、勞退 62 級、部分工時低級距）、勞保 12.5%（無就保者自動 12.5% 普通事故）、健保 5.17%＋眷屬、平均眷口數 0.56、職災費率、墊償基金、勞退雇主 6%／自提 0～6%、二代健保補充保費（員工獎金與投保單位）；法令參數依生效日保存歷年 |
| 會計拋轉 | 薪資、公司負擔保費、發放、職災費用、特休估列 → zms-gl 拋轉檔或直接傳送會計系統；依部門費用別記薪資支出 |
| 系統 | 使用者與權限（12 項功能 × 無／查詢／維護，「薪資個資」權限控管）、員工帳號、操作紀錄、備份還原、版本更新、使用說明＋語音、導入說明前言（祥和貿易範例） |

## 開發

```bash
py -3.12 -m venv .venv
.venv\Scripts\pip install flet==1.1.2 flet-audio==1.1.2 flet-desktop==1.1.2 pymysql pytest edge-tts qrcode pillow pyinstaller
.venv\Scripts\python main.py                 # 桌面版
.venv\Scripts\python run_web.py              # 網頁預覽 http://127.0.0.1:8580（開發自動登入 admin）
.venv\Scripts\python tools\demo_data.py      # 建立祥和貿易範例資料（會清空開發資料庫）
.venv\Scripts\python -m pytest -q tests      # 測試（測試資料庫埠 3388）
.venv\Scripts\python tools\build_windows.py  # 建置 dist-installer\ZMSGeneralHR-Setup-<版本>.exe
```

macOS（在 Mac 上）：`bash tools/build_macos.sh`（需要 Developer ID 憑證與 notarytool 設定檔 `zms-notary`；
從 SSH 觸發請用 `bash tools/mac_in_terminal.sh`，在終端機視窗建置以使用鑰匙圈），產生 `dist-mac/ZMSGeneralHR-<版本>-mac.dmg`。

Android（在 Mac 上）：`bash tools/build_android.sh`，產生 `dist-android/ZMSGeneralHR-<版本>-android.apk`
（簽章金鑰 `android/zmsgeneralhr.jks` 不進 git，請另外備份）。開發時可用 `python main.py --server` 加 `python run_web_mobile.py`
（http://127.0.0.1:8581）預覽手機版面。

需要 MariaDB（開發用 `C:\mariadb`，安裝檔會內附）。資料庫埠：開發 3378、手機連線服務 8785。

| 目錄 | 內容 |
|---|---|
| `hr/seed.py` | 權限、角色、薪資科目、假別、班別、法令參數、分級表、115 年國定假日、會計科目對照 |
| `hr/laws.py` | 投保分級、保費、加班費、特休日數、所得稅、補充保費（純計算，有測試） |
| `hr/people.py` `attendance.py` `leave.py` `occ.py` `payroll.py` `gl.py` `reports.py` | 員工、排班打卡、請假加班額度、職災、薪資、會計拋轉、報表 |
| `hr/api.py` `hr/punchpage.py` | 手機連線服務與 GPS 打卡網頁（`/punch`） |
| `hr/adoption.py` `hr/example.py` | 導入說明前言與範例公司（`tests/test_adoption.py` 逐格核對數字） |

## 法令依據（115 年 1 月 1 日起）

勞動部勞工保險局：勞工保險投保薪資分級表、勞工職業災害保險投保薪資分級表、勞工退休金月提繳分級表；
衛生福利部中央健康保險署：全民健康保險投保金額分級表、費率 5.17%、平均眷口數 0.56、補充保費 2.11%；
勞動部：基本工資 29,500 元、時薪 196 元；財政部：115 年度免稅額、標準扣除額、薪資特別扣除額、非固定薪資起扣額 90,501。
法令每年調整時，在「法令參數與分級表」新增新的生效日即可。

所得稅「依扣繳稅額表」為依綜所稅公式的概算，正式扣繳以國稅局公告的薪資所得扣繳稅額表為準（可改固定扣繳率或每月手動指定）。

## 授權

© 2026 吳玉柱
