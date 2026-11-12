"""員工手機 GPS 打卡網頁（由「手機連線服務」提供：GET /punch）。

參考 achir1015/gps-arrival-test：用瀏覽器 navigator.geolocation（高精確度、不用快取位置）取得座標，
送到電腦端判定是否在打卡地點範圍內（Haversine 距離）。手機瀏覽器只允許在 HTTPS 網址取得定位，
所以公司外或用手機打卡時，請用「外出連線」（Cloudflare 加密通道）的網址。
可在手機「加入主畫面」，像 App 一樣使用；另有請假申請、特休補休餘額與最近的請假紀錄。
"""

MANIFEST = """{"name": "資料助秘 GPS 打卡", "short_name": "GPS 打卡", "start_url": "/punch", "display": "standalone",
"background_color": "#0F2747", "theme_color": "#1E4D8C", "lang": "zh-Hant",
"icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}]}"""

PAGE = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1E4D8C"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="GPS 打卡">
<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/icon.png">
<title>GPS 打卡｜資料助秘之一般公司人事薪資差勤</title>
<style>
:root{--p:#1E4D8C;--pd:#0F2747;--a:#0F766E;--v:#6D28D9;--bg:#F2F5FA;--t:#1F2937;--m:#6B7280;--ok:#16A34A;--bad:#DC2626;--warn:#D97706}
*{box-sizing:border-box}body{margin:0;font-family:"Noto Sans TC","Microsoft JhengHei","PingFang TC",sans-serif;background:var(--bg);color:var(--t)}
header{background:linear-gradient(135deg,var(--pd),var(--p) 60%,#178A8F);color:#fff;padding:18px 18px 22px;padding-top:max(18px,env(safe-area-inset-top))}
header .co{font-size:13px;opacity:.8}header .hi{font-size:22px;font-weight:800;margin-top:2px}header .clock{font-size:40px;font-weight:800;letter-spacing:2px;margin-top:6px;font-variant-numeric:tabular-nums}
header .date{font-size:14px;opacity:.85}
main{padding:14px;max-width:560px;margin:0 auto}
.card{background:#fff;border:1px solid #E5E9F0;border-radius:16px;padding:16px;margin-bottom:14px;box-shadow:0 6px 18px -8px rgba(30,58,95,.25)}
.card h3{margin:0 0 10px;font-size:16px}
.shift{font-size:20px;font-weight:800;color:var(--p)}
.btns{display:flex;gap:12px;margin-top:12px}
.btn{flex:1;border:0;border-radius:16px;padding:20px 8px;font-size:19px;font-weight:800;color:#fff;cursor:pointer;box-shadow:0 8px 16px -8px rgba(0,0,0,.5)}
.btn.in{background:var(--a)}.btn.out{background:var(--v)}.btn:disabled{opacity:.5}
.small{border:1px solid #C7D4E8;background:#fff;color:var(--p);border-radius:10px;padding:10px 14px;font-size:15px;font-weight:600;cursor:pointer}
.status{margin-top:12px;padding:10px 12px;border-radius:10px;background:#F7F9FC;font-size:14px;min-height:22px;white-space:pre-line}
.status.ok{background:#DCFCE7;color:#166534}.status.bad{background:#FEE2E2;color:#991B1B}.status.warn{background:#FEF3C7;color:#92400E}
.row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #EEF2F7;font-size:15px}
.row:last-child{border-bottom:0}.chip{display:inline-block;border-radius:20px;padding:2px 10px;font-size:13px;font-weight:700}
.c-in{background:#D7F5F0;color:#0F766E}.c-out{background:#EEE8FF;color:#6D28D9}.c-warn{background:#FEF1C7;color:#B45309}
.kpis{display:flex;gap:10px}.kpi{flex:1;background:#F7F9FC;border-radius:12px;padding:12px;text-align:center}
.kpi b{display:block;font-size:22px;color:var(--p)}.kpi span{font-size:12px;color:var(--m)}
label{display:block;font-size:13px;color:var(--m);margin:10px 0 4px}
input,select,textarea{width:100%;font-size:16px;padding:11px 12px;border:1px solid #CBD5E1;border-radius:10px;background:#FBFCFE;font-family:inherit}
.login{max-width:420px;margin:30px auto}.muted{color:var(--m);font-size:13px}
iframe{width:100%;height:190px;border:0;border-radius:12px;margin-top:10px}
.hidden{display:none}.tabs{display:flex;gap:8px;margin-bottom:12px}.tab{flex:1;text-align:center;padding:10px;border-radius:20px;background:#EAF0F8;color:var(--p);font-weight:700;cursor:pointer}
.tab.on{background:var(--p);color:#fff}
</style></head><body>
<header><div class="co" id="co">資料助秘之一般公司人事薪資差勤</div><div class="hi" id="hi">GPS 打卡</div>
<div class="clock" id="clock">--:--:--</div><div class="date" id="date"></div></header>
<main>
<div id="loginBox" class="card login hidden"><h3>員工登入</h3>
<label>帳號（員工編號）</label><input id="uid" autocomplete="username">
<label>密碼</label><input id="pw" type="password" autocomplete="current-password">
<div class="btns"><button class="btn in" onclick="login()">登入</button></div>
<div id="loginMsg" class="status"></div>
<p class="muted">預設密碼請洽人資；第一次登入後可在電腦版「變更密碼」。</p></div>

<div id="app" class="hidden">
<div class="tabs"><div class="tab on" id="t1" onclick="tab(1)">打卡</div><div class="tab" id="t2" onclick="tab(2)">請假</div><div class="tab" id="t3" onclick="tab(3)">紀錄</div></div>
<section id="s1">
<div class="card"><h3 id="today">今天</h3><div class="shift" id="shift">讀取中…</div>
<div class="btns"><button class="btn in" id="bIn" onclick="punch('I')">上班打卡</button><button class="btn out" id="bOut" onclick="punch('O')">下班打卡</button></div>
<div class="status" id="st">按下按鈕後會取得 GPS 定位（請允許瀏覽器使用位置）</div><div id="map"></div></div>
<div class="card"><h3>今天的打卡</h3><div id="plist" class="muted">尚無紀錄</div></div>
</section>
<section id="s2" class="hidden"><div class="card"><h3>請假申請</h3>
<label>假別</label><select id="lt"></select>
<label>開始</label><input id="ls" type="datetime-local"><label>結束</label><input id="le" type="datetime-local">
<label>事由</label><input id="lr">
<div class="status" id="lcalc"></div>
<div class="btns"><button class="btn in" onclick="leave()">送出請假</button></div></div>
<div class="card"><h3>我的假期餘額</h3><div class="kpis"><div class="kpi"><b id="kA">-</b><span>特休（小時）</span></div><div class="kpi"><b id="kC">-</b><span>補休（小時）</span></div></div></div>
</section>
<section id="s3" class="hidden"><div class="card"><h3>最近的請假</h3><div id="llist" class="muted">讀取中…</div></div>
<div class="card"><button class="small" onclick="logout()">登出</button></div></section>
</div>
</main>
<script>
const $=id=>document.getElementById(id);let TOKEN=localStorage.getItem("hr_token")||"";
const WD="日一二三四五六";
function roc(d){return (d.getFullYear()-1911)+"/"+String(d.getMonth()+1).padStart(2,"0")+"/"+String(d.getDate()).padStart(2,"0")}
function tick(){const d=new Date();$("clock").textContent=d.toTimeString().slice(0,8);$("date").textContent=roc(d)+"（"+WD[d.getDay()]+"）"}
setInterval(tick,1000);tick();
function un(v){if(v&&typeof v==="object"){if("$d"in v)return Number(v.$d);if("$dt"in v)return new Date(v.$dt);if("$date"in v)return v.$date;
 if(Array.isArray(v))return v.map(un);const o={};for(const k in v)o[k]=un(v[k]);return o}return v}
async function post(path,body,tok){const h={"Content-Type":"application/json"};if(tok)h.Authorization="Bearer "+tok;
 const r=await fetch(path,{method:"POST",headers:h,body:JSON.stringify(body)});const j=await r.json();return [r.status,un(j)]}
async function call(method,args,kwargs){const [code,j]=await post("/api/call",{obj:"books",method,args:args||[],kwargs:kwargs||{}},TOKEN);
 if(j.relogin){TOKEN="";localStorage.removeItem("hr_token");show(false);throw new Error(j.error)}
 if(j.biz)throw new Error(j.biz);if(j.error)throw new Error(j.error);return j.result}
function show(on){$("loginBox").classList.toggle("hidden",on);$("app").classList.toggle("hidden",!on)}
function tab(n){for(const i of [1,2,3]){$("t"+i).classList.toggle("on",i==n);$("s"+i).classList.toggle("hidden",i!=n)}if(n==3)loadLeaves();if(n==2)loadBal()}
async function login(){$("loginMsg").textContent="登入中…";try{const [code,j]=await post("/api/login",{uid:$("uid").value.trim(),pw:$("pw").value});
 if(code!=200)throw new Error(j.error||"登入失敗");if(!j.user.emp_code)throw new Error("此帳號沒有對應員工，不能打卡");
 TOKEN=j.token;localStorage.setItem("hr_token",TOKEN);localStorage.setItem("hr_emp",j.user.emp_code);localStorage.setItem("hr_uid",$("uid").value.trim());show(true);init()}
 catch(e){$("loginMsg").textContent=e.message;$("loginMsg").className="status bad"}}
async function logout(){try{await post("/api/logout",{},TOKEN)}catch(e){}TOKEN="";localStorage.removeItem("hr_token");show(false)}
function hm(d){return d instanceof Date?d.toTimeString().slice(0,5):""}
async function loadToday(){const t=await call("my_today");$("hi").textContent=t.name+"，您好";
 const s=t.shift;$("today").textContent="今天 "+roc(new Date())+"（"+WD[new Date().getDay()]+"）";
 $("shift").textContent=s.code+" "+s.name+(s.start?"　"+hm(s.start)+"～"+hm(s.end):"");
 $("plist").innerHTML=t.punches.length?t.punches.map(p=>`<div class="row"><span class="chip ${p.kind=="I"?"c-in":"c-out"}">${p.kind=="I"?"上班":"下班"}</span><b>${p.ts.toTimeString().slice(0,8)}</b>${p.ok?"":'<span class="chip c-warn">待確認</span>'}</div>`).join(""):"尚無紀錄"}
async function init(){try{const c=await call("company_brief");$("co").textContent=c.name||"資料助秘";await loadToday();
 const types=await call("leave_types");$("lt").innerHTML=types.map(t=>`<option value="${t.code}">${t.name}</option>`).join("");
 const d=new Date();const z=x=>String(x).padStart(2,"0");const day=d.getFullYear()+"-"+z(d.getMonth()+1)+"-"+z(d.getDate());
 $("ls").value=day+"T09:00";$("le").value=day+"T18:00"}catch(e){$("st").textContent=e.message;$("st").className="status bad"}}
function punch(kind){const st=$("st");if(!navigator.geolocation){st.textContent="此瀏覽器不支援 GPS 定位";st.className="status bad";return}
 if(location.protocol!=="https:"&&location.hostname!=="localhost"&&location.hostname!=="127.0.0.1"){st.textContent="手機瀏覽器只允許在 HTTPS 網址取得定位，請改用人資提供的「外出連線」打卡網址（https://…/punch）";st.className="status bad";return}
 $("bIn").disabled=$("bOut").disabled=true;st.textContent="正在取得 GPS 定位…";st.className="status";
 navigator.geolocation.getCurrentPosition(async pos=>{try{const c=pos.coords;
  const r=await call("punch",[kind],{lat:c.latitude,lon:c.longitude,accuracy:Math.round(c.accuracy),device:navigator.userAgent.slice(0,110)});
  st.textContent="✅ "+r.text+(r.msg?"\n"+r.msg:"");st.className="status "+(r.ok?"ok":"warn");
  const la=c.latitude,lo=c.longitude,dd=0.003;
  $("map").innerHTML=`<iframe loading="lazy" src="https://www.openstreetmap.org/export/embed.html?bbox=${lo-dd},${la-dd},${lo+dd},${la+dd}&layer=mapnik&marker=${la},${lo}"></iframe>`;
  if(navigator.vibrate)navigator.vibrate(120);await loadToday()}catch(e){st.textContent="❌ "+e.message;st.className="status bad"}
  finally{$("bIn").disabled=$("bOut").disabled=false}},
 err=>{const m={1:"您拒絕了位置存取：請到瀏覽器（或手機設定）允許此網站使用位置。",2:"GPS 訊號無法取得，請到空曠處再試。",3:"GPS 取得逾時，請再試一次。"};
  st.textContent="❌ "+(m[err.code]||"GPS 發生錯誤");st.className="status bad";$("bIn").disabled=$("bOut").disabled=false},
 {enableHighAccuracy:true,timeout:15000,maximumAge:0})}
function fmt(v){return v.replace("T"," ").replaceAll("-","/")}
async function calcLeave(){try{const r=await call("leave_hours_self",[$("lt").value,fmt($("ls").value),fmt($("le").value)]);
 $("lcalc").textContent="共 "+Number(r.hours)+" 小時（"+r.text+"）";$("lcalc").className="status"}catch(e){$("lcalc").textContent=e.message;$("lcalc").className="status warn"}}
for(const id of ["lt","ls","le"])document.addEventListener("change",e=>{if(e.target.id===id)calcLeave()});
async function leave(){try{await call("request_leave",[null,$("lt").value,fmt($("ls").value),fmt($("le").value),$("lr").value]);
 $("lcalc").textContent="✅ 已送出，等待主管審核";$("lcalc").className="status ok";loadBal()}catch(e){$("lcalc").textContent="❌ "+e.message;$("lcalc").className="status bad"}}
async function loadBal(){try{const b=await call("my_balance");$("kA").textContent=Number(b.annual);$("kC").textContent=Number(b.comp)}catch(e){}}
async function loadLeaves(){try{const d=new Date();const a=new Date(d-90*864e5),b=new Date(+d+120*864e5);
 const rows=await call("leave_requests",[roc(a),roc(b),localStorage.getItem("hr_emp")||""]);
 $("llist").innerHTML=rows.length?rows.map(r=>`<div class="row"><span>${r.lname} ${roc(r.start_at)} ${hm(r.start_at)}</span><span>${Number(r.hours)}h <span class="chip ${r.status==1?"c-in":r.status==0?"c-warn":"c-out"}">${r.status_name}</span></span></div>`).join(""):"沒有請假紀錄"}
 catch(e){$("llist").textContent=e.message}}
(async()=>{if(TOKEN){try{const p=await call("my_profile");if(p){localStorage.setItem("hr_emp",p.code);show(true);init();return}}catch(e){}}
 $("uid").value=localStorage.getItem("hr_uid")||"";show(false)})();
</script></body></html>"""
