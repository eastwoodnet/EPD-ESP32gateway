import time
import os
from datetime import datetime
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

# 寻找跨不同 Linux 发行版（Debian/Ubuntu/CentOS/Alpine/Arch）中可用的中文字体
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_FONTS_DIR = os.path.join(BASE_DIR, "fonts")

FONT_CANDIDATES = [
    # 本地放置的字体优先
    os.path.join(LOCAL_FONTS_DIR, "font.ttc"),
    os.path.join(LOCAL_FONTS_DIR, "font.ttf"),
    os.path.join(LOCAL_FONTS_DIR, "wqy-zenhei.ttc"),
    # Debian / Ubuntu / Armbian
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    # Arch / Fedora / RHEL
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    # Alpine Linux
    "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",
    # Android / Droid 遗留系统
    "/usr/share/fonts/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/droid/DroidSansFallbackLegacy.ttf",
    "/usr/share/fonts/maple-mono-nf-cn/MapleMono-NF-CN-Medium.ttf",
]

def get_font(size: int, bold: bool = False):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def raw_to_image(raw_bytes: bytes, width: int = 400, height: int = 300) -> Image.Image:
    """
    将 30000 字节点阵 (前 15000 字节黑白, 后 15000 字节红色) 还原为三色 RGB Image
    用于在 Web 页面生成缩略图预览
    """
    img = Image.new("RGB", (width, height), (255, 255, 255))
    byte_width = (width + 7) // 8
    channel_len = byte_width * height

    if len(raw_bytes) < channel_len:
        return img

    bw_data = raw_bytes[:channel_len]
    red_data = raw_bytes[channel_len:channel_len * 2] if len(raw_bytes) >= channel_len * 2 else None

    pixels = img.load()
    for y in range(height):
        for x in range(width):
            byte_idx = y * byte_width + (x // 8)
            bit_idx = 7 - (x % 8)

            bw_bit = (bw_data[byte_idx] >> bit_idx) & 1
            red_bit = ((red_data[byte_idx] >> bit_idx) & 1) if red_data else 1

            if red_bit == 0:
                pixels[x, y] = (255, 0, 0)      # 红色
            elif bw_bit == 0:
                pixels[x, y] = (0, 0, 0)        # 黑色
            else:
                pixels[x, y] = (255, 255, 255)  # 白色

    return img

def clean_text(s: str) -> str:
    """替换常见 emoji 为优雅符号，避免字体库缺失出现方块"""
    s = s.replace("📌", "★ ").replace("⏳", "· ").replace("⚠️", "[提醒] ").replace("🌙", "· ")
    return s

def image_to_raw(img: Image.Image, width: int = 400, height: int = 300) -> bytes:
    """
    将 RGB Image 量化为 30000 字节点阵 (15000B BW + 15000B Red)
    EPD 规范:
      黑白通道: 1 = 白色, 0 = 黑色
      红色通道: 0 = 红色, 1 = 非红
    """
    img = img.resize((width, height)).convert("RGB")
    byte_width = (width + 7) // 8
    channel_len = byte_width * height

    bw_data = bytearray(b"\xFF" * channel_len)   # 默认全白
    red_data = bytearray(b"\xFF" * channel_len)  # 默认无红

    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            byte_idx = y * byte_width + (x // 8)
            bit_idx = 7 - (x % 8)

            # 严格判定纯红 (红通道高，绿蓝明显偏低)
            if r > 160 and g < 110 and b < 110:
                red_data[byte_idx] &= ~(1 << bit_idx)  # 红色通道置 0 (出红)
                bw_data[byte_idx] |= (1 << bit_idx)    # 黑白通道置 1 (非黑)
            else:
                gray = int(0.299 * r + 0.587 * g + 0.114 * b)
                if gray < 130:
                    bw_data[byte_idx] &= ~(1 << bit_idx) # 黑色通道置 0 (出黑)
                else:
                    bw_data[byte_idx] |= (1 << bit_idx)  # 白色通道置 1 (出白)
                red_data[byte_idx] |= (1 << bit_idx)     # 红色通道保持 1 (无红)

    return bytes(bw_data + red_data)

def render_memo_image(title: str, text: str, sender: str, expire_at: float, width: int = 400, height: int = 300) -> bytes:
    """
    渲染桌面即时便签卡片 (400x300 三色点阵)
    顶部红色醒目标签，中间自适应换行正文，底部保留时长倒计时
    """
    title = clean_text(title)
    text = clean_text(text)
    sender = clean_text(sender)

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 1. 顶部红色标题栏 (高 45px)
    draw.rectangle([(0, 0), (width, 45)], fill=(255, 0, 0))

    font_title = get_font(20, bold=True)
    font_sub = get_font(13)

    now_str = datetime.now().strftime("%H:%M")
    draw.text((15, 12), title, font=font_title, fill=(255, 255, 255))

    sender_label = f"[{sender} {now_str}]"
    draw.text((width - 15, 16), sender_label, font=font_sub, fill=(255, 255, 255), anchor="ra")

    # 2. 正文区域 (400x300, 自动按行折行)
    # 动态根据文本长度选择字号
    text_len = len(text)
    if text_len <= 30:
        font_size = 28
        line_height = 38
    elif text_len <= 80:
        font_size = 22
        line_height = 30
    else:
        font_size = 18
        line_height = 25

    font_body = get_font(font_size)

    # 自动折行算法
    max_text_width = width - 40  # 左右各留 20px 边距
    lines = []
    current_line = ""

    # 处理显式换行符
    paragraphs = text.split("\n")
    for para in paragraphs:
        if not para:
            lines.append("")
            continue
        for char in para:
            test_line = current_line + char
            bbox = font_body.getbbox(test_line)
            w = bbox[2] - bbox[0]
            if w <= max_text_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
            current_line = ""

    # 计算文本起始 Y 坐标以垂直居中
    total_text_height = len(lines) * line_height
    available_height = height - 45 - 35  # 减去顶部和底部
    start_y = 45 + max(10, (available_height - total_text_height) // 2)

    for i, line in enumerate(lines):
        y_pos = start_y + i * line_height
        if y_pos + line_height > height - 35:
            # 溢出提示
            draw.text((20, y_pos), "...", font=font_body, fill=(0, 0, 0))
            break
        draw.text((20, y_pos), line, font=font_body, fill=(0, 0, 0))

    # 3. 底部状态与自动恢复说明条
    draw.line([(15, height - 32), (width - 15, height - 32)], fill=(255, 0, 0), width=1)
    exp_dt = datetime.fromtimestamp(expire_at)
    exp_str = exp_dt.strftime("%H:%M")
    footer_text = f"● 持续展示至 {exp_str} 自动恢复常规排程"
    draw.text((width // 2, height - 18), footer_text, font=font_sub, fill=(0, 0, 0), anchor="mm")

    return image_to_raw(img, width, height)

def render_clock_image(width: int = 400, height: int = 300, info: str = "墨水屏数据中继服务") -> bytes:
    """
    当相册未配置或处于兜底时钟模式时，渲染极简日历画面。
    刻意不渲染分钟级时间：墨水屏固件自带时钟模式负责走时，本图只需日期级精度，
    否则 ETag 每分钟变化导致网关永远收不到 304，每次都全屏刷新。
    """
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    now = datetime.now()
    date_str = now.strftime("%Y年%m月%d日")
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_str = weekdays[now.weekday()]

    # 红色边框点缀
    draw.rectangle([(8, 8), (width - 9, height - 9)], outline=(255, 0, 0), width=2)

    # 头部标题
    font_sub = get_font(15)
    draw.text((width // 2, 40), "墨水屏数据中继服务", font=font_sub, fill=(255, 0, 0), anchor="mm")
    draw.line([(50, 58), (width - 50, 58)], fill=(255, 0, 0), width=1)

    # 超大日期显示 (居中, 一天内 ETag 恒定)
    font_clock = get_font(36, bold=True)
    draw.text((width // 2, 140), date_str, font=font_clock, fill=(0, 0, 0), anchor="mm")
    font_week = get_font(28)
    draw.text((width // 2, 190), weekday_str, font=font_week, fill=(0, 0, 0), anchor="mm")

    # 底部状态
    font_tip = get_font(13)
    draw.text((width // 2, 245), "· 系统状态正常 · 定时同步中 ·", font=font_tip, fill=(255, 0, 0), anchor="mm")
    draw.text((width // 2, 270), clean_text(info), font=font_tip, fill=(0, 0, 0), anchor="mm")

    return image_to_raw(img, width, height)

# 免打扰睡眠图为静态内容，进程内缓存一份，保证 ETag 恒定 (后续请求全部走 304)
_sleep_image_cache: Optional[bytes] = None

def render_sleep_image(width: int = 400, height: int = 300) -> bytes:
    """
    夜间免打扰模式的静态睡眠提示画面。
    不含任何时间元素且结果常驻缓存，ETag 永久不变，网关只需全刷一次后持续 304 休眠。
    """
    global _sleep_image_cache
    if _sleep_image_cache is None:
        img = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(8, 8), (width - 9, height - 9)], outline=(0, 0, 0), width=2)
        font_main = get_font(30)
        font_sub = get_font(15)
        draw.text((width // 2, 130), clean_text("🌙 夜间免打扰模式中"), font=font_main, fill=(0, 0, 0), anchor="mm")
        draw.text((width // 2, 190), "休眠时段结束后自动恢复常规排程", font=font_sub, fill=(255, 0, 0), anchor="mm")
        _sleep_image_cache = image_to_raw(img, width, height)
    return _sleep_image_cache
