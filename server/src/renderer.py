import math
import time
import os
from datetime import datetime
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


def fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "..."
    while text and draw.textlength(text + ellipsis, font=font) > max_width:
        text = text[:-1]
    return text + ellipsis if text else ""


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
                if gray < 165:
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
    sender_label = fit_text(draw, f"[{sender} {now_str}]", font_sub, width // 2)
    sender_width = draw.textlength(sender_label, font=font_sub)
    title = fit_text(draw, title, font_title, int(width - 45 - sender_width))
    draw.text((15, 12), title, font=font_title, fill=(255, 255, 255))
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

    max_lines = max(0, (height - 35 - start_y) // line_height)
    has_overflow = len(lines) > max_lines
    for i, line in enumerate(lines[:max_lines]):
        if has_overflow and i == max_lines - 1:
            line = fit_text(draw, line + "...", font_body, max_text_width)
        y_pos = start_y + i * line_height
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
    渲染日期卡片，避免分钟级内容变化导致墨水屏频繁全刷。
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
    draw.text((width // 2, 270), fit_text(draw, clean_text(info), font_tip, width - 40), font=font_tip, fill=(0, 0, 0), anchor="mm")

    return image_to_raw(img, width, height)


_SHARP_CACHE = {}


def _sharp_font(size: int):
    """文泉驿正黑点阵字 (Zen Hei Sharp, 内嵌 12~16px 手工点阵): 笔画恒为 1px，无抗锯齿，无粗细不均。"""
    if size not in _SHARP_CACHE:
        font = None
        for path in [os.path.join(LOCAL_FONTS_DIR, "wqy-zenhei.ttc"),
                     os.path.join(LOCAL_FONTS_DIR, "font.ttc"),
                     "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
                     "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size, index=2)
                    break
                except Exception:
                    continue
        _SHARP_CACHE[size] = font or get_font(size)
    return _SHARP_CACHE[size]


def _mono_big_font(size: int):
    for path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return get_font(size)


def _time_digit_font(size: int = 12, bold: bool = True):
    filename = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    for path in [
        os.path.join(LOCAL_FONTS_DIR, filename),
        os.path.join(LOCAL_FONTS_DIR, "DejaVuSansMono-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return get_font(size)


def render_weather_image(weather_data: dict, width: int = 400, height: int = 300) -> bytes:
    """
    400x300 原生点阵天气卡片 (报刊风):
    正文用 Zen Hei Sharp 点阵字 (关闭抗锯齿, 加粗=右移 1px 叠印); 大温度用 DejaVu Bold 关闭抗锯齿渲染。
    全程不缩放、不阈值化，红色仅用于左上角角标。
    """
    BLK, RED, WHT = (0, 0, 0), (255, 0, 0), (255, 255, 255)
    img = Image.new("RGB", (width, height), WHT)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"

    def T(xy, s, size=16, fill=BLK, bold=False, anchor="la"):
        f = _sharp_font(size)
        d.text(xy, s, font=f, fill=fill, anchor=anchor)
        if bold:
            d.text((xy[0] + 1, xy[1]), s, font=f, fill=fill, anchor=anchor)

    def big(xy, s, size):
        f = _mono_big_font(size)
        m = Image.new("L", (width, size * 2), 0)
        md = ImageDraw.Draw(m)
        md.fontmode = "1"
        md.text((0, size), s, font=f, fill=255, anchor="ls")
        bb = m.getbbox()
        if not bb:
            return 0
        m = m.crop(bb)
        img.paste(BLK, (xy[0], xy[1] - m.height // 2), m)
        return m.width

    def icon(x, y, size=46):
        cx, cy = x + size // 2, y + size // 2
        desc_ = desc
        if "晴" in desc_ and "云" not in desc_ and "阴" not in desc_:
            d.ellipse([(cx - 9, cy - 9), (cx + 9, cy + 9)], outline=BLK, width=2)
            for i in range(8):
                a = i * math.pi / 4
                d.line([(cx + math.cos(a) * 13, cy + math.sin(a) * 13),
                        (cx + math.cos(a) * 19, cy + math.sin(a) * 19)], fill=BLK, width=2)
        elif "雨" in desc_ or "雷" in desc_ or "雪" in desc_:
            d.ellipse([(cx - 15, cy - 8), (cx + 1, cy + 8)], outline=BLK, width=2)
            d.ellipse([(cx - 6, cy - 14), (cx + 12, cy + 4)], outline=BLK, width=2)
            d.ellipse([(cx + 4, cy - 8), (cx + 18, cy + 6)], outline=BLK, width=2)
            d.rectangle([(cx - 10, cy), (cx + 14, cy + 7)], fill=WHT)
            d.line([(cx - 12, cy + 8), (cx + 16, cy + 8)], fill=BLK, width=2)
            for rx in (cx - 8, cx + 1, cx + 10):
                d.line([(rx, cy + 12), (rx - 3, cy + 19)], fill=RED if ("雷" in desc_ or "大" in desc_) else BLK, width=2)
        elif "霾" in desc_ or "雾" in desc_ or "沙" in desc_:
            d.arc([(cx - 13, cy - 15), (cx + 13, cy + 5)], 180, 0, fill=BLK, width=2)
            for dy, hw in ((3, 16), (9, 12), (15, 16)):
                d.line([(cx - hw, cy + dy), (cx + hw, cy + dy)], fill=BLK, width=2)
        else:
            d.ellipse([(cx - 17, cy - 4), (cx - 1, cy + 12)], outline=BLK, width=2)
            d.ellipse([(cx - 7, cy - 14), (cx + 13, cy + 8)], outline=BLK, width=2)
            d.ellipse([(cx + 4, cy - 4), (cx + 19, cy + 11)], outline=BLK, width=2)
            d.rectangle([(cx - 11, cy + 2), (cx + 14, cy + 10)], fill=WHT)
            d.line([(cx - 12, cy + 12), (cx + 16, cy + 12)], fill=BLK, width=2)

    def hl(y, x0, x1, w=1):
        d.line([(x0, y), (x1, y)], fill=BLK, width=w)

    def vl(x, y0, y1):
        d.line([(x, y0), (x, y1)], fill=BLK, width=1)

    city = clean_text(weather_data.get("city", "天津")) or "天津"
    desc = clean_text(weather_data.get("weather_desc", "晴朗"))
    temp_c = str(weather_data.get("temp_c", "--"))
    feels = weather_data.get("feels_like_c", temp_c)
    humidity = weather_data.get("humidity", "--")
    wind = clean_text(weather_data.get("wind", "--"))
    parts = wind.split(" ", 1)
    wind_dir, wind_spd = parts[0], (parts[1] if len(parts) > 1 else "")
    t_min = weather_data.get("temp_min", "--")
    t_max = weather_data.get("temp_max", "--")

    # 报头
    now = datetime.now()
    wk = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    d.rectangle([(0, 0), (width - 1, 34)], fill=BLK)
    d.rectangle([(0, 0), (9, 34)], fill=RED)
    header_title = fit_text(d, f"天气早报 {city}", _sharp_font(16), 210)
    T((22, 17), header_title, 16, WHT, True, "lm")
    T((width - 14, 17), f"{now.strftime('%Y.%m.%d')} {wk}", 16, WHT, False, "rm")

    # 左栏
    vl(200, 46, 204)
    icon(20, 50)
    w = big((76, 74), temp_c, 50)
    T((76 + w + 4, 60), "℃", 16, bold=True)
    T((22, 116), fit_text(d, f"当前：{desc}", _sharp_font(16), 170), 16, bold=True)
    T((22, 142), f"温差：{t_min}℃ ~ {t_max}℃", 16)
    d.rectangle([(20, 168), (184, 198)], outline=BLK, width=1)
    try:
        tip = "天气湿冷 宜添衣" if int(float(feels)) <= 12 else ("天气炎热 注意防暑" if int(float(feels)) >= 30 else "体感舒适 出行愉快")
    except ValueError:
        tip = "出行请留意天气"
    if any(k in desc for k in ["雨", "雪", "雷"]):
        tip = "有降水 出行带伞"
    elif any(k in desc for k in ["霾", "雾", "沙"]):
        tip = "空气欠佳 宜戴口罩"
    T((102, 183), tip, 14, anchor="mm")

    # 右栏
    rows = [("体感温度", f"{feels}℃"), ("相对湿度", f"{humidity}%"), ("实时风向", wind_dir), ("风速", wind_spd or "--")]
    for i, (k, v) in enumerate(rows):
        y = 54 + i * 38
        T((214, y), k, 16)
        T((width - 16, y), v, 16, bold=True, anchor="ra")
        d.line([(214, y + 24), (width - 16, y + 24)], fill=BLK, width=1)

    # 预报
    hl(212, 0, width - 1, 2)
    for i, fc in enumerate(weather_data.get("forecast", [])[:3]):
        x = 14 + i * 130
        T((x, 226), clean_text(fc.get("label", "")), 16, bold=True)
        T((x + 44, 226), fit_text(d, clean_text(fc.get("desc", "")), _sharp_font(16), 74), 16)
        T((x, 252), f"{fc.get('temp_min', '-')}° ~ {fc.get('temp_max', '-')}°", 16)
        if i < 2:
            vl(x + 122, 222, 270)

    hl(278, 0, width - 1, 1)
    ut = str(weather_data.get("update_time", time.strftime("%H:%M")))
    try:
        hh, mm = ut.split(":")
        ut_txt = f"{int(hh)}时{int(mm)}分"
    except ValueError:
        ut_txt = ut
    T((width // 2, 289), f"更新于{ut_txt}" + (" (缓存)" if weather_data.get("stale") else ""), 14, anchor="mm")

    return image_to_raw(img, width, height)


def render_calendar_image(calendar_data: dict, width: int = 400, height: int = 300) -> bytes:
    """
    400x300 原生点阵日程看板 (报刊风格):
    - 严格 400x300 原生 1X 点阵，无抗锯齿，文字笔画锋利清晰
    - 报头: 黑色底色 + 红色角标，标题为「今日日程安排」(无城市名)，右侧显示公历日期与星期
    - 时段列表: 按时间先后排序，进行中事项带有红色指示条与 [进行中] 胶囊
    - 底部状态栏: iCal 同步状态与更新时间
    """
    BLK, RED, WHT = (0, 0, 0), (255, 0, 0), (255, 255, 255)
    img = Image.new("RGB", (width, height), WHT)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"

    def T(xy, s, size=16, fill=BLK, bold=False, anchor="la"):
        f = _sharp_font(size)
        d.text(xy, s, font=f, fill=fill, anchor=anchor)
        if bold:
            d.text((xy[0] + 1, xy[1]), s, font=f, fill=fill, anchor=anchor)

    def hl(y, x0=0, x1=width - 1, w=1, fill=BLK):
        d.line([(x0, y), (x1, y)], fill=fill, width=w)

    def vl(x, y0, y1, w=1, fill=BLK):
        d.line([(x, y0), (x, y1)], fill=fill, width=w)

    # 1. 顶部报头 (0 ~ 34px)
    now = datetime.now()
    wk = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    d.rectangle([(0, 0), (width - 1, 34)], fill=BLK)
    d.rectangle([(0, 0), (9, 34)], fill=RED)

    # 标题头：固定为「今日日程安排」
    T((22, 17), "今日日程安排", 16, WHT, True, "lm")
    T((width - 14, 17), f"{now.strftime('%Y.%m.%d')} {wk}", 16, WHT, False, "rm")

    events = calendar_data.get("events", [])

    # 2. 空日程状态
    if not events:
        icx, icy = width // 2, 115
        d.rectangle([(icx - 32, icy - 32), (icx + 32, icy + 32)], outline=BLK, width=2)
        d.rectangle([(icx - 32, icy - 32), (icx + 32, icy - 14)], fill=BLK)
        # 红色装订环
        d.rectangle([(icx - 20, icy - 38), (icx - 14, icy - 26)], fill=RED)
        d.rectangle([(icx + 14, icy - 38), (icx + 20, icy - 26)], fill=RED)
        # 日期数字
        T((icx, icy + 10), str(now.day), 24, BLK, True, "mm")

        T((width // 2, 185), "今日暂无日程安排", 16, BLK, True, "mm")
        T((width // 2, 214), "享受专注与从容的自由时光", 14, BLK, False, "mm")

    else:
        # 3. 日程列表 (最多展示 4~5 项)
        max_show = 4
        display_events = events[:max_show]
        has_more = len(events) > max_show

        slot_height = 58
        y_start = 38

        for i, ev in enumerate(display_events):
            cur_y = y_start + i * slot_height
            is_ongoing = ev.get("is_ongoing", False)
            is_all_day = ev.get("is_all_day", False)
            title = clean_text(ev.get("title", "未命名日程"))
            loc = clean_text(ev.get("location", ""))
            desc = clean_text(ev.get("description", ""))

            # 时间文本
            if is_all_day:
                time_str = "全天"
            else:
                st = ev.get("start_time", "--:--")
                et = ev.get("end_time", "")
                time_str = f"{st} - {et}" if et else st

            # 进行中指示：左侧指示条与胶囊标牌
            time_x = 18
            divider_x = 118
            title_x = 126

            if is_ongoing:
                d.rectangle([(10, cur_y + 3), (14, cur_y + slot_height - 9)], fill=RED)
                d.rectangle([(width - 64, cur_y + 4), (width - 12, cur_y + 22)], fill=RED)
                T((width - 38, cur_y + 13), "进行中", 14, WHT, True, "mm")
                title_max_w = width - title_x - 56
            else:
                d.rectangle([(10, cur_y + 5), (13, cur_y + slot_height - 11)], fill=BLK)
                title_max_w = width - title_x - 16

            # 时间列：数字使用专业等宽点阵数字字体，彻底避免冒号与数字粘连
            if is_all_day:
                T((time_x, cur_y + 5), time_str, 14, BLK, bold=is_ongoing)
            else:
                t_font = _time_digit_font(12, bold=True)
                d.text((time_x, cur_y + 6), time_str, font=t_font, fill=BLK)

            # 竖向细分隔线 (x: 118)
            vl(divider_x, cur_y + 6, cur_y + slot_height - 12, w=1, fill=BLK)

            # 标题 (文泉驿正黑内嵌点阵 16px)
            fitted_title = fit_text(d, title, _sharp_font(16), title_max_w)
            T((title_x, cur_y + 4), fitted_title, 16, BLK, bold=True)

            # 地点 / 补充说明 (x: 126)
            detail = loc if loc else desc
            if detail:
                sub_text = fit_text(d, f"地点: {detail}" if loc else detail, _sharp_font(14), width - title_x - 16)
                T((title_x, cur_y + 28), sub_text, 14, BLK, False)
            elif is_all_day:
                T((title_x, cur_y + 28), "全天安排", 14, BLK, False)

            # 槽间横向细分割线
            if i < len(display_events) - 1:
                hl(cur_y + slot_height - 4, 10, width - 10, 1)

        if has_more:
            remain = len(events) - max_show
            T((width - 14, y_start + max_show * slot_height - 8), f"+ 还有 {remain} 项日程...", 12, BLK, False, "ra")

    # 4. 底部状态栏 (276 ~ 300px)
    hl(276, 0, width - 1, 1)
    d.rectangle([(0, 277), (width - 1, height - 1)], fill=WHT)

    is_mock = calendar_data.get("is_mock", False)
    stale = calendar_data.get("stale", False)
    status = calendar_data.get("status", "ok")
    ut = calendar_data.get("update_time", now.strftime("%H:%M"))
    total_cnt = len(events)

    if status == "error":
        err_detail = calendar_data.get("error_detail") or calendar_data.get("message", "网络连接异常")
        if total_cnt == 0:
            status_text = f"● 同步异常({err_detail[:18]}) · 更新于 {ut}"
        else:
            status_text = f"● 离线缓存({total_cnt}项) · 同步异常({err_detail[:14]})"
    elif is_mock:
        status_text = f"● 模拟日程({total_cnt}项) · 未配置URL · {ut}"
    elif total_cnt == 0:
        status_text = f"● 今日暂无日程 · 更新于 {ut}"
    elif stale:
        status_text = f"● 今日共 {total_cnt} 项日程 · 更新于 {ut} (离线缓存)"
    else:
        status_text = f"● 今日共 {total_cnt} 项日程 · 更新于 {ut}"

    T((14, 288), status_text, 14, BLK, False, "lm")
    # 已移除右下角任何无意义字符

    return image_to_raw(img, width, height)

