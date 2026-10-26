#include "web_portal.h"
#include "config.h"
#include "config_manager.h"
#include "ble_epd_client.h"
#include "display_ui.h"
#include <WiFi.h>
#include <ArduinoJson.h>

static const char PAGE_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ESP32 墨水屏网关管理系统</title>
<style>
:root{--primary:#3b82f6;--bg:#0f172a;--card:#1e293b;--text:#f8fafc;--sub:#94a3b8;--border:#334155;--success:#22c55e;--danger:#ef4444;--warn:#f59e0b;}
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
body{background:var(--bg);color:var(--text);padding:16px;display:flex;justify-content:center;}
.container{max-width:680px;width:100%;}
.header{text-align:center;padding:16px 0 20px;}
.header h1{font-size:22px;color:var(--text);margin-bottom:6px;}
.header p{font-size:13px;color:var(--sub);}
.banner{background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.3);padding:10px 14px;border-radius:8px;font-size:12px;margin-bottom:14px;line-height:1.6;}
.tabs{display:flex;gap:6px;margin-bottom:16px;background:var(--card);padding:4px;border-radius:10px;border:1px solid var(--border);}
.tab-btn{flex:1;padding:8px 0;background:none;border:none;color:var(--sub);font-size:13px;font-weight:600;border-radius:6px;cursor:pointer;transition:all .2s;}
.tab-btn.active{background:var(--primary);color:#fff;}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:16px;}
.card h2{font-size:16px;margin-bottom:12px;display:flex;align-items:center;gap:8px;}
.info-row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-size:13px;}
.info-row:last-child{border-bottom:none;}
.info-label{color:var(--sub);}
.info-val{font-weight:600;color:var(--text);word-break:break-all;}
.btn{width:100%;padding:10px 14px;background:var(--primary);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-top:10px;transition:opacity .2s;}
.btn:hover{opacity:0.9;}
.btn:disabled{opacity:0.5;cursor:not-allowed;}
.btn-sec{background:transparent;border:1px solid var(--border);color:var(--text);}
.btn-warn{background:var(--warn);color:#000;}
.btn-success{background:#059669;}
.btn-cyan{background:#0284c7;}
.btn-danger{background:var(--danger);}
.btn-group{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;}
.form-group{margin-bottom:14px;}
.form-group label{display:block;font-size:12px;color:var(--sub);margin-bottom:6px;font-weight:500;}
.form-group input, .form-group select{width:100%;padding:10px;background:#090d16;border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;}
.badge{padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;}
.badge-epd{background:#047857;color:#6ee7b7;}
.badge-other{background:#334155;color:#94a3b8;}
.device-item{display:flex;justify-content:space-between;align-items:center;padding:12px;border-radius:8px;background:#0f172a;margin-bottom:8px;border:1px solid var(--border);}
.dev-meta{font-size:11px;color:var(--sub);margin-top:4px;}
#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1e293b;border:1px solid var(--border);color:#fff;padding:10px 20px;border-radius:24px;font-size:13px;display:none;z-index:999;box-shadow:0 10px 25px rgba(0,0,0,0.5);}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📡 ESP32 墨水屏自动化网关</h1>
    <p>局域网 HTTP 数据中继 ➔ BLE 墨水屏控制器</p>
  </div>

  <div class="banner">
    💡 <b>局域网免记 IP：</b>设备连入局域网后，同网络电脑/手机直接在浏览器输入 <a href="http://epd-gateway.local" target="_blank" style="color:#38bdf8;font-weight:bold;text-decoration:underline;">http://epd-gateway.local</a> 即可访问后台（或看 LilyGO 屏幕右上角绿色 IP）。
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tab-dash')">状态监控</button>
    <button class="tab-btn" onclick="switchTab('tab-ble')">蓝牙墨水屏</button>
    <button class="tab-btn" onclick="switchTab('tab-server')">服务与屏幕</button>
    <button class="tab-btn" onclick="switchTab('tab-wifi')">WiFi 设置</button>
  </div>

  <!-- 选项卡 1: 仪表盘 -->
  <div id="tab-dash" class="tab-content">
    <div class="card">
      <h2>📊 运行状态</h2>
      <div class="info-row"><span class="info-label">WiFi 模式</span><span class="info-val" id="val-wifimode">-</span></div>
      <div class="info-row"><span class="info-label">IP 地址</span><span class="info-val" id="val-ip">-</span></div>
      <div class="info-row"><span class="info-label">局域网域名</span><span class="info-val" id="val-mdns" style="color:#38bdf8;">http://epd-gateway.local</span></div>
      <div class="info-row"><span class="info-label">绑定的墨水屏</span><span class="info-val" id="val-ble" style="color:#38bdf8;">-</span></div>
      <div class="info-row"><span class="info-label">当前屏幕规格</span><span class="info-val" id="val-screen">-</span></div>
      <div class="info-row"><span class="info-label">上次同步时间</span><span class="info-val" id="val-lastsync">-</span></div>
      <div class="info-row"><span class="info-label">同步结果</span><span class="info-val" id="val-laststat">-</span></div>
      <div class="info-row"><span class="info-label">自动刷新间隔</span><span class="info-val" id="val-interval">-</span></div>
    </div>
    <div class="card">
      <h2>⚡ 快捷控制与测试</h2>
      <div class="btn-group">
        <button class="btn btn-success" onclick="setCalendarMode()">📅 切换至日历模式 (农历/节气)</button>
        <button class="btn btn-cyan" onclick="setClockMode()">⏰ 切换至时钟模式 (限双色屏)</button>
        <button class="btn" onclick="triggerSync()">⚡ 从服务器拉取并刷屏</button>
        <button class="btn btn-warn" onclick="testPattern()">🎨 发送内置测试图案</button>
        <button class="btn btn-sec" onclick="testClear()">🧹 清除屏幕 (白屏)</button>
      </div>
    </div>
  </div>

  <!-- 选项卡 2: 蓝牙管理 -->
  <div id="tab-ble" class="tab-content" style="display:none;">
    <div class="card">
      <h2>📡 搜索并绑定墨水屏</h2>
      <p style="font-size:12px;color:var(--sub);margin-bottom:12px;">点击下方按钮搜索周边低功耗蓝牙设备（如 NRF_EPD_5AF9），点击即可绑定：</p>
      <button class="btn" id="btn-scan" onclick="startBleScan()">🔍 开始扫描周边蓝牙 (5秒)</button>
      <div id="ble-list" style="margin-top:16px;"></div>
    </div>
    <div class="card">
      <h2>🎛️ 墨水屏直控</h2>
      <div class="btn-group">
        <button class="btn btn-success" onclick="setCalendarMode()">📅 显示中国农历日历</button>
        <button class="btn btn-cyan" onclick="setClockMode()">⏰ 显示实时时钟 (限双色屏)</button>
        <button class="btn btn-warn" onclick="testPattern()">🎨 刷新测试图案</button>
        <button class="btn btn-sec" onclick="testClear()">🧹 墨水屏全白清屏</button>
      </div>
    </div>
  </div>

  <!-- 选项卡 3: 图像服务器与屏幕规格配置 -->
  <div id="tab-server" class="tab-content" style="display:none;">
    <div class="card">
      <h2>📺 墨水屏尺寸与型号规格</h2>
      <div class="form-group">
        <label>选择墨水屏预设规格</label>
        <select id="cfg-screen" onchange="onScreenChange()">
          <option value="4.2_bwr">4.2寸 三色 (400x300, 黑白红, 30000字节)</option>
          <option value="4.2_bw">4.2寸 黑白 (400x300, 15000字节)</option>
          <option value="2.9_bwr">2.9寸 三色 (296x128, 黑白红, 9472字节)</option>
          <option value="2.9_bw">2.9寸 黑白 (296x128, 4736字节)</option>
          <option value="2.13_bwr">2.13寸 三色 (250x122, 黑白红, 7626字节)</option>
          <option value="2.13_bw">2.13寸 黑白 (250x122, 3813字节)</option>
          <option value="5.83_bwr">5.83寸 三色 (648x480, 黑白红, 77760字节)</option>
          <option value="7.5_bwr">7.5寸 三色 (800x480, 黑白红, 96000字节)</option>
          <option value="7.5_bw">7.5寸 黑白 (800x480, 48000字节)</option>
          <option value="custom">自定义规格分辨率...</option>
        </select>
      </div>
      <div style="display:flex;gap:10px;">
        <div class="form-group" style="flex:1;">
          <label>分辨率 宽 (px)</label>
          <input type="number" id="cfg-width" value="400" onchange="updateExpectedSize()">
        </div>
        <div class="form-group" style="flex:1;">
          <label>分辨率 高 (px)</label>
          <input type="number" id="cfg-height" value="300" onchange="updateExpectedSize()">
        </div>
        <div class="form-group" style="flex:1;">
          <label>色彩深度</label>
          <select id="cfg-colors" onchange="updateExpectedSize()">
            <option value="3">三色 (黑白红)</option>
            <option value="2">黑白 (双色)</option>
          </select>
        </div>
      </div>
      <div id="screen-info" style="font-size:12px;color:#38bdf8;margin-bottom:8px;">单通道大小: 15000 字节 | HTTP拉取图片总数据大小: 30000 字节</div>
    </div>

    <div class="card">
      <h2>⚙️ HTTP 图片服务器与定时策略</h2>
      <div class="form-group">
        <label>服务器 URL (支持本地 IP 或域名 API)</label>
        <input type="text" id="cfg-url" placeholder="http://192.168.1.100:8000/screen.bin">
      </div>
      <div class="form-group">
        <label>认证 Header 名称 (默认 Authorization)</label>
        <input type="text" id="cfg-hdr" placeholder="Authorization">
      </div>
      <div class="form-group">
        <label>用户 Token / 密钥 (可选，支持多用户区分)</label>
        <input type="text" id="cfg-token" placeholder="Bearer eyJhbGciOi...">
      </div>
      <div class="form-group">
        <label>自动唤醒拉取频率</label>
        <select id="cfg-interval">
          <option value="0">关闭定时拉取 (仅手动刷新)</option>
          <option value="5">每 5 分钟</option>
          <option value="15">每 15 分钟</option>
          <option value="30">每 30 分钟</option>
          <option value="60">每 1 小时 (推荐)</option>
          <option value="120">每 2 小时</option>
          <option value="360">每 6 小时</option>
          <option value="720">每 12 小时</option>
          <option value="1440">每 24 小时</option>
        </select>
      </div>
      <div class="form-group">
        <label>mDNS 主机名 (局域网访问: http://&lt;主机名&gt;.local)</label>
        <input type="text" id="cfg-mdns" value="epd-gateway">
      </div>
      <button class="btn" onclick="saveServerConfig()">💾 保存配置</button>
    </div>
  </div>

  <!-- 选项卡 4: WiFi 设置 -->
  <div id="tab-wifi" class="tab-content" style="display:none;">
    <div class="card">
      <h2>📶 局域网 WiFi 配网</h2>
      <p style="font-size:12px;color:var(--sub);margin-bottom:12px;">输入路由器 2.4GHz WiFi 账号和密码，保存后设备将自动重启并连接路由器：</p>
      <div class="form-group">
        <label>WiFi 名称 (SSID)</label>
        <input type="text" id="wifi-ssid" placeholder="Home-WiFi-2.4G">
      </div>
      <div class="form-group">
        <label>WiFi 密码 (Password)</label>
        <input type="password" id="wifi-pass" placeholder="WiFi 密码">
      </div>
      <button class="btn" onclick="saveWifi()">🔗 保存并重启连接局域网</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const SCREEN_PRESETS = {
  '4.2_bwr':  {w:400, h:300, c:3, name:'4.2寸 三色 (400x300)'},
  '4.2_bw':   {w:400, h:300, c:2, name:'4.2寸 黑白 (400x300)'},
  '2.9_bwr':  {w:296, h:128, c:3, name:'2.9寸 三色 (296x128)'},
  '2.9_bw':   {w:296, h:128, c:2, name:'2.9寸 黑白 (296x128)'},
  '2.13_bwr': {w:250, h:122, c:3, name:'2.13寸 三色 (250x122)'},
  '2.13_bw':  {w:250, h:122, c:2, name:'2.13寸 黑白 (250x122)'},
  '5.83_bwr': {w:648, h:480, c:3, name:'5.83寸 三色 (648x480)'},
  '7.5_bwr':  {w:800, h:480, c:3, name:'7.5寸 三色 (800x480)'},
  '7.5_bw':   {w:800, h:480, c:2, name:'7.5寸 黑白 (800x480)'}
};

function onScreenChange(){
  const model = document.getElementById('cfg-screen').value;
  if(SCREEN_PRESETS[model]){
    const p = SCREEN_PRESETS[model];
    document.getElementById('cfg-width').value = p.w;
    document.getElementById('cfg-height').value = p.h;
    document.getElementById('cfg-colors').value = p.c;
  }
  updateExpectedSize();
}

function updateExpectedSize(){
  const w = parseInt(document.getElementById('cfg-width').value) || 400;
  const h = parseInt(document.getElementById('cfg-height').value) || 300;
  const c = parseInt(document.getElementById('cfg-colors').value) || 3;
  const bytesPerRow = Math.ceil(w / 8);
  const chSize = bytesPerRow * h;
  const total = (c >= 3) ? (chSize * 2) : chSize;
  document.getElementById('screen-info').innerText = 
    `单通道大小: ${chSize} 字节 | HTTP拉取图片总数据大小: ${total} 字节 (${c>=3?'双通道黑白+红':'单通道黑白'})`;
}

function switchTab(id){
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c=>c.style.display='none');
  event.target.classList.add('active');
  document.getElementById(id).style.display='block';
}

function loadStatus(){
  fetch('/api/status').then(r=>r.json()).then(d=>{
    document.getElementById('val-wifimode').innerText = d.ap_mode ? '热点配网 (AP: ' + d.ap_ssid + ')' : '局域网连接 (STA)';
    document.getElementById('val-ip').innerText = d.ip;
    document.getElementById('val-mdns').innerText = 'http://' + (d.mdns_host || 'epd-gateway') + '.local';
    document.getElementById('val-ble').innerText = d.ble_mac ? (d.ble_name + ' [' + d.ble_mac + ']') : '未绑定 (请去蓝牙墨水屏绑定)';
    document.getElementById('val-screen').innerText = (d.screen_width||400) + 'x' + (d.screen_height||300) + ' (' + (d.screen_colors===3?'三色黑白红':'双色黑白') + ')';
    document.getElementById('val-lastsync').innerText = d.last_sync || '从未';
    document.getElementById('val-laststat').innerText = d.last_stat || '空闲';
    document.getElementById('val-interval').innerText = (d.interval > 0) ? (d.interval + ' 分钟') : '已关闭 (仅手动)';

    document.getElementById('cfg-url').value = d.server_url || '';
    document.getElementById('cfg-hdr').value = d.token_header || 'Authorization';
    document.getElementById('cfg-token').value = d.auth_token || '';
    document.getElementById('cfg-interval').value = (d.interval !== undefined) ? d.interval : 60;
    document.getElementById('cfg-screen').value = d.screen_model || '4.2_bwr';
    document.getElementById('cfg-width').value = d.screen_width || 400;
    document.getElementById('cfg-height').value = d.screen_height || 300;
    document.getElementById('cfg-colors').value = d.screen_colors || 3;
    document.getElementById('cfg-mdns').value = d.mdns_host || 'epd-gateway';
    document.getElementById('wifi-ssid').value = d.ssid || '';
    updateExpectedSize();
  }).catch(()=>{});
}

function startBleScan(){
  const btn = document.getElementById('btn-scan');
  btn.disabled = true;
  btn.innerText = '🔍 正在搜索周边蓝牙中... (约5秒)';
  fetch('/api/ble/scan', {method:'POST'}).then(r=>r.json()).then(()=>{
    let timer = setInterval(()=>{
      fetch('/api/ble/results').then(r=>r.json()).then(res=>{
        if(!res.scanning){
          clearInterval(timer);
          btn.disabled = false;
          btn.innerText = '🔍 重新扫描周边蓝牙';
          renderBleList(res.devices);
        }
      });
    }, 1000);
  });
}

function renderBleList(devs){
  const el = document.getElementById('ble-list');
  el.replaceChildren();
  if(!devs || devs.length === 0){
    const empty = document.createElement('p');
    empty.style.cssText = 'color:var(--sub);font-size:13px;text-align:center;';
    empty.innerText = '未发现周边蓝牙设备，请确保墨水屏处于唤醒广播状态';
    el.appendChild(empty);
    return;
  }
  devs.forEach(d=>{
    const item = document.createElement('div');
    item.className = 'device-item';
    const info = document.createElement('div');
    const nameRow = document.createElement('div');
    nameRow.style.fontWeight = '600';
    const name = document.createElement('span');
    name.innerText = String(d.name || '未知设备');
    const badge = document.createElement('span');
    badge.className = 'badge ' + (d.is_epd ? 'badge-epd' : 'badge-other');
    badge.innerText = d.is_epd ? '墨水屏 (EPD)' : '其他设备';
    nameRow.append(name, document.createTextNode(' '), badge);
    const meta = document.createElement('div');
    meta.className = 'dev-meta';
    meta.innerText = 'MAC: ' + d.mac + ' | 信号: ' + d.rssi + ' dBm';
    info.append(nameRow, meta);
    const button = document.createElement('button');
    button.className = 'btn';
    button.style.cssText = 'width:auto;margin:0;padding:6px 14px;font-size:12px;';
    button.innerText = '绑定此设备';
    button.addEventListener('click', ()=>bindBle(d.mac, d.name));
    item.append(info, button);
    el.appendChild(item);
  });
}

function bindBle(mac, name){
  fetch('/api/ble/bind', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({mac:mac, name:name})
  }).then(r=>r.json()).then(res=>{
    showToast(res.msg);
    loadStatus();
  });
}

function setCalendarMode(){
  showToast('正在发送日历模式切换指令并同步本地时间戳...');
  const ts = Math.floor(Date.now() / 1000);
  const tz = -(new Date().getTimezoneOffset() / 60);
  fetch('/api/ble/calendar', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({timestamp: ts, timezone: tz})
  }).then(r=>r.json()).then(res=>{
    showToast(res.msg || (res.error ? ('错误: ' + res.error) : '指令已发送'));
    setTimeout(loadStatus, 2000);
  });
}

function setClockMode(){
  const sc = (document.getElementById('cfg-screen') ? document.getElementById('cfg-screen').value : '') || '';
  if(sc.indexOf('bwr') >= 0 || sc.indexOf('bwry') >= 0){
    if(!confirm('⚠️ 警告：当前配置为三色/四色墨水屏！\n三色墨水屏硬件不支持局刷，每次刷新需全屏反转15秒以上；而时钟模式每分钟都会全刷一次，频繁全刷会导致墨水屏死锁、触发看门狗复位并退回1970年日历！\n官方固件原作者明确注明三色屏请勿开启时钟模式。\n\n是否仍然强制尝试？')){
      return;
    }
  }
  showToast('正在发送时钟模式切换指令...');
  const ts = Math.floor(Date.now() / 1000);
  const tz = -(new Date().getTimezoneOffset() / 60);
  fetch('/api/ble/clock', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({timestamp: ts, timezone: tz})
  }).then(r=>r.json()).then(res=>{
    showToast(res.msg || (res.error ? ('错误: ' + res.error) : '指令已发送'));
    setTimeout(loadStatus, 2000);
  });
}

function triggerSync(){
  showToast('正在请求图片服务器并推送到墨水屏...');
  fetch('/api/trigger', {method:'POST'}).then(r=>r.json()).then(res=>{
    showToast(res.msg);
    setTimeout(loadStatus, 3000);
  });
}

function testPattern(){
  showToast('正在生成并向墨水屏发送当前规格测试图案...');
  fetch('/api/ble/test_pattern', {method:'POST'}).then(r=>r.json()).then(res=>{
    showToast(res.msg);
  });
}

function testClear(){
  showToast('正在向墨水屏发送清屏命令...');
  fetch('/api/ble/clear', {method:'POST'}).then(r=>r.json()).then(res=>{
    showToast(res.msg);
  });
}

function saveServerConfig(){
  const url = document.getElementById('cfg-url').value;
  const hdr = document.getElementById('cfg-hdr').value;
  const token = document.getElementById('cfg-token').value;
  const interval = parseInt(document.getElementById('cfg-interval').value);
  const scModel = document.getElementById('cfg-screen').value;
  const scW = parseInt(document.getElementById('cfg-width').value) || 400;
  const scH = parseInt(document.getElementById('cfg-height').value) || 300;
  const scC = parseInt(document.getElementById('cfg-colors').value) || 3;
  const mdns = document.getElementById('cfg-mdns').value || 'epd-gateway';

  fetch('/api/config', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      url: url, hdr: hdr, token: token, interval: interval,
      sc_model: scModel, sc_w: scW, sc_h: scH, sc_c: scC, mdns: mdns
    })
  }).then(r=>r.json()).then(res=>{
    showToast(res.msg);
    loadStatus();
  });
}

function saveWifi(){
  const ssid = document.getElementById('wifi-ssid').value.trim();
  const pass = document.getElementById('wifi-pass').value;
  if(!ssid){
    alert('请输入 WiFi 名称');
    return;
  }
  showToast('正在保存 WiFi 配置并重启连接局域网...');
  fetch('/api/wifi', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ssid: ssid, pass: pass})
  }).then(r=>r.json()).then(res=>{
    alert(res.msg || 'WiFi 已保存！设备将重启连入局域网。之后可在同局域网浏览器访问 http://epd-gateway.local');
  });
}

function showToast(msg){
  const t = document.getElementById('toast');
  t.innerText = msg;
  t.style.display = 'block';
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(()=>{t.style.display='none';}, 3500);
}

window.onload = function(){
  loadStatus();
};
</script>
</body>
</html>
)rawliteral";

static bool isValidMacAddress(const String& mac) {
    if (mac.length() != 17) return false;
    for (uint8_t i = 0; i < 17; i++) {
        char c = mac.charAt(i);
        if ((i + 1) % 3 == 0) {
            if (c != ':') return false;
        } else if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) {
            return false;
        }
    }
    return true;
}

WebPortal::WebPortal() : server(80) {}

WebPortal& WebPortal::getInstance() {
    static WebPortal instance;
    return instance;
}

void WebPortal::begin(bool isApMode) {
    this->inApMode = isApMode;

    if (inApMode) {
        dnsServer.setErrorReplyCode(DNSReplyCode::NoError);
        dnsServer.start(53, "*", WiFi.softAPIP());
    }

    setupRoutes();
    server.begin();
    Serial.printf("[Web] Web 管理服务器启动成功, 模式: %s\n", inApMode ? "AP" : "STA");
}

void WebPortal::handleClient() {
    if (inApMode) {
        dnsServer.processNextRequest();
    }
    server.handleClient();
}

void WebPortal::setTriggerCallback(std::function<void()> cb) {
    triggerCallback = cb;
}

void WebPortal::setupRoutes() {
    server.on("/", HTTP_GET, [this]() { handleRoot(); });
    server.on("/api/status", HTTP_GET, [this]() { handleApiStatus(); });
    server.on("/api/ble/scan", HTTP_POST, [this]() { handleApiBleScan(); });
    server.on("/api/ble/results", HTTP_GET, [this]() { handleApiBleResults(); });
    server.on("/api/ble/bind", HTTP_POST, [this]() { handleApiBleBind(); });
    server.on("/api/ble/clear", HTTP_POST, [this]() { handleApiBleClear(); });
    server.on("/api/ble/test_pattern", HTTP_POST, [this]() { handleApiBleTestPattern(); });
    server.on("/api/ble/calendar", HTTP_POST, [this]() { handleApiBleCalendar(); });
    server.on("/api/ble/clock", HTTP_POST, [this]() { handleApiBleClock(); });
    server.on("/api/config", HTTP_POST, [this]() { handleApiConfig(); });
    server.on("/api/wifi", HTTP_POST, [this]() { handleApiWifi(); });
    server.on("/api/trigger", HTTP_POST, [this]() { handleApiTrigger(); });

    // 适配 Captive Portal 强制门户
    server.onNotFound([this]() {
        if (inApMode) {
            server.sendHeader("Location", String("http://192.168.4.1/"), true);
            server.send(302, "text/plain", "");
        } else {
            server.send(404, "text/plain", "Not Found");
        }
    });
}

void WebPortal::handleRoot() {
    server.send_P(200, "text/html", PAGE_HTML);
}

void WebPortal::handleApiStatus() {
    AppConfig& cfg = ConfigManager::getInstance().config;
    String mac = WiFi.macAddress();
    mac.replace(":", "");
    String suffix = mac.substring(mac.length() > 4 ? mac.length() - 4 : 0);
    JsonDocument doc;
    doc["ap_mode"] = inApMode;
    doc["ap_ssid"] = String(DEFAULT_AP_SSID_PREFIX) + suffix;
    doc["ip"] = inApMode ? WiFi.softAPIP().toString() : WiFi.localIP().toString();
    doc["ssid"] = cfg.wifi_ssid;
    doc["ble_mac"] = cfg.ble_mac;
    doc["ble_name"] = cfg.ble_name;
    doc["server_url"] = cfg.server_url;
    doc["token_header"] = cfg.token_header;
    doc["auth_token"] = cfg.auth_token;
    doc["interval"] = cfg.refresh_interval;
    doc["last_sync"] = cfg.last_sync_time;
    doc["last_stat"] = cfg.last_sync_status;
    doc["screen_model"] = cfg.screen_model;
    doc["screen_width"] = cfg.screen_width;
    doc["screen_height"] = cfg.screen_height;
    doc["screen_colors"] = cfg.screen_colors;
    doc["mdns_host"] = cfg.mdns_host;

    String jsonStr;
    serializeJson(doc, jsonStr);
    server.send(200, "application/json", jsonStr);
}

void WebPortal::handleApiBleScan() {
    BleEpdClient::getInstance().startScan(BLE_DEFAULT_SCAN_SECONDS);
    server.send(200, "application/json", "{\"status\":\"started\"}");
}

void WebPortal::handleApiBleResults() {
    auto results = BleEpdClient::getInstance().getScanResults();
    bool scanning = BleEpdClient::getInstance().isScanning();

    JsonDocument doc;
    doc["scanning"] = scanning;
    JsonArray arr = doc["devices"].to<JsonArray>();

    for (const auto& dev : results) {
        JsonObject obj = arr.add<JsonObject>();
        obj["name"] = dev.name;
        obj["mac"] = dev.address;
        obj["rssi"] = dev.rssi;
        obj["is_epd"] = dev.isEpd;
    }

    String jsonStr;
    serializeJson(doc, jsonStr);
    server.send(200, "application/json", jsonStr);
}

void WebPortal::handleApiBleBind() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"error\":\"缺少数据\"}");
        return;
    }

    JsonDocument doc;
    if (deserializeJson(doc, server.arg("plain"))) {
        server.send(400, "application/json", "{\"error\":\"JSON 格式错误\"}");
        return;
    }
    String mac = doc["mac"].as<String>();
    String name = doc["name"].as<String>();
    mac.trim();
    name.trim();
    if (!isValidMacAddress(mac) || name.length() > 64) {
        server.send(400, "application/json", "{\"error\":\"MAC 地址或设备名称无效\"}");
        return;
    }

    AppConfig& cfg = ConfigManager::getInstance().config;
    if (cfg.ble_mac != mac) cfg.last_etag = "";
    cfg.ble_mac = mac;
    cfg.ble_name = name;
    ConfigManager::getInstance().save();

    server.send(200, "application/json", "{\"status\":\"ok\",\"msg\":\"绑定成功！\"}");
}

void WebPortal::handleApiBleClear() {
    AppConfig& cfg = ConfigManager::getInstance().config;
    if (cfg.ble_mac.length() == 0) {
        server.send(400, "application/json", "{\"error\":\"请先绑定墨水屏\"}");
        return;
    }

    bool ok = BleEpdClient::getInstance().clearScreen(cfg.ble_mac);
    if (ok) {
        cfg.last_etag = "";
        ConfigManager::getInstance().save();
        server.send(200, "application/json", "{\"status\":\"ok\",\"msg\":\"清屏指令已发送！墨水屏正在刷新\"}");
    } else {
        server.send(500, "application/json", "{\"error\":\"清屏失败，请检查蓝牙距离或墨水屏状态\"}");
    }
}

void WebPortal::handleApiBleTestPattern() {
    AppConfig& cfg = ConfigManager::getInstance().config;
    if (cfg.ble_mac.length() == 0) {
        server.send(400, "application/json", "{\"error\":\"请先绑定墨水屏\"}");
        return;
    }

    bool ok = BleEpdClient::getInstance().sendTestPattern(cfg.ble_mac, cfg.screen_width, cfg.screen_height, cfg.screen_colors);
    if (ok) {
        cfg.last_etag = "";
        ConfigManager::getInstance().save();
        server.send(200, "application/json", "{\"status\":\"ok\",\"msg\":\"测试画面已发送！墨水屏正在刷新\"}");
    } else {
        server.send(500, "application/json", "{\"error\":\"发送失败，请检查墨水屏连接\"}");
    }
}

void WebPortal::handleApiBleCalendar() {
    AppConfig& cfg = ConfigManager::getInstance().config;
    if (cfg.ble_mac.length() == 0) {
        server.send(400, "application/json", "{\"error\":\"请先绑定墨水屏\"}");
        return;
    }

    uint32_t ts = 0;
    int8_t tz = 8;
    if (server.hasArg("plain")) {
        JsonDocument doc;
        deserializeJson(doc, server.arg("plain"));
        if (doc["timestamp"].is<uint32_t>()) ts = doc["timestamp"].as<uint32_t>();
        if (doc["timezone"].is<int8_t>()) tz = doc["timezone"].as<int8_t>();
    }

    DisplayUI::getInstance().showToast("切换至日历模式...", 0x0596);
    bool ok = BleEpdClient::getInstance().setCalendarMode(cfg.ble_mac, ts, tz, [](int pct, const String& msg) {
        DisplayUI::getInstance().showProgress(pct, msg);
    });

    if (ok) {
        cfg.last_etag = "";
        cfg.last_sync_status = "已切至日历模式";
        ConfigManager::getInstance().save();
        server.send(200, "application/json", "{\"status\":\"ok\",\"msg\":\"日历模式已切换！时间已校准且墨水屏已完成全刷\"}");
    } else {
        server.send(500, "application/json", "{\"error\":\"日历模式切换失败，请检查墨水屏状态\"}");
    }
}

void WebPortal::handleApiBleClock() {
    AppConfig& cfg = ConfigManager::getInstance().config;
    if (cfg.ble_mac.length() == 0) {
        server.send(400, "application/json", "{\"error\":\"请先绑定墨水屏\"}");
        return;
    }

    uint32_t ts = 0;
    int8_t tz = 8;
    if (server.hasArg("plain")) {
        JsonDocument doc;
        deserializeJson(doc, server.arg("plain"));
        if (doc["timestamp"].is<uint32_t>()) ts = doc["timestamp"].as<uint32_t>();
        if (doc["timezone"].is<int8_t>()) tz = doc["timezone"].as<int8_t>();
    }

    DisplayUI::getInstance().showToast("切换至时钟模式...", 0x0284);
    bool ok = BleEpdClient::getInstance().setClockMode(cfg.ble_mac, ts, tz, [](int pct, const String& msg) {
        DisplayUI::getInstance().showProgress(pct, msg);
    });

    if (ok) {
        cfg.last_etag = "";
        cfg.last_sync_status = "已切至时钟模式";
        ConfigManager::getInstance().save();
        server.send(200, "application/json", "{\"status\":\"ok\",\"msg\":\"时钟模式已切换！时间已校准且墨水屏已完成全刷\"}");
    } else {
        server.send(500, "application/json", "{\"error\":\"时钟模式切换失败，请检查墨水屏状态\"}");
    }
}

void WebPortal::handleApiConfig() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"error\":\"缺少数据\"}");
        return;
    }

    JsonDocument doc;
    if (deserializeJson(doc, server.arg("plain"))) {
        server.send(400, "application/json", "{\"error\":\"JSON 格式错误\"}");
        return;
    }

    AppConfig& cfg = ConfigManager::getInstance().config;
    AppConfig newCfg = cfg;
    if (doc["url"].is<String>()) newCfg.server_url = doc["url"].as<String>();
    if (doc["hdr"].is<String>()) newCfg.token_header = doc["hdr"].as<String>();
    if (doc["token"].is<String>()) newCfg.auth_token = doc["token"].as<String>();
    if (doc["interval"].is<uint32_t>()) newCfg.refresh_interval = doc["interval"].as<uint32_t>();
    if (doc["sc_model"].is<String>()) newCfg.screen_model = doc["sc_model"].as<String>();
    if (doc["sc_w"].is<uint16_t>()) newCfg.screen_width = doc["sc_w"].as<uint16_t>();
    if (doc["sc_h"].is<uint16_t>()) newCfg.screen_height = doc["sc_h"].as<uint16_t>();
    if (doc["sc_c"].is<uint8_t>()) newCfg.screen_colors = doc["sc_c"].as<uint8_t>();
    if (doc["mdns"].is<String>()) newCfg.mdns_host = doc["mdns"].as<String>();

    size_t bytesPerRow = (newCfg.screen_width + 7UL) / 8UL;
    size_t frameLength = bytesPerRow * newCfg.screen_height * (newCfg.screen_colors >= 3 ? 2UL : 1UL);
    if (newCfg.refresh_interval > 10080 || newCfg.screen_width == 0 || newCfg.screen_height == 0 ||
        (newCfg.screen_colors != 2 && newCfg.screen_colors != 3) || frameLength > 200UL * 1024UL ||
        newCfg.server_url.length() > 512 || newCfg.token_header.length() > 64 || newCfg.auth_token.length() > 512) {
        server.send(400, "application/json", "{\"error\":\"配置值超出有效范围\"}");
        return;
    }
    if (newCfg.server_url != cfg.server_url || newCfg.auth_token != cfg.auth_token ||
        newCfg.token_header != cfg.token_header || newCfg.screen_model != cfg.screen_model ||
        newCfg.screen_width != cfg.screen_width || newCfg.screen_height != cfg.screen_height ||
        newCfg.screen_colors != cfg.screen_colors) {
        newCfg.last_etag = "";
    }
    cfg = newCfg;
    if (!ConfigManager::getInstance().save()) {
        server.send(500, "application/json", "{\"error\":\"配置写入失败\"}");
        return;
    }
    server.send(200, "application/json", "{\"status\":\"ok\",\"msg\":\"配置保存成功！\"}");
}

void WebPortal::handleApiWifi() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"error\":\"缺少数据\"}");
        return;
    }

    JsonDocument doc;
    if (deserializeJson(doc, server.arg("plain")) || !doc["ssid"].is<String>()) {
        server.send(400, "application/json", "{\"error\":\"WiFi 配置格式错误\"}");
        return;
    }

    AppConfig& cfg = ConfigManager::getInstance().config;
    String ssid = doc["ssid"].as<String>();
    String pass = doc["pass"].as<String>();
    if (ssid.length() == 0 || ssid.length() > 32 || pass.length() > 63) {
        server.send(400, "application/json", "{\"error\":\"WiFi SSID 或密码长度无效\"}");
        return;
    }
    cfg.wifi_ssid = ssid;
    cfg.wifi_pass = pass;
    if (!ConfigManager::getInstance().save()) {
        server.send(500, "application/json", "{\"error\":\"WiFi 配置写入失败\"}");
        return;
    }

    String msg = "WiFi 配置已保存，设备即将重启连接！你可以直接在浏览器打开 http://" + cfg.mdns_host + ".local 访问管理后台！";
    JsonDocument resp;
    resp["status"] = "ok";
    resp["msg"] = msg;
    String respStr;
    serializeJson(resp, respStr);
    server.send(200, "application/json", respStr);
    delay(1000);
    ESP.restart();
}

void WebPortal::handleApiTrigger() {
    if (triggerCallback) {
        triggerCallback();
        server.send(200, "application/json", "{\"status\":\"ok\",\"msg\":\"已触发刷新任务\"}");
    } else {
        server.send(500, "application/json", "{\"error\":\"触发器未初始化\"}");
    }
}
