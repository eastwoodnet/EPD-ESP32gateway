// EPD Backend Main Application Script
const WIDTH = 400;
const HEIGHT = 300;
const MAX_IMAGE_FILE_BYTES = 10 * 1024 * 1024;
const MAX_IMAGE_PIXELS = 24000000;
const SUPPORTED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

let originalImage = null;
let currentProcessedBinary = null;
let imageSelectionVersion = 0;
let activeImageReader = null;
let albumSlotsRequestVersion = 0;
let memoStatusRequestVersion = 0;

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

function formatApiError(data, status) {
  let detail = data && (data.detail || data.message);
  if (Array.isArray(detail)) {
    detail = detail.map(item => {
      if (typeof item === "string") return item;
      if (item && typeof item.msg === "string") return item.msg;
      return JSON.stringify(item);
    }).join("; ");
  } else if (detail && typeof detail === "object") {
    detail = JSON.stringify(detail);
  }
  return detail || `HTTP ${status}`;
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  let data;
  try {
    data = await res.json();
  } catch (err) {
    throw new Error(res.ok ? "服务器返回了无效 JSON" : `请求失败 (HTTP ${res.status})`);
  }
  if (!res.ok) {
    throw new Error(formatApiError(data, res.status));
  }
  return data;
}

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

  fileInput.addEventListener("change", async (e) => {
    const selectionVersion = ++imageSelectionVersion;
    originalImage = null;
    currentProcessedBinary = null;
    document.getElementById("saveSlotButtons").style.display = "none";

    if (activeImageReader) {
      activeImageReader.abort();
      activeImageReader = null;
    }

    const file = e.target.files[0];
    if (!file) return;

    try {
      await validateImageFile(file);
      if (selectionVersion !== imageSelectionVersion) return;

      const dataUrl = await readImageAsDataUrl(file);
      if (selectionVersion !== imageSelectionVersion) return;

      const img = await decodeImage(dataUrl);
      if (selectionVersion !== imageSelectionVersion) return;

      const pixels = img.naturalWidth * img.naturalHeight;
      if (!img.naturalWidth || !img.naturalHeight || pixels > MAX_IMAGE_PIXELS) {
        throw new Error(`图片像素尺寸无效或超过 ${MAX_IMAGE_PIXELS / 1000000} 百万像素上限`);
      }

      originalImage = img;
      renderCanvas();
    } catch (err) {
      if (selectionVersion !== imageSelectionVersion || err.name === "AbortError") return;
      originalImage = null;
      currentProcessedBinary = null;
      document.getElementById("saveSlotButtons").style.display = "none";
      fileInput.value = "";
      alert(`图片加载失败: ${err.message}`);
    }
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

async function validateImageFile(file) {
  if (!file.size) {
    throw new Error("图片文件为空");
  }
  if (file.size > MAX_IMAGE_FILE_BYTES) {
    throw new Error("图片文件不能超过 10 MiB");
  }
  if (file.type && !SUPPORTED_IMAGE_TYPES.has(file.type.toLowerCase())) {
    throw new Error("仅支持 PNG、JPG 和 WebP 图片");
  }

  const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const isPng = header.length >= 8 &&
    header[0] === 0x89 && header[1] === 0x50 && header[2] === 0x4E && header[3] === 0x47 &&
    header[4] === 0x0D && header[5] === 0x0A && header[6] === 0x1A && header[7] === 0x0A;
  const isJpeg = header.length >= 3 && header[0] === 0xFF && header[1] === 0xD8 && header[2] === 0xFF;
  const isWebp = header.length >= 12 &&
    header[0] === 0x52 && header[1] === 0x49 && header[2] === 0x46 && header[3] === 0x46 &&
    header[8] === 0x57 && header[9] === 0x45 && header[10] === 0x42 && header[11] === 0x50;

  if (!isPng && !isJpeg && !isWebp) {
    throw new Error("文件内容不是有效的 PNG、JPG 或 WebP 图片");
  }
}

function readImageAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    activeImageReader = reader;
    reader.onload = () => {
      if (activeImageReader === reader) activeImageReader = null;
      resolve(reader.result);
    };
    reader.onerror = () => {
      if (activeImageReader === reader) activeImageReader = null;
      reject(reader.error || new Error("读取图片文件失败"));
    };
    reader.onabort = () => {
      if (activeImageReader === reader) activeImageReader = null;
      reject(new DOMException("图片读取已取消", "AbortError"));
    };
    reader.readAsDataURL(file);
  });
}

function decodeImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("图片解码失败，请换一张有效图片"));
    img.src = dataUrl;
  });
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
  } else if (typeof thresholdDither === "function") {
    imgData = thresholdDither(imgData);
  }

  // 4. 将抖动后的三色效果放回 Canvas 预览
  ctx.putImageData(imgData, 0, 0);

  // 5. 生成 30,000 字节二进制数据准备保存
  currentProcessedBinary = processImageDataToBinary(imgData);
  document.getElementById("saveSlotButtons").style.display = "flex";
}

async function saveCurrentToSlot(slotId) {
  if (!originalImage || !currentProcessedBinary || currentProcessedBinary.length !== 30000) {
    alert("请先选择图片并调优后再保存！");
    return;
  }

  albumSlotsRequestVersion++;
  try {
    await requestJson(`/api/album/slot/${slotId}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: currentProcessedBinary
    });
    alert(`已成功保存到卡槽 ${slotId}！`);
    await loadAlbumSlots();
  } catch (err) {
    alert(`保存失败: ${err.message}`);
  }
}

function createSlotButton(label, slotId, handler, primary = false) {
  const button = document.createElement("button");
  button.className = primary ? "btn btn-primary" : "btn btn-outline";
  button.style.padding = primary ? "6px 12px" : "4px 8px";
  button.style.fontSize = "12px";
  button.textContent = label;
  button.addEventListener("click", () => handler(slotId));
  return button;
}

function renderAlbumSlots(slots) {
  if (!Array.isArray(slots)) {
    throw new Error("卡槽响应格式无效");
  }

  const fragment = document.createDocumentFragment();
  const cacheBuster = Date.now().toString();

  slots.forEach(slot => {
    if (!slot || typeof slot.exists !== "boolean") {
      throw new Error("卡槽响应格式无效");
    }
    const slotId = Number(slot.id);
    if (!Number.isInteger(slotId) || slotId < 1) {
      throw new Error("卡槽 ID 无效");
    }

    const card = document.createElement("div");
    card.classList.add("slot-card");
    if (!slot.exists) card.classList.add("empty");

    const badge = document.createElement("div");
    badge.className = "slot-badge";
    badge.textContent = `卡槽 ${slotId}${slot.exists ? "" : " (空)"}`;
    card.appendChild(badge);

    if (slot.exists) {
      if (typeof slot.preview_url !== "string") {
        throw new Error("卡槽预览地址无效");
      }
      const previewUrl = new URL(slot.preview_url, window.location.origin);
      if (previewUrl.origin !== window.location.origin) {
        throw new Error("卡槽预览地址必须同源");
      }
      previewUrl.searchParams.set("t", cacheBuster);

      const image = document.createElement("img");
      image.src = previewUrl.href;
      image.className = "slot-thumb";
      image.alt = `Slot ${slotId}`;

      const updated = document.createElement("div");
      updated.style.fontSize = "11px";
      updated.style.color = "var(--text-muted)";
      updated.style.marginBottom = "8px";
      const updatedAt = typeof slot.updated_at === "string" ? slot.updated_at : "";
      const size = Number(slot.size);
      const sizeLabel = Number.isFinite(size) ? `${(size / 1024).toFixed(0)}KB` : "--";
      updated.textContent = `更新: ${updatedAt ? updatedAt.slice(11, 16) : "--"} (${sizeLabel})`;

      const actions = document.createElement("div");
      actions.style.display = "flex";
      actions.style.gap = "6px";
      actions.style.justifyContent = "center";
      actions.appendChild(createSlotButton("覆盖", slotId, saveCurrentToSlot));
      const deleteButton = createSlotButton("清空", slotId, deleteSlot);
      deleteButton.style.color = "#ef4444";
      actions.appendChild(deleteButton);

      card.append(image, updated, actions);
    } else {
      const emptyBox = document.createElement("div");
      emptyBox.className = "slot-empty-box";
      const icon = document.createElement("span");
      icon.style.fontSize = "24px";
      icon.style.marginBottom = "4px";
      icon.textContent = "\u{1F5BC}\uFE0F";
      const label = document.createElement("span");
      label.textContent = "待上传";
      emptyBox.append(icon, label);

      const saveButton = createSlotButton("存入当前图片", slotId, saveCurrentToSlot, true);
      saveButton.style.width = "100%";
      card.append(emptyBox, saveButton);
    }

    fragment.appendChild(card);
  });

  document.getElementById("slotsContainer").replaceChildren(fragment);
}

async function loadAlbumSlots() {
  const requestVersion = ++albumSlotsRequestVersion;
  try {
    const data = await requestJson("/api/album/slots");
    if (requestVersion !== albumSlotsRequestVersion) return;
    renderAlbumSlots(data.slots);
  } catch (err) {
    if (requestVersion !== albumSlotsRequestVersion) return;
    console.error("加载卡槽失败:", err);
    const error = document.createElement("div");
    error.style.gridColumn = "1 / -1";
    error.textContent = `卡槽加载失败: ${err.message}`;
    document.getElementById("slotsContainer").replaceChildren(error);
  }
}

async function deleteSlot(slotId) {
  if (!confirm(`确定清空卡槽 ${slotId} 吗？`)) return;
  albumSlotsRequestVersion++;
  try {
    await requestJson(`/api/album/slot/${slotId}`, { method: "DELETE" });
    await loadAlbumSlots();
  } catch (err) {
    alert(`删除失败: ${err.message}`);
  }
}

// ----------------- 24小时自由排程 (Schedule) -----------------
let currentScheduleConfig = null;
let scheduleBusy = false;
let scheduleConfigRequestVersion = 0;
let scheduleStatusRequestVersion = 0;

function validateScheduleResponse(data) {
  if (!data || !data.config || !Array.isArray(data.config.rules) || typeof data.active_mode !== "string") {
    throw new Error("排程响应格式无效");
  }
  return data;
}

function renderScheduleOverview(data) {
  const modeName = getModeLabel(data.active_mode);
  const nextPullSec = Number(data.next_pull_sec);
  document.getElementById("activeModeBadge").textContent = `当前生效: ${modeName}`;
  document.getElementById("nextPullBadge").textContent = Number.isFinite(nextPullSec)
    ? `下次刷新约 ${Math.round(nextPullSec / 60)} 分钟后`
    : "下次刷新: --";
}

function updateScheduleControls() {
  const disabled = scheduleBusy || !currentScheduleConfig;
  const addBtn = document.getElementById("addRuleBtn");
  if (addBtn) addBtn.disabled = disabled;
  const fallbackSelect = document.getElementById("fallbackModeSelect");
  if (fallbackSelect) fallbackSelect.disabled = disabled;
  const sortBtn = document.getElementById("sortRulesBtn");
  if (sortBtn) {
    sortBtn.disabled = disabled || !currentScheduleConfig || currentScheduleConfig.rules.length <= 1;
  }
  if (typeof document.querySelectorAll === "function") {
    document.querySelectorAll("#ruleListContainer button").forEach(button => {
      button.disabled = disabled || (button.dataset && button.dataset.edgeDisabled === "true");
    });
  }
}

async function loadSchedule() {
  const requestVersion = ++scheduleConfigRequestVersion;
  const statusRequestVersion = ++scheduleStatusRequestVersion;
  scheduleBusy = true;
  updateScheduleControls();

  try {
    const data = validateScheduleResponse(await requestJson("/api/schedule"));
    if (requestVersion !== scheduleConfigRequestVersion) return false;

    currentScheduleConfig = data.config;
    renderTimelineBar(data.config.rules);
    renderRuleList(data.config.rules);
    document.getElementById("fallbackModeSelect").value = data.config.fallback_mode || "photo_album";
    updateNewRuleHint();
    if (statusRequestVersion === scheduleStatusRequestVersion) {
      renderScheduleOverview(data);
    }
    return true;
  } catch (err) {
    if (requestVersion !== scheduleConfigRequestVersion) return false;
    console.error("加载排程配置失败:", err);
    if (statusRequestVersion === scheduleStatusRequestVersion) {
      document.getElementById("activeModeBadge").textContent = "排程加载失败";
      document.getElementById("nextPullBadge").textContent = "请检查服务状态";
    }
    if (!currentScheduleConfig) {
      const error = document.createElement("div");
      error.style.padding = "20px";
      error.style.color = "var(--text-muted)";
      error.textContent = `排程加载失败: ${err.message}`;
      document.getElementById("ruleListContainer").replaceChildren(error);
    }
    return false;
  } finally {
    if (requestVersion === scheduleConfigRequestVersion) {
      scheduleBusy = false;
      updateScheduleControls();
    }
  }
}

async function loadScheduleOverview() {
  const statusRequestVersion = ++scheduleStatusRequestVersion;
  try {
    const data = validateScheduleResponse(await requestJson("/api/schedule"));
    if (statusRequestVersion !== scheduleStatusRequestVersion) return;
    renderScheduleOverview(data);
  } catch (err) {
    if (statusRequestVersion !== scheduleStatusRequestVersion) return;
    console.error("刷新排程状态失败:", err);
    document.getElementById("activeModeBadge").textContent = "排程状态刷新失败";
    document.getElementById("nextPullBadge").textContent = "请检查服务状态";
  }
}

function getModeLabel(mode) {
  const map = {
    photo_album: "🖼️ 相册轮播",
    calendar_todo: "📅 今日日程看板",
    weather_date: "⛅ 天气与日期",
    clock: "📆 硬件原生万年历",
    sleep_dnd: "🌙 免打扰休眠"
  };
  return map[mode] || mode;
}

function getModeColor(mode) {
  const map = {
    photo_album: "#3b82f6",   // 蓝色
    calendar_todo: "#10b981", // 绿色
    weather_date: "#f59e0b",  // 橙色
    clock: "#8b5cf6",         // 紫色
    sleep_dnd: "#64748b"      // 板岩灰
  };
  return map[mode] || "#64748b";
}

function formatMinutesToTime(m) {
  const h = String(Math.floor(m / 60)).padStart(2, "0");
  const min = String(m % 60).padStart(2, "0");
  return `${h}:${min}`;
}

function parseTimeToMinutes(hm) {
  if (typeof hm !== "string") return null;
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(hm);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

function getRuleMinutes(rule) {
  const start = parseTimeToMinutes(rule.start);
  const end = parseTimeToMinutes(rule.end);
  if (start === null || end === null || start === end) return [];
  const mins = [];
  if (start < end) {
    for (let m = start; m < end; m++) mins.push(m);
  } else {
    // 跨午夜
    for (let m = start; m < 1440; m++) mins.push(m);
    for (let m = 0; m < end; m++) mins.push(m);
  }
  return mins;
}

function sortRulesSmart(rules) {
  if (!Array.isArray(rules) || rules.length <= 1) return rules;
  const n = rules.length;
  const meta = rules.map((rule, idx) => {
    const mins = getRuleMinutes(rule);
    return {
      rule,
      idx,
      start: parseTimeToMinutes(rule.start) ?? 0,
      dur: mins.length || 1440,
      minSet: new Set(mins)
    };
  });

  // 构建优先级有向无环图 (DAG):
  // 当两个时段存在时间重叠时，持续时间更短（更精细的子时段）必须排在更宽泛的长时段前面，避免被吞没；
  // 若重叠且时长完全一致，则保持原有相对先后顺序。
  const adj = Array.from({ length: n }, () => []);
  const inDegree = new Array(n).fill(0);

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      let overlaps = false;
      for (const m of meta[i].minSet) {
        if (meta[j].minSet.has(m)) {
          overlaps = true;
          break;
        }
      }
      if (!overlaps) continue;

      if (meta[i].dur < meta[j].dur || (meta[i].dur === meta[j].dur && meta[i].idx < meta[j].idx)) {
        adj[i].push(j);
        inDegree[j]++;
      } else {
        adj[j].push(i);
        inDegree[i]++;
      }
    }
  }

  const visited = new Array(n).fill(false);
  const result = [];
  for (let step = 0; step < n; step++) {
    let best = -1;
    for (let i = 0; i < n; i++) {
      if (visited[i] || inDegree[i] > 0) continue;
      if (
        best === -1 ||
        meta[i].start < meta[best].start ||
        (meta[i].start === meta[best].start && meta[i].dur < meta[best].dur) ||
        (meta[i].start === meta[best].start && meta[i].dur === meta[best].dur && meta[i].idx < meta[best].idx)
      ) {
        best = i;
      }
    }
    if (best === -1) break;
    visited[best] = true;
    result.push(meta[best].rule);
    for (const next of adj[best]) {
      inDegree[next]--;
    }
  }

  return result.length === n ? result : rules;
}

function analyzeRuleConflicts(rules) {
  // claimedBy[minute] = index of the earliest rule that claimed this minute
  const claimedBy = new Array(1440).fill(null);
  const results = [];

  rules.forEach((rule, idx) => {
    const mins = getRuleMinutes(rule);
    const totalMinutes = mins.length;
    let claimedCount = 0;
    const overlappingRuleIndices = new Set();

    mins.forEach(m => {
      if (claimedBy[m] !== null) {
        claimedCount++;
        overlappingRuleIndices.add(claimedBy[m]);
      } else {
        claimedBy[m] = idx;
      }
    });

    let conflict = null;
    if (totalMinutes > 0 && claimedCount > 0) {
      const overlapNames = Array.from(overlappingRuleIndices)
        .map(i => rules[i]?.name || `规则#${i + 1}`);

      if (claimedCount === totalMinutes) {
        conflict = {
          type: "full",
          message: `⚠️ 该时段已被上方「${overlapNames.join("、")}」完全覆盖，将无法生效（可点击上移或智能排序）`,
          overlapMinutes: claimedCount,
          overlappingRules: overlapNames
        };
      } else {
        conflict = {
          type: "partial",
          message: `ℹ️ 其中 ${claimedCount} 分钟优先执行上方「${overlapNames.join("、")}」，其余 ${totalMinutes - claimedCount} 分钟正常生效`,
          overlapMinutes: claimedCount,
          overlappingRules: overlapNames
        };
      }
    }

    results.push({
      rule,
      index: idx,
      totalMinutes,
      effectiveMinutes: totalMinutes - claimedCount,
      conflict
    });
  });

  return results;
}

function renderTimelineBar(rules) {
  const bar = document.getElementById("timelineBar");
  const fragment = document.createDocumentFragment();

  // 离散为 24 小时 (1440分钟)
  const minutes = new Array(1440).fill(null);

  rules.forEach(rule => {
    const startMin = parseTimeToMinutes(rule.start);
    const endMin = parseTimeToMinutes(rule.end);
    if (startMin === null || endMin === null) return;

    if (startMin <= endMin) {
      for (let m = startMin; m < endMin; m++) {
        if (minutes[m] === null) minutes[m] = rule;
      }
    } else {
      // 跨午夜
      for (let m = startMin; m < 1440; m++) {
        if (minutes[m] === null) minutes[m] = rule;
      }
      for (let m = 0; m < endMin; m++) {
        if (minutes[m] === null) minutes[m] = rule;
      }
    }
  });

  // 聚合连续段
  let segments = [];
  let curRule = minutes[0];
  let curStart = 0;
  let curCount = 0;

  for (let m = 0; m < 1440; m++) {
    if (minutes[m] === curRule) {
      curCount++;
    } else {
      segments.push({ rule: curRule, startMin: curStart, endMin: m, duration: curCount });
      curRule = minutes[m];
      curStart = m;
      curCount = 1;
    }
  }
  if (curCount > 0) {
    segments.push({ rule: curRule, startMin: curStart, endMin: 1440, duration: curCount });
  }

  segments.forEach(seg => {
    const el = document.createElement("div");
    el.className = "timeline-segment";
    el.style.width = `${(seg.duration / 1440) * 100}%`;
    if (seg.rule) {
      el.style.backgroundColor = getModeColor(seg.rule.mode);
      const startHm = formatMinutesToTime(seg.startMin);
      const endHm = formatMinutesToTime(seg.endMin);
      el.title = `${seg.rule.name} (${seg.rule.start} - ${seg.rule.end})\n实际生效展示区间: ${startHm} ~ ${endHm}`;
      if (seg.duration >= 90) {
        el.textContent = seg.rule.name;
      } else if (seg.duration >= 35) {
        el.textContent = seg.rule.name.length > 4 ? seg.rule.name.slice(0, 3) : seg.rule.name;
      } else {
        el.textContent = "";
      }
    } else {
      el.style.backgroundColor = "transparent";
      el.title = "未设定时段 (执行兜底模式)";
    }
    fragment.appendChild(el);
  });
  bar.replaceChildren(fragment);
}

function renderRuleList(rules) {
  const fragment = document.createDocumentFragment();

  if (rules.length === 0) {
    const empty = document.createElement("div");
    empty.style.textAlign = "center";
    empty.style.color = "var(--text-muted)";
    empty.style.padding = "20px";
    empty.textContent = "暂无排程规则，将全天执行兜底模式";
    document.getElementById("ruleListContainer").replaceChildren(empty);
    return;
  }

  const conflictAnalysis = analyzeRuleConflicts(rules);

  rules.forEach((rule, idx) => {
    if (!rule || typeof rule !== "object") {
      throw new Error("排程规则格式无效");
    }

    const analysis = conflictAnalysis[idx];
    const item = document.createElement("div");
    item.className = "rule-item";
    if (analysis && analysis.conflict) {
      if (analysis.conflict.type === "full") {
        item.classList.add("has-full-conflict");
      } else {
        item.classList.add("has-partial-conflict");
      }
    }

    const info = document.createElement("div");
    info.className = "rule-info";
    const time = document.createElement("span");
    time.className = "rule-time";
    time.textContent = `${rule.start} ~ ${rule.end}`;

    const details = document.createElement("div");
    details.className = "rule-details";

    const topRow = document.createElement("div");
    topRow.className = "rule-details-top";

    const name = document.createElement("span");
    name.style.fontWeight = "600";
    name.textContent = rule.name;

    const mode = document.createElement("span");
    mode.className = "rule-mode-tag";
    mode.style.borderLeft = `3px solid ${getModeColor(rule.mode)}`;
    mode.textContent = getModeLabel(rule.mode);
    topRow.append(name, mode);

    if (rule.mode === "photo_album") {
      const interval = document.createElement("span");
      interval.style.fontSize = "11px";
      interval.style.color = "var(--text-muted)";
      const rotateMin = rule.config && rule.config.rotate_interval_min
        ? rule.config.rotate_interval_min
        : 60;
      interval.textContent = `(每${rotateMin}分钟换图)`;
      topRow.appendChild(interval);
    }
    details.appendChild(topRow);

    // 冲突遮挡提示
    if (analysis && analysis.conflict) {
      const badge = document.createElement("div");
      badge.className = `rule-conflict-badge ${analysis.conflict.type === "full" ? "conflict-badge-full" : "conflict-badge-partial"}`;
      badge.textContent = analysis.conflict.message;
      details.appendChild(badge);
    }

    info.append(time, details);

    const actions = document.createElement("div");
    actions.className = "rule-actions";

    // 上移按钮
    const upButton = document.createElement("button");
    upButton.className = "btn-icon";
    upButton.textContent = "▲";
    upButton.title = "上移（提高规则匹配优先级）";
    upButton.dataset = { edgeDisabled: idx === 0 ? "true" : "false" };
    if (typeof upButton.setAttribute === "function") {
      upButton.setAttribute("data-edge-disabled", idx === 0 ? "true" : "false");
    }
    upButton.disabled = scheduleBusy || idx === 0;
    upButton.addEventListener("click", () => moveRule(idx, -1));
    actions.appendChild(upButton);

    // 下移按钮
    const downButton = document.createElement("button");
    downButton.className = "btn-icon";
    downButton.textContent = "▼";
    downButton.title = "下移（降低规则匹配优先级）";
    downButton.dataset = { edgeDisabled: idx === rules.length - 1 ? "true" : "false" };
    if (typeof downButton.setAttribute === "function") {
      downButton.setAttribute("data-edge-disabled", idx === rules.length - 1 ? "true" : "false");
    }
    downButton.disabled = scheduleBusy || idx === rules.length - 1;
    downButton.addEventListener("click", () => moveRule(idx, 1));
    actions.appendChild(downButton);

    // 删除按钮
    const deleteButton = document.createElement("button");
    deleteButton.className = "btn btn-outline";
    deleteButton.style.padding = "4px 10px";
    deleteButton.style.fontSize = "12px";
    deleteButton.style.color = "#ef4444";
    deleteButton.textContent = "删除";
    deleteButton.disabled = scheduleBusy;
    deleteButton.addEventListener("click", () => deleteRule(rule.id));
    actions.appendChild(deleteButton);

    item.append(info, actions);
    fragment.appendChild(item);
  });

  document.getElementById("ruleListContainer").replaceChildren(fragment);
}

function cloneScheduleConfig() {
  return JSON.parse(JSON.stringify(currentScheduleConfig));
}

async function moveRule(index, direction) {
  if (scheduleBusy || !currentScheduleConfig) return;
  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= currentScheduleConfig.rules.length) return;

  const nextConfig = cloneScheduleConfig();
  const [removed] = nextConfig.rules.splice(index, 1);
  nextConfig.rules.splice(targetIndex, 0, removed);
  await saveScheduleConfig(nextConfig);
}

async function sortRulesByTime() {
  if (scheduleBusy || !currentScheduleConfig || currentScheduleConfig.rules.length <= 1) return;
  const nextConfig = cloneScheduleConfig();
  nextConfig.rules = sortRulesSmart(nextConfig.rules);
  await saveScheduleConfig(nextConfig);
}

function updateNewRuleHint() {
  const hintEl = document.getElementById("newRuleConflictHint");
  if (!hintEl || !currentScheduleConfig) return;

  const start = document.getElementById("newRuleStart").value;
  const end = document.getElementById("newRuleEnd").value;
  const startMin = parseTimeToMinutes(start);
  const endMin = parseTimeToMinutes(end);
  if (startMin === null || endMin === null) {
    hintEl.style.display = "none";
    return;
  }
  if (startMin === endMin) {
    hintEl.className = "hint-conflict-full";
    hintEl.textContent = "⚠️ 开始时间与结束时间不能相同";
    hintEl.style.display = "block";
    return;
  }

  const tempRule = { start, end };
  const tempMins = getRuleMinutes(tempRule);
  if (tempMins.length === 0) {
    hintEl.style.display = "none";
    return;
  }

  const overlappingRules = [];
  currentScheduleConfig.rules.forEach(r => {
    const rMins = new Set(getRuleMinutes(r));
    const overlap = tempMins.filter(m => rMins.has(m)).length;
    if (overlap > 0) {
      overlappingRules.push({ name: r.name, overlap, dur: rMins.size });
    }
  });

  if (overlappingRules.length === 0) {
    hintEl.className = "hint-conflict-ok";
    hintEl.textContent = "✓ 该时段与现有排程规则无时间重叠";
    hintEl.style.display = "block";
  } else {
    const ruleNames = overlappingRules.map(r => `「${r.name}」`).join("、");
    const isSubPeriod = overlappingRules.every(r => tempMins.length < r.dur);
    hintEl.className = "hint-conflict-partial";
    hintEl.textContent = isSubPeriod
      ? `ℹ️ 提示: 该时段属于现有 ${ruleNames} 的子时段，保存后将自动置于其上方优先执行。`
      : `ℹ️ 提示: 该时段与现有 ${ruleNames} 存在重叠，保存后将按子时段优先规则自动排布。`;
    hintEl.style.display = "block";
  }
}

function initScheduleForm() {
  const sortBtn = document.getElementById("sortRulesBtn");
  if (sortBtn) {
    sortBtn.addEventListener("click", sortRulesByTime);
  }

  document.getElementById("newRuleStart").addEventListener("input", updateNewRuleHint);
  document.getElementById("newRuleEnd").addEventListener("input", updateNewRuleHint);

  document.getElementById("addRuleBtn").addEventListener("click", async () => {
    if (scheduleBusy || !currentScheduleConfig) return;

    const name = document.getElementById("newRuleName").value.trim() || "自定义时段";
    const start = document.getElementById("newRuleStart").value;
    const end = document.getElementById("newRuleEnd").value;
    const mode = document.getElementById("newRuleMode").value;

    const startMin = parseTimeToMinutes(start);
    const endMin = parseTimeToMinutes(end);
    if (startMin === null || endMin === null) {
      alert("请填写有效的开始时间和结束时间！");
      return;
    }
    if (startMin === endMin) {
      alert("开始时间和结束时间不能相同！");
      return;
    }

    let rotateMin = 60;
    if (mode === "photo_album") {
      rotateMin = document.getElementById("newRuleRotateMin").valueAsNumber;
      if (!Number.isInteger(rotateMin) || rotateMin < 10 || rotateMin > 1440) {
        alert("相册轮换间隔必须是 10~1440 分钟之间的整数！");
        return;
      }
    }

    const newRule = {
      id: "rule_" + Date.now(),
      name: name,
      start: start,
      end: end,
      mode: mode,
      config: mode === "photo_album" ? { rotate_interval_min: rotateMin } : {}
    };
    const nextConfig = cloneScheduleConfig();
    nextConfig.rules.unshift(newRule);

    const autoSort = document.getElementById("autoSortCheckbox")?.checked;
    if (autoSort) {
      nextConfig.rules = sortRulesSmart(nextConfig.rules);
    }

    await saveScheduleConfig(nextConfig);
    updateNewRuleHint();
  });

  document.getElementById("fallbackModeSelect").addEventListener("change", async (e) => {
    if (scheduleBusy || !currentScheduleConfig) return;
    const nextConfig = cloneScheduleConfig();
    nextConfig.fallback_mode = e.target.value;
    await saveScheduleConfig(nextConfig);
  });

  // 时段类型切换时联动展示相册轮播间隔
  document.getElementById("newRuleMode").addEventListener("change", (e) => {
    const rotateGroup = document.getElementById("rotateIntervalGroup");
    rotateGroup.style.display = e.target.value === "photo_album" ? "block" : "none";
  });
}

async function deleteRule(ruleId) {
  if (scheduleBusy || !currentScheduleConfig) return;
  if (!confirm("确定删除此时段规则吗？")) return;

  const nextConfig = cloneScheduleConfig();
  const index = nextConfig.rules.findIndex(rule => rule.id === ruleId);
  if (index < 0) {
    alert("该规则已不存在，正在刷新排程！");
    await loadSchedule();
    return;
  }
  nextConfig.rules.splice(index, 1);
  await saveScheduleConfig(nextConfig);
}

async function saveScheduleConfig(nextConfig) {
  if (scheduleBusy || !currentScheduleConfig) return false;

  scheduleBusy = true;
  updateScheduleControls();
  try {
    await requestJson("/api/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(nextConfig)
    });

    currentScheduleConfig = nextConfig;
    renderTimelineBar(nextConfig.rules);
    renderRuleList(nextConfig.rules);
    document.getElementById("fallbackModeSelect").value = nextConfig.fallback_mode || "photo_album";
    await loadSchedule();
    return true;
  } catch (err) {
    alert(`保存排程失败: ${err.message}`);
    if (currentScheduleConfig) {
      document.getElementById("fallbackModeSelect").value = currentScheduleConfig.fallback_mode || "photo_album";
    }
    return false;
  } finally {
    scheduleBusy = false;
    updateScheduleControls();
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

    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    memoStatusRequestVersion++;
    try {
      await requestJson("/api/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title,
          text: text,
          duration_min: duration,
          sender: "Web后台"
        })
      });
      alert("便签已推送，已向 ESP32 网关发送即时刷新指令！");
      document.getElementById("memoTextInput").value = "";
      await loadMemoStatus();
    } catch (err) {
      alert(`推送失败: ${err.message}`);
    } finally {
      submitButton.disabled = false;
    }
  });

  document.getElementById("clearMemoBtn").addEventListener("click", async (e) => {
    if (!confirm("确定撤回当前即时便签吗？")) return;
    const button = e.currentTarget;
    button.disabled = true;
    memoStatusRequestVersion++;
    try {
      await requestJson("/api/push", { method: "DELETE" });
      alert("便签已清除，已通知网关恢复常规排程！");
      await loadMemoStatus();
    } catch (err) {
      alert(`清除失败: ${err.message}`);
    } finally {
      button.disabled = false;
    }
  });
}

async function loadMemoStatus() {
  const requestVersion = ++memoStatusRequestVersion;
  try {
    const memo = await requestJson("/api/memo/status");
    if (requestVersion !== memoStatusRequestVersion) return;
    if (!memo || typeof memo.active !== "boolean") {
      throw new Error("便签状态响应格式无效");
    }

    const card = document.getElementById("activeMemoCard");
    if (memo.active) {
      const remainingSec = Number(memo.remaining_sec);
      if (!Number.isFinite(remainingSec) || remainingSec < 0) {
        throw new Error("便签剩余时间无效");
      }
      card.style.display = "block";
      document.getElementById("activeMemoTitle").textContent = memo.title;
      document.getElementById("activeMemoText").textContent = memo.text;

      const remainMin = Math.max(0, Math.ceil(remainingSec / 60));
      document.getElementById("activeMemoExpire").textContent = `剩余展示约 ${remainMin} 分钟 (发布者: ${memo.sender})`;
    } else {
      card.style.display = "none";
    }
  } catch (err) {
    if (requestVersion !== memoStatusRequestVersion) return;
    console.error("获取便签状态失败:", err);
    const card = document.getElementById("activeMemoCard");
    if (card.style.display !== "none") {
      document.getElementById("activeMemoExpire").textContent = "便签状态刷新失败，当前信息可能不是最新";
    }
  }
}

// ----------------- 系统设置与日历/网关联动 -----------------
async function updateCalendarStatusDisplay() {
  const statusEl = document.getElementById("calendarSyncStatus");
  if (!statusEl) return;
  try {
    const data = await requestJson("/api/calendar");
    if (!data) return;
    const isMock = data.is_mock;
    const count = (data.events || []).length;
    const ut = data.update_time || "--:--";
    if (isMock) {
      statusEl.innerHTML = `<span style="color: #d97706;">⚠️ 未配置 iCal URL，当前展示模拟日程 (共 ${count} 项，更新于 ${ut})</span>`;
    } else if (data.status === "error" || data.stale) {
      statusEl.innerHTML = `<span style="color: #dc2626;">⚠️ 同步异常或展示离线缓存 (共 ${count} 项): ${data.message || "连接受限"}</span>`;
    } else {
      statusEl.innerHTML = `<span style="color: #059669;">✅ iCal 已同步 (${data.message || `找到 ${count} 项今日日程`}，更新于 ${ut})</span>`;
    }
  } catch (err) {
    statusEl.innerHTML = `<span style="color: #dc2626;">❌ 获取日历状态失败: ${err.message}</span>`;
  }
}

function initSettingsForm() {
  // 核心与天气表单
  document.getElementById("settingsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const gatewayUrl = document.getElementById("gatewayUrlInput").value.trim();
    const weatherCity = document.getElementById("weatherCityInput") ? document.getElementById("weatherCityInput").value.trim() : "";
    const submitButton = e.currentTarget.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      await requestJson("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gateway_url: gatewayUrl, weather_city: weatherCity })
      });
      alert("核心设置保存成功！");
    } catch (err) {
      alert(`保存失败: ${err.message}`);
    } finally {
      submitButton.disabled = false;
    }
  });

  // 日历保存链接按钮
  const saveCalBtn = document.getElementById("saveCalendarBtn");
  if (saveCalBtn) {
    saveCalBtn.addEventListener("click", async () => {
      const icalUrl = document.getElementById("calendarIcalUrlInput").value.trim();
      saveCalBtn.disabled = true;
      try {
        await requestJson("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ calendar_ical_url: icalUrl })
        });
        alert("日历链接保存成功！已触发后台自动同步。");
        await updateCalendarStatusDisplay();
      } catch (err) {
        alert(`保存日历链接失败: ${err.message}`);
      } finally {
        saveCalBtn.disabled = false;
      }
    });
  }

  // 日历立即同步测试按钮
  const syncCalBtn = document.getElementById("syncCalendarBtn");
  if (syncCalBtn) {
    syncCalBtn.addEventListener("click", async () => {
      const icalUrl = document.getElementById("calendarIcalUrlInput").value.trim();
      syncCalBtn.disabled = true;
      syncCalBtn.textContent = "正在拉取...";
      try {
        const query = icalUrl ? `?url=${encodeURIComponent(icalUrl)}` : "";
        const data = await requestJson(`/api/calendar/refresh${query}`, { method: "POST" });
        alert(data.message || "日历已同步更新！");
        await updateCalendarStatusDisplay();
      } catch (err) {
        alert(`日历同步失败: ${err.message}`);
      } finally {
        syncCalBtn.disabled = false;
        syncCalBtn.textContent = "🔄 立即同步";
      }
    });
  }

  // 日历预览按钮
  const previewCalBtn = document.getElementById("previewCalendarBtn");
  const previewBox = document.getElementById("calendarPreviewBox");
  const previewImg = document.getElementById("calendarPreviewImg");
  const closeCalPreviewBtn = document.getElementById("closeCalendarPreviewBtn");

  if (previewCalBtn && previewBox && previewImg) {
    previewCalBtn.addEventListener("click", () => {
      const icalUrl = document.getElementById("calendarIcalUrlInput").value.trim();
      const query = icalUrl ? `?url=${encodeURIComponent(icalUrl)}&t=${Date.now()}` : `?t=${Date.now()}`;
      previewImg.src = `/api/calendar/preview.png${query}`;
      previewBox.style.display = "block";
    });
  }

  if (closeCalPreviewBtn && previewBox) {
    closeCalPreviewBtn.addEventListener("click", () => {
      previewBox.style.display = "none";
    });
  }

  // 网关手动触发按钮
  document.getElementById("testGatewayBtn").addEventListener("click", async () => {
    const btn = document.getElementById("testGatewayBtn");
    btn.disabled = true;
    btn.textContent = "正在通知网关...";
    try {
      const data = await requestJson("/api/trigger", { method: "POST" });
      if (!data || data.status !== "ok") {
        throw new Error(data && data.message ? data.message : "网关触发失败");
      }
      alert(data.message);
    } catch (err) {
      alert(`触发失败: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "⚡ 立即触发网关同步 (测试刷新)";
    }
  });

  // 硬件原生万年历指令触发按钮
  const triggerNativeCalBtn = document.getElementById("triggerNativeCalBtn");
  if (triggerNativeCalBtn) {
    triggerNativeCalBtn.addEventListener("click", async () => {
      triggerNativeCalBtn.disabled = true;
      triggerNativeCalBtn.textContent = "正在下发万年历指令并等待全刷 (约18秒)...";
      try {
        const data = await requestJson("/api/device/calendar", { method: "POST" });
        if (!data || data.status !== "ok") {
          throw new Error(data && data.message ? data.message : "指令下发失败");
        }
        alert(data.message);
      } catch (err) {
        alert(`切换失败: ${err.message}`);
      } finally {
        triggerNativeCalBtn.disabled = false;
        triggerNativeCalBtn.textContent = "📆 立即切换墨水屏至硬件原生万年历 (0x20 指令)";
      }
    });
  }
}

async function loadSettings() {
  try {
    const data = await requestJson("/api/settings");
    if (!data || typeof data.gateway_url !== "string" || !data.gateway_url) {
      throw new Error("设置响应格式无效");
    }
    document.getElementById("gatewayUrlInput").value = data.gateway_url;
    if (document.getElementById("weatherCityInput")) {
      document.getElementById("weatherCityInput").value = data.weather_city || "";
    }
    if (document.getElementById("calendarIcalUrlInput")) {
      document.getElementById("calendarIcalUrlInput").value = data.calendar_ical_url || "";
    }
    await updateCalendarStatusDisplay();
  } catch (err) {
    console.error("加载系统设置失败:", err);
    document.getElementById("gatewayUrlInput").placeholder = "设置加载失败，请刷新后重试";
  }
}
