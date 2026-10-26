const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.children = [];
    this.style = {};
    this.className = "";
    this.textContent = "";
    this.disabled = false;
    this.listeners = {};
    this.classList = {
      add: (...names) => {
        this.className = [...new Set([...this.className.split(" ").filter(Boolean), ...names])].join(" ");
      },
    };
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = [...children];
  }

  addEventListener(name, handler) {
    this.listeners[name] = handler;
  }
}

const elements = new Map();
global.document = {
  addEventListener() {},
  createElement(tagName) {
    return new FakeElement(tagName);
  },
  createDocumentFragment() {
    return new FakeElement("fragment");
  },
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new FakeElement("div"));
    return elements.get(id);
  },
};

const serverDir = path.resolve(__dirname, "..");
vm.runInThisContext(fs.readFileSync(path.join(serverDir, "static/js/dithering.js"), "utf8"));
vm.runInThisContext(fs.readFileSync(path.join(serverDir, "static/js/app.js"), "utf8"));

const imageData = {
  width: 8,
  height: 2,
  data: new Uint8ClampedArray(8 * 2 * 4).fill(255),
};
imageData.data.set([0, 0, 0, 255], 0);
imageData.data.set([255, 0, 0, 255], 4);
const packed = processImageDataToBinary(imageData);
assert.equal(packed.length, 4);
assert.deepEqual([...packed], [0x7f, 0xff, 0xbf, 0xff]);

assert.equal(parseTimeToMinutes("08:30"), 510);
assert.equal(parseTimeToMinutes("24:00"), null);
assert.equal(parseTimeToMinutes("8:30"), null);
assert.equal(parseTimeToMinutes(null), null);

const payload = '<img src=x onerror="globalThis.pwned=true">';
renderRuleList([{
  id: "rule_xss",
  name: payload,
  start: "08:00",
  end: "09:00",
  mode: payload,
  config: { rotate_interval_min: 60 },
}]);

const rendered = document.getElementById("ruleListContainer");
function collectText(element) {
  return [element.textContent, ...element.children.map(collectText)].join("\n");
}
const serialized = JSON.stringify(rendered, (key, value) => key === "listeners" ? undefined : value);
assert.ok(collectText(rendered).includes(payload));
assert.ok(!serialized.includes("innerHTML"));
assert.equal(globalThis.pwned, undefined);

const invalidSchedule = validateScheduleResponse({
  config: { rules: [], fallback_mode: "photo_album" },
  active_mode: "photo_album",
  next_pull_sec: 30,
});
assert.equal(invalidSchedule.active_mode, "photo_album");
assert.throws(() => validateScheduleResponse({ config: {} }), /排程响应格式无效/);

// 验证智能排序：子时段优先于宽泛时段，非重叠时段按开始时间升序
const smartSorted = sortRulesSmart([
  { id: "day", name: "白天相册", start: "08:30", end: "22:30", mode: "photo_album", config: {} },
  { id: "night", name: "夜间休眠", start: "22:30", end: "08:30", mode: "sleep_dnd", config: {} },
  { id: "afternoon", name: "下午天气", start: "13:30", end: "18:00", mode: "weather_date", config: {} },
  { id: "morning", name: "早间天气", start: "08:30", end: "09:30", mode: "weather_date", config: {} },
]);
assert.deepEqual(smartSorted.map(r => r.id), ["morning", "afternoon", "day", "night"]);
const smartConflicts = analyzeRuleConflicts(smartSorted);
assert.ok(smartConflicts.every(item => item.effectiveMinutes > 0));

// 验证日间/夜间/自动主题解析逻辑
assert.equal(resolveEffectiveTheme("dark"), "dark");
assert.equal(resolveEffectiveTheme("light"), "light");
assert.equal(resolveEffectiveTheme("auto"), "light");

console.log("Frontend tests passed");
