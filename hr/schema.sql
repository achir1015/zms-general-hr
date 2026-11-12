-- 資料助秘之一般公司人事薪資差勤：資料表（MariaDB，utf8mb4）
-- 每次開啟程式都會執行（IF NOT EXISTS），新增欄位請寫在 database.py 的 UPGRADES。
-- 金額一律到元（整數）；時數到 0.01 小時。

CREATE TABLE IF NOT EXISTS meta (
  k VARCHAR(40) PRIMARY KEY,
  v VARCHAR(200) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS company (
  id TINYINT PRIMARY KEY,
  name VARCHAR(80) NOT NULL DEFAULT '',
  short_name VARCHAR(30) NOT NULL DEFAULT '',
  tax_id VARCHAR(10) NOT NULL DEFAULT '',
  owner VARCHAR(30) NOT NULL DEFAULT '',
  phone VARCHAR(30) NOT NULL DEFAULT '',
  email VARCHAR(80) NOT NULL DEFAULT '',
  address VARCHAR(200) NOT NULL DEFAULT '',
  labor_ins_no VARCHAR(20) NOT NULL DEFAULT '',     -- 勞保投保單位保險證號
  nhi_no VARCHAR(20) NOT NULL DEFAULT '',           -- 健保投保單位代號
  tax_unit_no VARCHAR(20) NOT NULL DEFAULT '',      -- 扣繳單位統一編號（通常同統編）
  occ_rate DECIMAL(6,4) NOT NULL DEFAULT 0.18,      -- 職災保險費率（%）＝行業別費率＋上下班災害費率 0.07
  pay_day TINYINT NOT NULL DEFAULT 5,               -- 每月發薪日（次月幾日）
  leave_system CHAR(1) NOT NULL DEFAULT 'A',        -- 特休：A 週年制、C 曆年制（依比例）
  ot_round_min INT NOT NULL DEFAULT 30,             -- 加班時數計算單位（分鐘，不足捨去）
  late_grace INT NOT NULL DEFAULT 5,                -- 遲到寬限（分鐘）
  late_deduct TINYINT NOT NULL DEFAULT 1,           -- 遲到早退按分鐘比例扣薪
  absent_deduct TINYINT NOT NULL DEFAULT 1,         -- 曠職按日扣薪
  attend_rule CHAR(1) NOT NULL DEFAULT 'R',         -- 全勤獎金：R 依請假比例扣、A 有影響全勤的假就不發
  week_start TINYINT NOT NULL DEFAULT 1,            -- 班表一週從星期幾開始（1＝一、7＝日）
  gl_mode VARCHAR(4) NOT NULL DEFAULT 'run',
  slip_footer VARCHAR(200) NOT NULL DEFAULT '',
  closed_ym CHAR(6) NOT NULL DEFAULT ''             -- 已關帳（薪資發放完畢）的最後年月：出勤、請假、加班不能再改
);

CREATE TABLE IF NOT EXISTS users (
  uid VARCHAR(20) PRIMARY KEY,
  name VARCHAR(30) NOT NULL,
  pw_hash VARCHAR(200) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT '',
  is_admin TINYINT NOT NULL DEFAULT 0,
  emp_code VARCHAR(20) NOT NULL DEFAULT '',         -- 對應的員工（員工自助：打卡、請假、看薪資單）
  active TINYINT NOT NULL DEFAULT 1,
  last_login DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_perms (
  uid VARCHAR(20) NOT NULL,
  func VARCHAR(8) NOT NULL,
  lvl TINYINT NOT NULL DEFAULT 0,                   -- 0 無、1 查詢、2 維護
  PRIMARY KEY (uid, func)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  uid VARCHAR(20) NOT NULL DEFAULT '',
  action VARCHAR(30) NOT NULL,
  target VARCHAR(60) NOT NULL DEFAULT '',
  detail VARCHAR(500) NOT NULL DEFAULT '',
  INDEX idx_at (at)
);

-- ---------------------------------------------------------------- 組織與員工
CREATE TABLE IF NOT EXISTS departments (
  code VARCHAR(10) PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  cost_type CHAR(1) NOT NULL DEFAULT 'A',           -- A 管理、S 推銷、M 製造、R 研發（決定薪資費用科目）
  manager VARCHAR(20) NOT NULL DEFAULT '',          -- 主管員工編號（請假加班第一層審核）
  active TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS employees (
  code VARCHAR(20) PRIMARY KEY,
  name VARCHAR(30) NOT NULL,
  id_no VARCHAR(12) NOT NULL DEFAULT '',            -- 身分證／居留證號
  gender CHAR(1) NOT NULL DEFAULT 'M',              -- M 男、F 女
  birthday DATE NULL,
  nationality CHAR(1) NOT NULL DEFAULT 'T',         -- T 本國、F 外國籍、P 外籍有永久居留／配偶（適用勞退）
  hire_date DATE NULL,
  seniority_date DATE NULL,                         -- 年資起算日（空白＝到職日）
  leave_date DATE NULL,                             -- 離職日（最後在職日）
  dept VARCHAR(10) NOT NULL DEFAULT '',
  title VARCHAR(30) NOT NULL DEFAULT '',
  emp_type CHAR(1) NOT NULL DEFAULT 'M',            -- M 月薪、H 時薪、P 部分工時（月薪）
  status CHAR(1) NOT NULL DEFAULT 'A',              -- A 在職、L 留職停薪、Q 離職
  base_salary DECIMAL(12,0) NOT NULL DEFAULT 0,     -- 本薪（月薪）
  hourly_wage DECIMAL(10,2) NOT NULL DEFAULT 0,     -- 時薪（時薪人員）
  shift_group VARCHAR(10) NOT NULL DEFAULT '',      -- 預設班別（沒有排班時用）
  punch_required TINYINT NOT NULL DEFAULT 1,        -- 需要打卡
  gps_site INT NOT NULL DEFAULT 0,                  -- 預設打卡地點（0＝任一地點）
  phone VARCHAR(30) NOT NULL DEFAULT '',
  mobile VARCHAR(30) NOT NULL DEFAULT '',
  email VARCHAR(80) NOT NULL DEFAULT '',
  address VARCHAR(200) NOT NULL DEFAULT '',
  emergency VARCHAR(60) NOT NULL DEFAULT '',        -- 緊急聯絡人與電話
  bank_code VARCHAR(10) NOT NULL DEFAULT '',        -- 銀行代號（7 碼含分行）
  bank_account VARCHAR(20) NOT NULL DEFAULT '',
  -- 保險與退休金
  labor_ins TINYINT NOT NULL DEFAULT 1,             -- 勞保（普通事故）
  employment_ins TINYINT NOT NULL DEFAULT 1,        -- 就業保險（65 歲以上、外國籍不加保）
  occ_ins TINYINT NOT NULL DEFAULT 1,               -- 職災保險
  nhi TINYINT NOT NULL DEFAULT 1,                   -- 健保由本公司投保
  pension TINYINT NOT NULL DEFAULT 1,               -- 勞退新制雇主提繳 6%
  labor_wage DECIMAL(10,0) NOT NULL DEFAULT 0,      -- 勞保投保薪資（0＝依月薪自動對照分級表）
  nhi_wage DECIMAL(10,0) NOT NULL DEFAULT 0,        -- 健保投保金額（0＝自動）
  pension_wage DECIMAL(10,0) NOT NULL DEFAULT 0,    -- 勞退月提繳工資（0＝自動）
  nhi_dependents TINYINT NOT NULL DEFAULT 0,        -- 健保眷屬人數（計費最多 3 口）
  pension_self DECIMAL(4,2) NOT NULL DEFAULT 0,     -- 勞退個人自願提繳率 0～6（%）
  ins_date DATE NULL,                               -- 加保日（空白＝到職日）
  -- 所得稅
  tax_mode CHAR(1) NOT NULL DEFAULT 'T',            -- T 依扣繳稅額表（概算）、R 固定扣繳率、N 不扣繳
  tax_dependents TINYINT NOT NULL DEFAULT 0,        -- 免稅額申報表的受扶養親屬人數
  tax_rate DECIMAL(5,2) NOT NULL DEFAULT 5,         -- 固定扣繳率（%）
  memo VARCHAR(300) NOT NULL DEFAULT '',
  active TINYINT NOT NULL DEFAULT 1,
  INDEX idx_dept (dept)
);

CREATE TABLE IF NOT EXISTS salary_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  emp VARCHAR(20) NOT NULL,
  eff_date DATE NOT NULL,
  base_salary DECIMAL(12,0) NOT NULL DEFAULT 0,
  hourly_wage DECIMAL(10,2) NOT NULL DEFAULT 0,
  reason VARCHAR(60) NOT NULL DEFAULT '',           -- 到職、調薪、升遷、試用期滿…
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_emp (emp, eff_date)
);

-- 薪資科目（應發、應扣、公司負擔、參考）
CREATE TABLE IF NOT EXISTS pay_items (
  code VARCHAR(12) PRIMARY KEY,
  name VARCHAR(30) NOT NULL,
  kind CHAR(1) NOT NULL DEFAULT 'E',                -- E 應發、D 應扣、C 公司負擔、R 參考
  method CHAR(1) NOT NULL DEFAULT 'F',              -- F 員工固定金額、M 每月輸入、S 系統計算
  taxable TINYINT NOT NULL DEFAULT 1,               -- 應稅（計入薪資所得）
  regular TINYINT NOT NULL DEFAULT 0,               -- 經常性給與（計入加班費、請假扣薪、投保薪資基數）
  nhi_bonus TINYINT NOT NULL DEFAULT 0,             -- 獎金：計入二代健保補充保費（年累計超過投保金額 4 倍）
  income_code VARCHAR(4) NOT NULL DEFAULT '50',     -- 所得類別（扣繳憑單）
  gl_account VARCHAR(12) NOT NULL DEFAULT '',       -- 會計科目（空白＝依部門別的薪資支出科目）
  sort INT NOT NULL DEFAULT 100,
  sys TINYINT NOT NULL DEFAULT 0,                   -- 系統內建（不可刪除）
  memo VARCHAR(200) NOT NULL DEFAULT '',
  active TINYINT NOT NULL DEFAULT 1
);

-- 員工固定薪資項目（津貼、固定扣款）
CREATE TABLE IF NOT EXISTS emp_items (
  emp VARCHAR(20) NOT NULL,
  item VARCHAR(12) NOT NULL,
  amount DECIMAL(12,0) NOT NULL DEFAULT 0,
  PRIMARY KEY (emp, item)
);

-- 津貼、獎金、年終獎金規則（月數或固定金額）
CREATE TABLE IF NOT EXISTS bonus_rules (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  item VARCHAR(12) NOT NULL,                        -- 發在哪個薪資科目
  basis CHAR(1) NOT NULL DEFAULT 'M',               -- M 月數（×本薪＋經常性津貼）、B 月數（×本薪）、A 固定金額
  value DECIMAL(12,2) NOT NULL DEFAULT 0,           -- 月數或金額
  prorate CHAR(1) NOT NULL DEFAULT 'Y',             -- Y 依當年在職月數比例、D 依在職日數比例、N 不打折
  min_months INT NOT NULL DEFAULT 0,                -- 在職滿幾個月才發
  depts VARCHAR(200) NOT NULL DEFAULT '',           -- 適用部門（逗號分隔，空白＝全部）
  exclude_left TINYINT NOT NULL DEFAULT 1,          -- 發放日前已離職者不發
  memo VARCHAR(200) NOT NULL DEFAULT '',
  active TINYINT NOT NULL DEFAULT 1
);

-- 法令參數（依生效日，可保留歷年）
CREATE TABLE IF NOT EXISTS law_params (
  k VARCHAR(30) NOT NULL,
  eff_date DATE NOT NULL,
  v VARCHAR(60) NOT NULL,
  PRIMARY KEY (k, eff_date)
);

-- 投保分級表：LI 勞保、LIP 部分工時勞保低級距、OC 職災保險、NHI 健保、PEN 勞退月提繳工資
CREATE TABLE IF NOT EXISTS ins_grades (
  kind VARCHAR(4) NOT NULL,
  eff_date DATE NOT NULL,
  amount DECIMAL(10,0) NOT NULL,
  PRIMARY KEY (kind, eff_date, amount)
);

-- ---------------------------------------------------------------- 差勤
CREATE TABLE IF NOT EXISTS shifts (
  code VARCHAR(12) PRIMARY KEY,
  name VARCHAR(30) NOT NULL,
  start_t CHAR(5) NOT NULL DEFAULT '09:00',
  end_t CHAR(5) NOT NULL DEFAULT '18:00',
  break_min INT NOT NULL DEFAULT 60,
  day_type CHAR(1) NOT NULL DEFAULT 'W',            -- W 工作日、R 休息日、H 例假、N 國定假日（休）
  color VARCHAR(9) NOT NULL DEFAULT '#1E88E5',
  sort INT NOT NULL DEFAULT 100,
  memo VARCHAR(100) NOT NULL DEFAULT '',
  active TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS roster (
  emp VARCHAR(20) NOT NULL,
  d DATE NOT NULL,
  shift VARCHAR(12) NOT NULL,
  note VARCHAR(60) NOT NULL DEFAULT '',
  PRIMARY KEY (emp, d),
  INDEX idx_d (d)
);

-- 行事曆：國定假日、補班日、公司休假
CREATE TABLE IF NOT EXISTS calendar (
  d DATE PRIMARY KEY,
  kind CHAR(1) NOT NULL,                            -- N 國定假日、W 補班（工作日）、C 公司休假（給薪）
  name VARCHAR(40) NOT NULL DEFAULT ''
);

-- 天然災害與不可預期事件（颱風、地震、水災、疫情…）停班停課
CREATE TABLE IF NOT EXISTS disasters (
  id INT AUTO_INCREMENT PRIMARY KEY,
  d DATE NOT NULL,
  kind VARCHAR(10) NOT NULL DEFAULT 'typhoon',      -- typhoon 颱風、quake 地震、flood 水災、epidemic 疫情、other 其他
  title VARCHAR(60) NOT NULL DEFAULT '',
  scope VARCHAR(200) NOT NULL DEFAULT '',           -- 適用部門（逗號分隔，空白＝全公司）
  period CHAR(1) NOT NULL DEFAULT 'D',              -- D 全天、A 上午、P 下午
  pay_policy CHAR(1) NOT NULL DEFAULT 'P',          -- P 照常給薪、U 不給薪（不扣全勤、不算曠職）
  work_extra DECIMAL(4,2) NOT NULL DEFAULT 1,       -- 停班日仍出勤：另加發幾倍日薪（依工作規則；0＝不加發）
  memo VARCHAR(200) NOT NULL DEFAULT '',
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  INDEX idx_d (d)
);

CREATE TABLE IF NOT EXISTS gps_sites (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  address VARCHAR(200) NOT NULL DEFAULT '',
  lat DECIMAL(10,6) NOT NULL DEFAULT 0,
  lon DECIMAL(10,6) NOT NULL DEFAULT 0,
  radius INT NOT NULL DEFAULT 150,                  -- 允許打卡半徑（公尺）
  max_accuracy INT NOT NULL DEFAULT 200,            -- GPS 精確度超過幾公尺列為「待確認」
  active TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS punches (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  emp VARCHAR(20) NOT NULL,
  ts DATETIME NOT NULL,
  kind CHAR(1) NOT NULL DEFAULT 'I',                -- I 上班、O 下班
  source VARCHAR(8) NOT NULL DEFAULT 'gps',         -- gps 手機定位、pc 電腦、fix 補卡、import 匯入
  lat DECIMAL(10,6) NULL,
  lon DECIMAL(10,6) NULL,
  accuracy INT NULL,
  site_id INT NOT NULL DEFAULT 0,
  distance INT NULL,                                -- 距打卡地點（公尺）
  ok TINYINT NOT NULL DEFAULT 1,                    -- 1 有效、0 待確認（超出範圍或精確度不足）
  device VARCHAR(120) NOT NULL DEFAULT '',
  ip VARCHAR(45) NOT NULL DEFAULT '',
  note VARCHAR(100) NOT NULL DEFAULT '',
  void TINYINT NOT NULL DEFAULT 0,
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  INDEX idx_emp_ts (emp, ts),
  INDEX idx_ts (ts)
);

-- 假別
CREATE TABLE IF NOT EXISTS leave_types (
  code VARCHAR(10) PRIMARY KEY,
  name VARCHAR(30) NOT NULL,
  pay_ratio DECIMAL(4,3) NOT NULL DEFAULT 1,        -- 給薪比例：1 全薪、0.5 半薪、0 不給薪
  min_hours DECIMAL(4,2) NOT NULL DEFAULT 1,        -- 最小請假單位（小時）
  quota_days DECIMAL(6,2) NOT NULL DEFAULT 0,       -- 每年上限（日；0＝不限或依其他規定）
  gender CHAR(1) NOT NULL DEFAULT '',               -- 限定性別：F 女、M 男、空白不限
  affects_attend TINYINT NOT NULL DEFAULT 0,        -- 影響全勤獎金
  balance CHAR(1) NOT NULL DEFAULT '',              -- A 扣特休餘額、C 扣補休餘額
  calendar_days TINYINT NOT NULL DEFAULT 0,         -- 依曆計算（例假日照算，如產假、婚喪假依規定）
  law_note VARCHAR(300) NOT NULL DEFAULT '',
  color VARCHAR(9) NOT NULL DEFAULT '#26A69A',
  sort INT NOT NULL DEFAULT 100,
  sys TINYINT NOT NULL DEFAULT 0,
  active TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS leave_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  emp VARCHAR(20) NOT NULL,
  ltype VARCHAR(10) NOT NULL,
  start_at DATETIME NOT NULL,
  end_at DATETIME NOT NULL,
  hours DECIMAL(7,2) NOT NULL DEFAULT 0,
  reason VARCHAR(200) NOT NULL DEFAULT '',
  proxy VARCHAR(20) NOT NULL DEFAULT '',            -- 職務代理人
  status TINYINT NOT NULL DEFAULT 0,                -- 0 待審核、1 核准、9 駁回／撤銷
  approver VARCHAR(20) NOT NULL DEFAULT '',
  approved_at DATETIME NULL,
  occ_case INT NOT NULL DEFAULT 0,                  -- 公傷病假對應的職災案件
  disaster INT NOT NULL DEFAULT 0,                  -- 災害假對應的事件
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_emp (emp, start_at)
);

-- 假期額度：特休（依年資）、補休（加班換休）、遞延特休
CREATE TABLE IF NOT EXISTS leave_grants (
  id INT AUTO_INCREMENT PRIMARY KEY,
  emp VARCHAR(20) NOT NULL,
  kind CHAR(1) NOT NULL,                            -- A 特休、C 補休
  start_d DATE NOT NULL,                            -- 可使用期間
  end_d DATE NOT NULL,
  hours DECIMAL(7,2) NOT NULL DEFAULT 0,
  pay_rate DECIMAL(10,2) NOT NULL DEFAULT 0,        -- 補休：未休完要折發的每小時金額（原加班費率）
  source VARCHAR(10) NOT NULL DEFAULT 'law',        -- law 依法、manual 手動、ot 加班、defer 遞延
  ref_id INT NOT NULL DEFAULT 0,
  settled CHAR(1) NOT NULL DEFAULT '',              -- 空白未結算、P 折發工資、D 遞延到下一年、X 已休完
  settled_ym CHAR(6) NOT NULL DEFAULT '',
  settled_hours DECIMAL(7,2) NOT NULL DEFAULT 0,
  settled_amount DECIMAL(12,0) NOT NULL DEFAULT 0,
  memo VARCHAR(100) NOT NULL DEFAULT '',
  INDEX idx_emp (emp, kind, start_d)
);

CREATE TABLE IF NOT EXISTS overtime (
  id INT AUTO_INCREMENT PRIMARY KEY,
  emp VARCHAR(20) NOT NULL,
  d DATE NOT NULL,
  start_at DATETIME NOT NULL,
  end_at DATETIME NOT NULL,
  hours DECIMAL(6,2) NOT NULL DEFAULT 0,
  day_type CHAR(1) NOT NULL DEFAULT 'W',            -- W 平日、R 休息日、N 國定假日／特休日、H 例假（天災等）、D 災害停班日
  comp CHAR(1) NOT NULL DEFAULT 'P',                -- P 加班費、C 換補休
  reason VARCHAR(200) NOT NULL DEFAULT '',
  status TINYINT NOT NULL DEFAULT 0,                -- 0 待審核、1 核准、9 駁回
  approver VARCHAR(20) NOT NULL DEFAULT '',
  approved_at DATETIME NULL,
  amount DECIMAL(12,0) NOT NULL DEFAULT 0,          -- 加班費（核准時試算，計薪時重算）
  grant_id INT NOT NULL DEFAULT 0,                  -- 換補休時產生的補休額度
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_emp (emp, d)
);

-- 職業災害（公傷）
CREATE TABLE IF NOT EXISTS occ_cases (
  id INT AUTO_INCREMENT PRIMARY KEY,
  case_no VARCHAR(20) NOT NULL,
  emp VARCHAR(20) NOT NULL,
  injury_at DATETIME NOT NULL,
  kind CHAR(1) NOT NULL DEFAULT 'W',                -- W 工作場所、C 上下班途中、D 職業病、O 出差／公出
  place VARCHAR(100) NOT NULL DEFAULT '',
  description VARCHAR(500) NOT NULL DEFAULT '',
  injury VARCHAR(200) NOT NULL DEFAULT '',          -- 傷害部位與程度
  hospital VARCHAR(60) NOT NULL DEFAULT '',
  reported_at DATE NULL,                            -- 職災通報（重大職災 8 小時內通報勞檢）
  claim_at DATE NULL,                               -- 向勞保局申請職災給付日
  status CHAR(1) NOT NULL DEFAULT 'T',              -- T 治療中、R 已復工、C 結案
  return_date DATE NULL,
  avg_wage DECIMAL(10,0) NOT NULL DEFAULT 0,        -- 原領工資（月）
  memo VARCHAR(300) NOT NULL DEFAULT '',
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_no (case_no)
);

CREATE TABLE IF NOT EXISTS occ_costs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  case_id INT NOT NULL,
  d DATE NOT NULL,
  kind VARCHAR(8) NOT NULL,                         -- medical 醫療費用、wage 工資補償、disab 失能補償、death 死亡補償、other 其他、ins 保險給付（抵充）
  amount DECIMAL(12,0) NOT NULL DEFAULT 0,
  payer CHAR(1) NOT NULL DEFAULT 'C',               -- C 公司支付、I 保險給付
  memo VARCHAR(200) NOT NULL DEFAULT '',
  gl_batch_id INT NULL,
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  INDEX idx_case (case_id)
);

-- ---------------------------------------------------------------- 薪資
-- 每月變動輸入（獎金、扣款、借支…）
CREATE TABLE IF NOT EXISTS pay_inputs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ym CHAR(6) NOT NULL,
  run_kind CHAR(1) NOT NULL DEFAULT 'M',            -- M 月薪、B 獎金
  emp VARCHAR(20) NOT NULL,
  item VARCHAR(12) NOT NULL,
  amount DECIMAL(12,0) NOT NULL DEFAULT 0,
  note VARCHAR(100) NOT NULL DEFAULT '',
  source VARCHAR(10) NOT NULL DEFAULT 'manual',     -- manual、bonus（獎金規則）、leave（特休／補休折發）、occ（職災）
  ref_id INT NOT NULL DEFAULT 0,
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  INDEX idx_ym (ym, run_kind, emp)
);

CREATE TABLE IF NOT EXISTS payroll_runs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ym CHAR(6) NOT NULL,
  kind CHAR(1) NOT NULL DEFAULT 'M',                -- M 月薪、B 獎金（年終、三節、績效）
  title VARCHAR(60) NOT NULL DEFAULT '',
  pay_date DATE NOT NULL,
  status TINYINT NOT NULL DEFAULT 0,                -- 0 試算、1 已確認、2 已發放
  emp_count INT NOT NULL DEFAULT 0,
  gross DECIMAL(14,0) NOT NULL DEFAULT 0,
  net DECIMAL(14,0) NOT NULL DEFAULT 0,
  employer_cost DECIMAL(14,0) NOT NULL DEFAULT 0,
  gl_batch_id INT NULL,
  pay_gl_batch_id INT NULL,                         -- 發放分錄（借應付薪資／貸銀行存款）
  note VARCHAR(200) NOT NULL DEFAULT '',
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  confirmed_by VARCHAR(20) NOT NULL DEFAULT '',
  confirmed_at DATETIME NULL,
  UNIQUE KEY uq_run (ym, kind, title)
);

CREATE TABLE IF NOT EXISTS payslips (
  id INT AUTO_INCREMENT PRIMARY KEY,
  run_id INT NOT NULL,
  emp VARCHAR(20) NOT NULL,
  name VARCHAR(30) NOT NULL DEFAULT '',
  dept VARCHAR(10) NOT NULL DEFAULT '',
  cost_type CHAR(1) NOT NULL DEFAULT 'A',
  base_salary DECIMAL(12,0) NOT NULL DEFAULT 0,
  work_days DECIMAL(5,2) NOT NULL DEFAULT 0,        -- 本月在職日數（以 30 日計）
  gross DECIMAL(12,0) NOT NULL DEFAULT 0,           -- 應發合計
  deduct DECIMAL(12,0) NOT NULL DEFAULT 0,          -- 應扣合計
  net DECIMAL(12,0) NOT NULL DEFAULT 0,             -- 實發
  taxable DECIMAL(12,0) NOT NULL DEFAULT 0,         -- 應稅所得（已減自提勞退）
  bonus_nhi DECIMAL(12,0) NOT NULL DEFAULT 0,       -- 本次計入補充保費的獎金
  labor_wage DECIMAL(10,0) NOT NULL DEFAULT 0,
  occ_wage DECIMAL(10,0) NOT NULL DEFAULT 0,
  nhi_wage DECIMAL(10,0) NOT NULL DEFAULT 0,
  pension_wage DECIMAL(10,0) NOT NULL DEFAULT 0,
  labor_emp DECIMAL(10,0) NOT NULL DEFAULT 0,       -- 員工自付勞保（含就保）
  nhi_emp DECIMAL(10,0) NOT NULL DEFAULT 0,         -- 員工自付健保（含眷屬）
  nhi_sup_emp DECIMAL(10,0) NOT NULL DEFAULT 0,     -- 二代健保補充保費（員工）
  pension_self DECIMAL(10,0) NOT NULL DEFAULT 0,    -- 個人自提勞退
  tax DECIMAL(10,0) NOT NULL DEFAULT 0,             -- 代扣所得稅
  labor_er DECIMAL(10,0) NOT NULL DEFAULT 0,        -- 公司負擔勞保（含就保）
  occ_er DECIMAL(10,0) NOT NULL DEFAULT 0,          -- 公司負擔職災保險
  fund_er DECIMAL(10,0) NOT NULL DEFAULT 0,         -- 工資墊償基金
  nhi_er DECIMAL(10,0) NOT NULL DEFAULT 0,          -- 公司負擔健保
  pension_er DECIMAL(10,0) NOT NULL DEFAULT 0,      -- 公司提繳勞退 6%
  ot_hours DECIMAL(7,2) NOT NULL DEFAULT 0,
  leave_hours DECIMAL(7,2) NOT NULL DEFAULT 0,
  late_min INT NOT NULL DEFAULT 0,
  notes TEXT NULL,                                  -- 計算說明（JSON 陣列）
  UNIQUE KEY uq_slip (run_id, emp)
);

CREATE TABLE IF NOT EXISTS payslip_lines (
  id INT AUTO_INCREMENT PRIMARY KEY,
  slip_id INT NOT NULL,
  item VARCHAR(12) NOT NULL,
  name VARCHAR(30) NOT NULL,
  kind CHAR(1) NOT NULL,
  amount DECIMAL(12,0) NOT NULL DEFAULT 0,
  note VARCHAR(120) NOT NULL DEFAULT '',
  taxable TINYINT NOT NULL DEFAULT 1,
  regular TINYINT NOT NULL DEFAULT 0,
  nhi_bonus TINYINT NOT NULL DEFAULT 0,
  gl_account VARCHAR(12) NOT NULL DEFAULT '',
  sort INT NOT NULL DEFAULT 100,
  INDEX idx_slip (slip_id)
);

-- 二代健保：投保單位補充保費（每月）
CREATE TABLE IF NOT EXISTS nhi_employer_sup (
  ym CHAR(6) PRIMARY KEY,
  wage_total DECIMAL(14,0) NOT NULL DEFAULT 0,
  insured_total DECIMAL(14,0) NOT NULL DEFAULT 0,
  premium DECIMAL(12,0) NOT NULL DEFAULT 0,
  gl_batch_id INT NULL
);

-- ---------------------------------------------------------------- 會計拋轉
CREATE TABLE IF NOT EXISTS gl_map (
  k VARCHAR(16) PRIMARY KEY,
  account VARCHAR(12) NOT NULL,
  name VARCHAR(40) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS gl_batches (
  id INT AUTO_INCREMENT PRIMARY KEY,
  batch_no VARCHAR(20) NOT NULL,
  batch_uid VARCHAR(64) NOT NULL,                   -- 全域唯一代碼（會計系統用來防止重複匯入）
  date_from DATE NOT NULL,
  date_to DATE NOT NULL,
  scope VARCHAR(60) NOT NULL DEFAULT '',
  method VARCHAR(8) NOT NULL DEFAULT 'file',        -- file 拋轉檔、api 直接傳送
  status TINYINT NOT NULL DEFAULT 1,                -- 1 已產生、2 已送達會計、9 已取消
  voucher_count INT NOT NULL DEFAULT 0,
  total DECIMAL(16,2) NOT NULL DEFAULT 0,
  payload LONGTEXT NULL,
  result VARCHAR(500) NOT NULL DEFAULT '',
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_batch_no (batch_no)
);

-- 年度特休未休估列（應付休假給付）
CREATE TABLE IF NOT EXISTS leave_accruals (
  ym CHAR(6) PRIMARY KEY,
  amount DECIMAL(14,0) NOT NULL DEFAULT 0,
  detail TEXT NULL,
  gl_batch_id INT NULL,
  created_by VARCHAR(20) NOT NULL DEFAULT ''
);
