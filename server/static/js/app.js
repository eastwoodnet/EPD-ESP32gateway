// EPD Backend Main Application Script
const WIDTH = 400;
const HEIGHT = 300;

let originalImage = null;
let currentProcessedBinary = null;

// 初始化
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initPhotoStudio();
  loadAlbumSlots();
  loadSchedule();
  loadMemoStatus();
  loadSettings();
  initMemoForm();
  initScheduleForm();
  initSettingsForm();

  // 定时刷新便签和状态 (每 10 秒)
  setInterval(() => {
    loadMemoStatus();
    loadScheduleOverview();
  }, 10000);
});

// ----------------- 标签页切换 -----------------
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");
    });
  });
}

// ----------------- 相册与图像调优 (Photo Studio) -----------------
function initPhotoStudio() {
  const fileInput = document.getElementById("imageFileInput");
  const canvas = document.getElementById("previewCanvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");

  // 默认画个白底和提示
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  ctx.fillStyle = "#888888";
  ctx.font = "14px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("请在下方选择图片上传调优 (400x300)", WIDTH / 2, HEIGHT / 2);

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const img = new Image();
      img.onload = () => {
        originalImage = img;
        renderCanvas();
      };
      img.src = event.target.result;
    };
    reader.readAsDataURL(file);
  });

  // 滑块与下拉框事件
  const contrastInput = document.getElementById("contrastRange");
  const strengthInput = document.getElementById("strengthRange");
  const algSelect = document.getElementById("algSelect");

  contrastInput.addEventListener("input", (e) => {
    document.getElementById("contrastVal").textContent = e.target.value;
    renderCanvas();
  });

  strengthInput.addEventListener("input", (e) => {
    document.getElementById("strengthVal").textContent = e.target.value;
    renderCanvas();
  });

  algSelect.addEventListener("change", renderCanvas);
}

function renderCanvas() {
  if (!originalImage) return;

  const canvas = document.getElementById("previewCanvas");
  const ctx = canvas.getContext("2d");

  // 1. 等比居中缩放裁剪至 400x300
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  const imgRatio = originalImage.width / originalImage.height;
  const canvasRatio = WIDTH / HEIGHT;

  let sWidth, sHeight, sx, sy;
  if (imgRatio > canvasRatio) {
    sHeight = originalImage.height;
    sWidth = sHeight * canvasRatio;
    sx = (originalImage.width - sWidth) / 2;
    sy = 0;
  } else {
    sWidth = originalImage.width;
    sHeight = sWidth / canvasRatio;
    sx = 0;
    sy = (originalImage.height - sHeight) / 2;
  }

  ctx.drawImage(originalImage, sx, sy, sWidth, sHeight, 0, 0, WIDTH, HEIGHT);

  // 2. 获取 ImageData 并应用对比度调节
  let imgData = ctx.getImageData(0, 0, WIDTH, HEIGHT);
  const contrast = parseFloat(document.getElementById("contrastRange").value) || 1.0;
  imgData = adjustContrast(imgData, contrast);

  // 3. 执行抖动算法 (Floyd-Steinberg / Atkinson)
  const alg = document.getElementById("algSelect").value;
  const strength = parseFloat(document.getElementById("strengthRange").value) || 1.0;

  if (alg === "floydSteinberg") {
    imgData = floydSteinbergDither(imgData, strength);
  } else if (alg === "atkinson") {
    imgData = atkinsonDither(imgData, strength);
  }

  // 4. 将抖动后的三色效果放回 Canvas 预览
  ctx.putImageData(imgData, 0, 0);

  // 5. 生成 30,000 字节二进制数据准备保存
  currentProcessedBinary = processImageDataToBinary(imgData);
  document.getElementById("saveSlotButtons").style.display = "flex";
}

async function saveCurrentToSlot(slotId) {
  if (!currentProcessedBinary || currentProcessedBinary.length !== 30000) {
    alert("请先选择图片并调优后再保存！");
    return;
  }

  try {
    const res = await fetch(`/api/album/slot/${slotId}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: currentProcessedBinary
    });
    const data = await res.json();
    if (res.ok) {
      alert(`已成功保存到卡槽 ${slotId}！`);
      loadAlbumSlots();
    } else {
      alert(`保存失败: ${data.detail || data.message}`);
    }
  } catch (err) {
    alert(`网络错误: ${err.message}`);
  }
}

async function loadAlbumSlots() {
  try {
    const res = await fetch("/api/album/slots");
    const data = await res.json();
    const container = document.getElementById("slotsContainer");
    container.innerHTML = "";

    data.slots.forEach(slot => {
      const card = document.createElement("div");
      card.className = `slot-card ${slot.exists ? "" : "empty"}`;

      if (slot.exists) {
        card.innerHTML = `
          <div class="slot-badge">卡槽 ${slot.id}</div>
          <img src="${slot.preview_url}?t=${Date.now()}" class="slot-thumb" alt="Slot ${slot.id}">
          <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">
            更新: ${slot.updated_at.slice(11, 16)} (${(slot.size / 1024).toFixed(0)}KB)
          </div>
          <div style="display: flex; gap: 6px; justify-content: center;">
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 12px;" onclick="saveCurrentToSlot(${slot.id})">覆盖</button>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 12px; color: #ef4444;" onclick="deleteSlot(${slot.id})">清空</button>
          </div>
        `;
      } else {
        card.innerHTML = `
          <div class="slot-badge">卡槽 ${slot.id} (空)</div>
          <div class="slot-empty-box">
            <span style="font-size: 24px; margin-bottom: 4px;">🖼️</span>
            <span>待上传</span>
          </div>
          <button class="btn btn-primary" style="padding: 6px 12px; font-size: 12px; width: 100%;" onclick="saveCurrentToSlot(${slot.id})">存入当前图片</button>
        `;
      }
      container.appendChild(card);
    });
  } catch (err) {
    console.error("加载卡槽失败:", err);
  }
}

async function deleteSlot(slotId) {
  if (!confirm(`确定清空卡槽 ${slotId} 吗？`)) return;
  try {
    const res = await fetch(`/api/album/slot/${slotId}`, { method: "DELETE" });
    if (res.ok) {
      loadAlbumSlots();
    }
  } catch (err) {
    alert("删除失败: " + err.message);
  }
}

// ----------------- 24小时自由排程 (Schedule) -----------------
let currentScheduleConfig = null;

async function loadSchedule() {
  try {
    const res = await fetch("/api/schedule");
    const data = await res.json();
    currentScheduleConfig = data.config;
    renderTimelineBar(data.config.rules);
    renderRuleList(data.config.rules);
    document.getElementById("fallbackModeSelect").value = data.config.fallback_mode || "photo_album";

    // 状态条展示
    const modeName = getModeLabel(data.active_mode);
    document.getElementById("activeModeBadge").textContent = `当前生效: ${modeName}`;
    document.getElementById("nextPullBadge").textContent = `下次刷新约 ${Math.round(data.next_pull_sec / 60)} 分钟后`;
  } catch (err) {
    console.error("加载排程配置失败:", err);
  }
}

function getModeLabel(mode) {
  const map = {
    photo_album: "🖼️ 相册轮播",
    calendar_todo: "📅 日程待办",
    weather_date: "⛅ 天气日期",
    clock: "🕒 极简时钟",
    sleep_dnd: "🌙 夜间休眠免打扰"
  };
  return map[mode] || mode;
}

function getModeColor(mode) {
  const map = {
    photo_album: "#3b82f6",   // 蓝色
    calendar_todo: "#10b981", // 绿色
    weather_date: "#f59e0b",  // 橙色
    clock: "#8b5cf6",         // 紫色
    sleep_dnd: "#334155"      // 暗灰
  };
  return map[mode] || "#64748b";
}

function parseTimeToMinutes(hm) {
  const [h, m] = hm.split(":").map(Number);
  return h * 60 + m;
}

function renderTimelineBar(rules) {
  const bar = document.getElementById("timelineBar");
  bar.innerHTML = "";

  // 简单离散为 24 小时 (1440分钟)
  const minutes = new Array(1440).fill(null);

  rules.forEach(rule => {
    let startMin = parseTimeToMinutes(rule.start);
    let endMin = parseTimeToMinutes(rule.end);
    if (startMin <= endMin) {
      for (let m = startMin; m < endMin; m++) minutes[m] = rule;
    } else {
      // 跨午夜
      for (let m = startMin; m < 1440; m++) minutes[m] = rule;
      for (let m = 0; m < endMin; m++) minutes[m] = rule;
    }
  });

  // 聚合连续段
  let segments = [];
  let curRule = minutes[0];
  let curCount = 0;

  for (let m = 0; m < 1440; m++) {
    if (minutes[m] === curRule) {
      curCount++;
    } else {
      segments.push({ rule: curRule, duration: curCount });
      curRule = minutes[m];
      curCount = 1;
    }
  }
  if (curCount > 0) {
    segments.push({ rule: curRule, duration: curCount });
  }

  segments.forEach(seg => {
    const el = document.createElement("div");
    el.className = "timeline-segment";
    el.style.width = `${(seg.duration / 1440) * 100}%`;
    if (seg.rule) {
      el.style.backgroundColor = getModeColor(seg.rule.mode);
      el.title = `${seg.rule.name} (${seg.rule.start} - ${seg.rule.end})`;
      el.textContent = seg.duration >= 90 ? seg.rule.name : "";
    } else {
      el.style.backgroundColor = "transparent";
      el.title = "未设定时段 (执行兜底模式)";
    }
    bar.appendChild(el);
  });
}

function renderRuleList(rules) {
  const container = document.getElementById("ruleListContainer");
  container.innerHTML = "";

  if (rules.length === 0) {
    container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">暂无排程规则，将全天执行兜底模式</div>`;
    return;
  }

  rules.forEach((rule, index) => {
    const item = document.createElement("div");
    item.className = "rule-item";
    item.innerHTML = `
      <div class="rule-info">
        <span class="rule-time">${rule.start} ~ ${rule.end}</span>
        <div>
          <div style="font-weight: 600;">${rule.name}</div>
          <span class="rule-mode-tag" style="border-left: 3px solid ${getModeColor(rule.mode)}">
            ${getModeLabel(rule.mode)}
          </span>
          ${rule.mode === 'photo_album' ? `<span style="font-size: 11px; color: var(--text-muted); margin-left: 6px;">(每${rule.config.rotate_interval_min || 60}分钟换图)</span>` : ''}
        </div>
      </div>
      <div>
        <button class="btn btn-outline" style="padding: 4px 10px; font-size: 12px; color: #ef4444;" onclick="deleteRule(${index})">删除</button>
      </div>
    `;
    container.appendChild(item);
  });
}

function initScheduleForm() {
  document.getElementById("addRuleBtn").addEventListener("click", () => {
    const name = document.getElementById("newRuleName").value.trim() || "自定义时段";
    const start = document.getElementById("newRuleStart").value;
    const end = document.getElementById("newRuleEnd").value;
    const mode = document.getElementById("newRuleMode").value;
    const rotateMin = parseInt(document.getElementById("newRuleRotateMin").value) || 60;

    if (!start || !end) {
      alert("请填写完整的开始时间和结束时间！");
      return;
    }

    const newRule = {
      id: "rule_" + Date.now(),
      name: name,
      start: start,
      end: end,
      mode: mode,
      config: mode === "photo_album" ? { rotate_interval_min: rotateMin } : {}
    };

    currentScheduleConfig.rules.push(newRule);
    saveScheduleConfig();
  });

  document.getElementById("fallbackModeSelect").addEventListener("change", (e) => {
    if (currentScheduleConfig) {
      currentScheduleConfig.fallback_mode = e.target.value;
      saveScheduleConfig();
    }
  });

  // 时段类型切换时联动展示相册轮播间隔
  document.getElementById("newRuleMode").addEventListener("change", (e) => {
    const rotateGroup = document.getElementById("rotateIntervalGroup");
    rotateGroup.style.display = e.target.value === "photo_album" ? "block" : "none";
  });
}

async function deleteRule(index) {
  if (!confirm("确定删除此时段规则吗？")) return;
  currentScheduleConfig.rules.splice(index, 1);
  saveScheduleConfig();
}

async function saveScheduleConfig() {
  try {
    const res = await fetch("/api/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentScheduleConfig)
    });
    if (res.ok) {
      loadSchedule();
    } else {
      alert("保存排程失败");
    }
  } catch (err) {
    alert("网络错误: " + err.message);
  }
}

// ----------------- 即时便签推送 (Memo) -----------------
function initMemoForm() {
  const form = document.getElementById("memoPushForm");
  const durationSlider = document.getElementById("memoDurationSlider");
  const durationVal = document.getElementById("memoDurationVal");

  durationSlider.addEventListener("input", (e) => {
    durationVal.textContent = e.target.value;
  });

  // 快捷预设按钮
  document.querySelectorAll(".duration-preset").forEach(btn => {
    btn.addEventListener("click", () => {
      const min = parseInt(btn.getAttribute("data-min"));
      durationSlider.value = min;
      durationVal.textContent = min;
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("memoTitleInput").value.trim() || "📌 桌面备忘提醒";
    const text = document.getElementById("memoTextInput").value.trim();
    const duration = parseInt(durationSlider.value) || 120;

    if (!text) {
      alert("请输入便签内容！");
      return;
    }

    try {
      const res = await fetch("/api/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title,
          text: text,
          duration_min: duration,
          sender: "Web后台"
        })
      });
      const data = await res.json();
      if (res.ok) {
        alert("便签已推送，已向 ESP32 网关发送即时刷新指令！");
        document.getElementById("memoTextInput").value = "";
        loadMemoStatus();
      } else {
        alert("推送失败: " + data.detail);
      }
    } catch (err) {
      alert("网络错误: " + err.message);
    }
  });

  document.getElementById("clearMemoBtn").addEventListener("click", async () => {
    if (!confirm("确定撤回当前即时便签吗？")) return;
    try {
      const res = await fetch("/api/push", { method: "DELETE" });
      if (res.ok) {
        alert("便签已清除，已通知网关恢复常规排程！");
        loadMemoStatus();
      }
    } catch (err) {
      alert("清除失败: " + err.message);
    }
  });
}

async function loadMemoStatus() {
  try {
    const res = await fetch("/api/memo/status");
    const memo = await res.json();
    const card = document.getElementById("activeMemoCard");

    if (memo.active) {
      card.style.display = "block";
      document.getElementById("activeMemoTitle").textContent = memo.title;
      document.getElementById("activeMemoText").textContent = memo.text;

      const remainMin = Math.max(0, Math.round((memo.expire_at - Date.now() / 1000) / 60));
      document.getElementById("activeMemoExpire").textContent = `剩余展示约 ${remainMin} 分钟 (发布者: ${memo.sender})`;
    } else {
      card.style.display = "none";
    }
  } catch (err) {
    console.error("获取便签状态失败:", err);
  }
}

// ----------------- 系统设置与测试 -----------------
function initSettingsForm() {
  document.getElementById("settingsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const gatewayUrl = document.getElementById("gatewayUrlInput").value.trim();
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gateway_url: gatewayUrl })
      });
      if (res.ok) {
        alert("系统设置保存成功！");
      }
    } catch (err) {
      alert("保存失败: " + err.message);
    }
  });

  document.getElementById("testGatewayBtn").addEventListener("click", async () => {
    const btn = document.getElementById("testGatewayBtn");
    btn.disabled = true;
    btn.textContent = "正在通知网关...";
    try {
      const res = await fetch("/api/trigger", { method: "POST" });
      const data = await res.json();
      alert(data.message);
    } catch (err) {
      alert("触发失败: " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "立即触发网关同步 (测试刷新)";
    }
  });
}

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    document.getElementById("gatewayUrlInput").value = data.gateway_url || "http://192.168.1.118";
  } catch (err) {
    console.error("加载系统设置失败:", err);
  }
}
