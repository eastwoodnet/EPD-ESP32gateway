// Ported & Optimized from tsl0922/EPD-nRF5
// 墨水屏专用三色调色板与抖动算法

const threeColorPalette = [
  { name: "黑色", r: 0, g: 0, b: 0, value: 0x00 },
  { name: "白色", r: 255, g: 255, b: 255, value: 0x01 },
  { name: "红色", r: 255, g: 0, b: 0, value: 0x02 }
];

function adjustContrast(imageData, factor) {
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    data[i] = Math.min(255, Math.max(0, (data[i] - 128) * factor + 128));
    data[i + 1] = Math.min(255, Math.max(0, (data[i + 1] - 128) * factor + 128));
    data[i + 2] = Math.min(255, Math.max(0, (data[i + 2] - 128) * factor + 128));
  }
  return imageData;
}

function rgbToLab(r, g, b) {
  r = r / 255;
  g = g / 255;
  b = b / 255;

  r = r > 0.04045 ? Math.pow((r + 0.055) / 1.055, 2.4) : r / 12.92;
  g = g > 0.04045 ? Math.pow((g + 0.055) / 1.055, 2.4) : g / 12.92;
  b = b > 0.04045 ? Math.pow((b + 0.055) / 1.055, 2.4) : b / 12.92;

  r *= 100;
  g *= 100;
  b *= 100;

  let x = r * 0.4124 + g * 0.3576 + b * 0.1805;
  let y = r * 0.2126 + g * 0.7152 + b * 0.0722;
  let z = r * 0.0193 + g * 0.1192 + b * 0.9505;

  x /= 95.047;
  y /= 100.0;
  z /= 108.883;

  x = x > 0.008856 ? Math.pow(x, 1 / 3) : (7.787 * x) + (16 / 116);
  y = y > 0.008856 ? Math.pow(y, 1 / 3) : (7.787 * y) + (16 / 116);
  z = z > 0.008856 ? Math.pow(z, 1 / 3) : (7.787 * z) + (16 / 116);

  const l = (116 * y) - 16;
  const a = 500 * (x - y);
  const bLab = 200 * (y - z);

  return { l, a, b: bLab };
}

function labDistance(lab1, lab2) {
  const dl = lab1.l - lab2.l;
  const da = lab1.a - lab2.a;
  const db = lab1.b - lab2.b;
  return Math.sqrt(0.2 * dl * dl + 3 * da * da + 3 * db * db);
}

function findClosestColor(r, g, b) {
  const inputLab = rgbToLab(r, g, b);
  let minDistance = Infinity;
  let closestColor = threeColorPalette[0];

  for (const color of threeColorPalette) {
    const colorLab = rgbToLab(color.r, color.g, color.b);
    const distance = labDistance(inputLab, colorLab);
    if (distance < minDistance) {
      minDistance = distance;
      closestColor = color;
    }
  }
  return closestColor;
}

// Floyd-Steinberg 误差扩散抖动
function floydSteinbergDither(imageData, strength = 1.0) {
  const width = imageData.width;
  const height = imageData.height;
  const data = imageData.data;
  const tempData = new Uint8ClampedArray(data);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      const r = tempData[idx];
      const g = tempData[idx + 1];
      const b = tempData[idx + 2];

      const closest = findClosestColor(r, g, b);

      const errR = (r - closest.r) * strength;
      const errG = (g - closest.g) * strength;
      const errB = (b - closest.b) * strength;

      data[idx] = closest.r;
      data[idx + 1] = closest.g;
      data[idx + 2] = closest.b;
      data[idx + 3] = 255;

      const distributeError = (dx, dy, factor) => {
        const nx = x + dx;
        const ny = y + dy;
        if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
          const nidx = (ny * width + nx) * 4;
          tempData[nidx] = Math.min(255, Math.max(0, tempData[nidx] + errR * factor));
          tempData[nidx + 1] = Math.min(255, Math.max(0, tempData[nidx + 1] + errG * factor));
          tempData[nidx + 2] = Math.min(255, Math.max(0, tempData[nidx + 2] + errB * factor));
        }
      };

      distributeError(1, 0, 7 / 16);
      distributeError(-1, 1, 3 / 16);
      distributeError(0, 1, 5 / 16);
      distributeError(1, 1, 1 / 16);
    }
  }
  return imageData;
}

// Atkinson 抖动（艺术感极强，反差锐利）
function atkinsonDither(imageData, strength = 1.0) {
  const width = imageData.width;
  const height = imageData.height;
  const data = imageData.data;
  const tempData = new Uint8ClampedArray(data);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      const r = tempData[idx];
      const g = tempData[idx + 1];
      const b = tempData[idx + 2];

      const closest = findClosestColor(r, g, b);

      const errR = ((r - closest.r) * strength) / 8;
      const errG = ((g - closest.g) * strength) / 8;
      const errB = ((b - closest.b) * strength) / 8;

      data[idx] = closest.r;
      data[idx + 1] = closest.g;
      data[idx + 2] = closest.b;
      data[idx + 3] = 255;

      const distributeError = (dx, dy) => {
        const nx = x + dx;
        const ny = y + dy;
        if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
          const nidx = (ny * width + nx) * 4;
          tempData[nidx] = Math.min(255, Math.max(0, tempData[nidx] + errR));
          tempData[nidx + 1] = Math.min(255, Math.max(0, tempData[nidx + 1] + errG));
          tempData[nidx + 2] = Math.min(255, Math.max(0, tempData[nidx + 2] + errB));
        }
      };

      distributeError(1, 0);
      distributeError(2, 0);
      distributeError(-1, 1);
      distributeError(0, 1);
      distributeError(1, 1);
      distributeError(0, 2);
    }
  }
  return imageData;
}

// 无抖动纯阈值三色量化（与 processImageDataToBinary 阈值严格一致）
function thresholdDither(imageData) {
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    if (r > 150 && g < 100 && b < 100) {
      data[i] = 255;
      data[i + 1] = 0;
      data[i + 2] = 0;
    } else {
      const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
      const v = gray < 128 ? 0 : 255;
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v;
    }
    data[i + 3] = 255;
  }
  return imageData;
}

// 核心打包函数：将 Canvas ImageData 转为 30,000 字节二进制流 (15,000B 黑白 + 15,000B 红白)
function processImageDataToBinary(imageData) {
  const width = imageData.width;
  const height = imageData.height;
  const data = imageData.data;

  const byteWidth = Math.ceil(width / 8);
  const channelLen = byteWidth * height;

  const blackWhiteData = new Uint8Array(channelLen).fill(0xFF);
  const redWhiteData = new Uint8Array(channelLen).fill(0xFF);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      const r = data[idx];
      const g = data[idx + 1];
      const b = data[idx + 2];

      const byteIdx = y * byteWidth + Math.floor(x / 8);
      const bitIdx = 7 - (x % 8);

      // 判断三色分类
      if (r > 150 && g < 100 && b < 100) {
        // 红色: redWhiteData 对应 bit 置 0
        redWhiteData[byteIdx] &= ~(1 << bitIdx);
        // 黑白通道置 1 (非黑)
        blackWhiteData[byteIdx] |= (1 << bitIdx);
      } else {
        const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
        if (gray < 128) {
          // 黑色: blackWhiteData 对应 bit 置 0
          blackWhiteData[byteIdx] &= ~(1 << bitIdx);
        } else {
          // 白色: blackWhiteData 对应 bit 置 1
          blackWhiteData[byteIdx] |= (1 << bitIdx);
        }
        // 红色通道保持 1 (非红)
        redWhiteData[byteIdx] |= (1 << bitIdx);
      }
    }
  }

  const result = new Uint8Array(channelLen * 2);
  result.set(blackWhiteData, 0);
  result.set(redWhiteData, channelLen);
  return result;
}
