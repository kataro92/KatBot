"""Generate architecture + wiring PNGs from the firmware pin map (not AI)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
FONT_REG = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")

BG = (250, 251, 252)
INK = (22, 26, 33)
MUTED = (90, 98, 110)
LINE = (40, 48, 60)
ACCENT = (40, 110, 190)
ESP = (36, 92, 160)
PC = (46, 125, 90)
WEB = (150, 95, 40)
WIRE = {
    "gnd": (40, 40, 40),
    "3v3": (200, 80, 40),
    "5v": (180, 30, 30),
    "sda": (40, 130, 190),
    "scl": (120, 70, 170),
    "dht": (40, 140, 90),
    "btn": (210, 150, 30),
    "mic": (30, 140, 150),
    "i2s": (180, 70, 120),
    "spk": (90, 90, 90),
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REG
    return ImageFont.truetype(str(path), size)


def rounded(draw: ImageDraw.ImageDraw, xy, r, fill, outline=None, width=2):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def center_text(draw, xy, text, f, fill=INK):
    x0, y0, x1, y1 = xy
    bbox = draw.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((x0 + x1 - tw) / 2, (y0 + y1 - th) / 2 - 2), text, font=f, fill=fill)


def arrow(draw, a, b, color, width=4):
    draw.line([a, b], fill=color, width=width)
    x0, y0 = a
    x1, y1 = b
    import math

    ang = math.atan2(y1 - y0, x1 - x0)
    L = 14
    for d in (2.6, -2.6):
        draw.line(
            [
                (x1, y1),
                (x1 - L * math.cos(ang + d), y1 - L * math.sin(ang + d)),
            ],
            fill=color,
            width=width,
        )


def draw_architecture() -> None:
    w, h = 1400, 780
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.text((48, 32), "KatBot — kiến trúc", font=font(36, True), fill=INK)

    # 3 big boxes only
    rounded(d, (60, 140, 420, 620), 22, (232, 240, 250), ESP, 4)
    d.text((88, 164), "1. Phần cứng", font=font(20, True), fill=ESP)
    rounded(d, (100, 220, 380, 360), 16, ESP, LINE, 2)
    center_text(d, (100, 220, 380, 360), "ESP-12F", font(28, True), (255, 255, 255))
    d.text((128, 390), "Mic  ·  Nút 5s  ·  OLED", font=font(18), fill=INK)
    d.text((128, 430), "DHT11  ·  Loa  ·  Amp I2S", font=font(18), fill=INK)
    d.text((128, 490), "Chỉ thu/phát + cảm biến.", font=font(16), fill=MUTED)
    d.text((128, 522), "Không chạy AI trên chip.", font=font(16), fill=MUTED)

    rounded(d, (500, 140, 900, 620), 22, (232, 246, 236), PC, 4)
    d.text((528, 164), "2. Máy tính", font=font(20, True), fill=PC)
    rounded(d, (540, 220, 860, 360), 16, PC, LINE, 2)
    center_text(d, (540, 220, 860, 360), "Backend + Ollama", font(24, True), (255, 255, 255))
    d.text((548, 390), "Nghe → chữ → trả lời → tiếng", font=font(18), fill=INK)
    d.text((548, 430), "Một phiên chat nóng.", font=font(18), fill=INK)
    d.text((548, 490), "Mọi xử lý nặng nằm ở đây.", font=font(16), fill=MUTED)

    rounded(d, (980, 140, 1340, 620), 22, (250, 242, 228), WEB, 4)
    d.text((1008, 164), "3. Trình duyệt", font=font(20, True), fill=WEB)
    rounded(d, (1020, 220, 1300, 360), 16, WEB, LINE, 2)
    center_text(d, (1020, 220, 1300, 360), "Monitor", font(28, True), (255, 255, 255))
    d.text((1040, 390), "Xem trạng thái, DHT,", font=font(18), fill=INK)
    d.text((1040, 430), "nhật ký, chat thử.", font=font(18), fill=INK)
    d.text((1040, 490), "Chỉ nối tới PC.", font=font(16), fill=MUTED)
    d.text((1040, 522), "Không tải thêm ESP.", font=font(16), fill=MUTED)

    arrow(d, (420, 290), (500, 290), ACCENT, 6)
    d.text((428, 236), "Wi-Fi", font=font(16, True), fill=ACCENT)
    arrow(d, (900, 290), (980, 290), WEB, 6)
    d.text((908, 236), "HTTP/WS", font=font(16, True), fill=WEB)

    d.text(
        (60, 680),
        "Luồng nói:  Nút 5s  →  ESP  →  PC (Ollama)  →  ESP  →  Loa.    Monitor chỉ xem từ PC.",
        font=font(18),
        fill=MUTED,
    )
    im.save(OUT / "architecture.png", "PNG", optimize=True)


def pin_row(draw, pins, origin, side: str, pitch=34, used=None):
    """Draw a vertical pin header. origin is top pin center. Returns {name: (x,y)}."""
    ox, oy = origin
    f = font(13, True)
    coords = {}
    used = used or {}
    for i, name in enumerate(pins):
        y = oy + i * pitch
        x = ox
        highlight = name in used
        fill = used[name] if highlight else (245, 245, 245)
        outline = used[name] if highlight else (90, 90, 90)
        r = 8
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill, outline=outline, width=2)
        if side == "left":
            draw.text((x - 16, y - 9), name, font=f, fill=INK, anchor="ra")
        else:
            draw.text((x + 14, y - 9), name, font=f, fill=INK)
        coords[name] = (x, y)
    return coords


def module_box(draw, xy, title, pins, pin_colors):
    x0, y0, x1, y1 = xy
    rounded(draw, xy, 14, (255, 255, 255), LINE, 3)
    draw.text((x0 + 14, y0 + 10), title, font=font(18, True), fill=INK)
    coords = {}
    n = len(pins)
    gap = (x1 - x0 - 28) / max(n, 1)
    py = y1 - 28
    for i, name in enumerate(pins):
        px = x0 + 22 + i * gap
        color = pin_colors.get(name, (80, 80, 80))
        draw.ellipse((px - 8, py - 8, px + 8, py + 8), fill=color, outline=LINE, width=2)
        bbox = draw.textbbox((0, 0), name, font=font(12, True))
        tw = bbox[2] - bbox[0]
        draw.text((px - tw / 2, py - 28), name, font=font(12, True), fill=INK)
        coords[name] = (px, py)
    return coords


def draw_wiring() -> None:
    w, h = 2800, 1880
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.text((48, 28), "KatBot — sơ đồ cắm dây (NodeMCU v1.0 / ESP-12F)", font=font(34, True), fill=INK)
    d.text(
        (48, 78),
        "Đúng pin trong firmware/config.h. USB ở cạnh dưới. Đen = GND, cam = 3V3, đỏ = Vin 5V. Luôn theo chữ in trên module nếu thứ tự chân khác.",
        font=font(18),
        fill=MUTED,
    )

    used_colors = {
        "A0": WIRE["mic"],
        "D1": WIRE["scl"],
        "D2": WIRE["sda"],
        "D4": WIRE["i2s"],
        "D5": WIRE["dht"],
        "D6": WIRE["btn"],
        "RX": WIRE["i2s"],
        "D8": WIRE["i2s"],
        "3V3": WIRE["3v3"],
        "GND": WIRE["gnd"],
        "Vin": WIRE["5v"],
    }

    left_pins = [
        "A0",
        "RSV",
        "RSV",
        "SD3",
        "SD2",
        "SD1",
        "CMD",
        "SD0",
        "CLK",
        "GND",
        "3V3",
        "EN",
        "RST",
        "GND",
        "Vin",
    ]
    right_pins = [
        "D0",
        "D1",
        "D2",
        "D3",
        "D4",
        "3V3",
        "GND",
        "D5",
        "D6",
        "D7",
        "D8",
        "RX",
        "TX",
        "GND",
        "3V3",
    ]

    board = (1040, 160, 1760, 1180)
    rounded(d, board, 20, (226, 232, 238), LINE, 4)
    # USB
    rounded(d, (1280, 1148, 1520, 1220), 8, (40, 44, 50), LINE, 2)
    center_text(d, (1280, 1148, 1520, 1220), "USB", font(16, True), (255, 255, 255))
    # ESP can
    rounded(d, (1220, 200, 1580, 430), 8, (70, 78, 88), LINE, 2)
    center_text(d, (1220, 200, 1580, 380), "ESP-12F", font(22, True), (255, 255, 255))
    d.text((1320, 385), "NodeMCU v1.0", font=font(16), fill=(220, 220, 220))
    d.text((1260, 1088), "USB ở dưới — thứ tự chân NodeMCU v1.0", font=font(14), fill=MUTED)

    lp = pin_row(d, left_pins, (1088, 470), "left", pitch=42, used=used_colors)
    rp = pin_row(d, right_pins, (1712, 470), "right", pitch=42, used=used_colors)

    # Prefer specific physical pins for power that are closest to modules
    gnd_left = lp["GND"]  # first GND on left (next to CLK) — actually two GND on left
    # left GND appears twice; pin_row overwrites. Capture both:
    # Rebuild unique keys for duplicate names by indexing
    # We'll wire GND using nearest labeled GND on each side.

    # Re-walk to get all GND coords
    def header_coords(names, origin, side):
        ox, oy = origin
        out = []
        for i, name in enumerate(names):
            out.append((name, (ox, oy + i * 42)))
        return out

    left_all = header_coords(left_pins, (1088, 470), "left")
    right_all = header_coords(right_pins, (1712, 470), "right")
    left_gnds = [xy for n, xy in left_all if n == "GND"]
    right_gnds = [xy for n, xy in right_all if n == "GND"]
    left_3v3 = [xy for n, xy in left_all if n == "3V3"][0]
    right_3v3_top = [xy for n, xy in right_all if n == "3V3"][0]
    vin = lp["Vin"]

    # Modules
    oled = module_box(
        d,
        (1960, 160, 2680, 360),
        "SSD1306  0.96\"  JMD0.96D-1  (I2C  0x3C)",
        ["GND", "VCC", "SCL", "SDA"],
        {"GND": WIRE["gnd"], "VCC": WIRE["3v3"], "SCL": WIRE["scl"], "SDA": WIRE["sda"]},
    )
    d.text((1974, 318), "Thứ tự chân phổ biến JMD0.96D-1: GND–VCC–SCL–SDA. Nếu board in ngược VCC/GND thì theo chữ in.", font=font(13), fill=MUTED)

    amp = module_box(
        d,
        (1960, 420, 2680, 640),
        "MAX98357  (I2S amp)  +  loa 3W",
        ["VIN", "GND", "DIN", "BCLK", "LRC"],
        {"VIN": WIRE["5v"], "GND": WIRE["gnd"], "DIN": WIRE["i2s"], "BCLK": WIRE["i2s"], "LRC": WIRE["i2s"]},
    )
    d.text((1974, 598), "GAIN / SD để treo (mặc định). Loa chỉ cắm vào + − trên amp, không cắm vào ESP.", font=font(13), fill=MUTED)

    spk = module_box(
        d,
        (1960, 680, 2320, 820),
        "Loa 3W",
        ["+", "−"],
        {"+": WIRE["spk"], "−": WIRE["spk"]},
    )

    mic = module_box(
        d,
        (80, 160, 820, 380),
        "MAX9814  (mic analog)",
        ["OUT", "GND", "VDD", "GAIN", "A/R"],
        {"OUT": WIRE["mic"], "GND": WIRE["gnd"], "VDD": WIRE["3v3"], "GAIN": (180, 180, 180), "A/R": (180, 180, 180)},
    )
    d.text((94, 338), "GAIN và A/R không nối (mặc định). OUT tới A0 (ADC NodeMCU 0–3.3V).", font=font(13), fill=MUTED)

    dht = module_box(
        d,
        (80, 440, 820, 640),
        "DHT11  (module 3 chân, thường có trở kéo sẵn)",
        ["VCC", "DATA", "GND"],
        {"VCC": WIRE["3v3"], "DATA": WIRE["dht"], "GND": WIRE["gnd"]},
    )

    btn = module_box(
        d,
        (80, 700, 820, 900),
        "Nút nhấn  (active LOW, INPUT_PULLUP trong firmware)",
        ["D6", "GND"],
        {"D6": WIRE["btn"], "GND": WIRE["gnd"]},
    )
    d.text((94, 858), "Nút 4 chân: dùng 2 chân chéo. Nhấn nối D6 xuống GND. Không cần điện trở ngoài.", font=font(13), fill=MUTED)

    def wire(a, b, color, width=4, via=None):
        pts = [a]
        if via:
            pts.extend(via)
        pts.append(b)
        d.line(pts, fill=color, width=width)
        for p in (a, b):
            d.ellipse((p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4), fill=color)

    # OLED
    wire(oled["GND"], right_gnds[0], WIRE["gnd"], via=[(1860, oled["GND"][1]), (1860, right_gnds[0][1])])
    wire(oled["VCC"], right_3v3_top, WIRE["3v3"], via=[(1888, oled["VCC"][1]), (1888, right_3v3_top[1])])
    wire(oled["SCL"], rp["D1"], WIRE["scl"], via=[(1830, oled["SCL"][1]), (1830, rp["D1"][1])])
    wire(oled["SDA"], rp["D2"], WIRE["sda"], via=[(1808, oled["SDA"][1]), (1808, rp["D2"][1])])

    # Amp
    wire(amp["VIN"], vin, WIRE["5v"], via=[(1900, amp["VIN"][1]), (1900, 1240), (1088, 1240)])
    wire(amp["GND"], right_gnds[0], WIRE["gnd"], via=[(1860, amp["GND"][1]), (1860, right_gnds[0][1])])
    wire(amp["DIN"], rp["RX"], WIRE["i2s"], via=[(1844, amp["DIN"][1]), (1844, rp["RX"][1])])
    wire(amp["BCLK"], rp["D8"], WIRE["i2s"], via=[(1820, amp["BCLK"][1]), (1820, rp["D8"][1])])
    wire(amp["LRC"], rp["D4"], WIRE["i2s"], via=[(1796, amp["LRC"][1]), (1796, rp["D4"][1])])
    amp_plus = (2580, 500)
    amp_minus = (2640, 500)
    d.ellipse((amp_plus[0] - 7, amp_plus[1] - 7, amp_plus[0] + 7, amp_plus[1] + 7), fill=WIRE["spk"], outline=LINE)
    d.ellipse((amp_minus[0] - 7, amp_minus[1] - 7, amp_minus[0] + 7, amp_minus[1] + 7), fill=WIRE["spk"], outline=LINE)
    d.text((2568, 478), "+", font=font(14, True), fill=INK)
    d.text((2628, 478), "−", font=font(14, True), fill=INK)
    wire(spk["+"], amp_plus, WIRE["spk"], via=[(spk["+"][0], 650), (amp_plus[0], 650)])
    wire(spk["−"], amp_minus, WIRE["spk"], via=[(spk["−"][0], 665), (amp_minus[0], 665)])

    # Mic
    wire(mic["OUT"], lp["A0"], WIRE["mic"], via=[(900, mic["OUT"][1]), (900, lp["A0"][1])])
    wire(mic["GND"], left_gnds[0], WIRE["gnd"], via=[(930, mic["GND"][1]), (930, left_gnds[0][1])])
    wire(mic["VDD"], left_3v3, WIRE["3v3"], via=[(960, mic["VDD"][1]), (960, left_3v3[1])])

    # DHT
    wire(dht["VCC"], left_3v3, WIRE["3v3"], via=[(960, dht["VCC"][1]), (960, left_3v3[1])])
    wire(dht["DATA"], rp["D5"], WIRE["dht"], via=[(980, dht["DATA"][1]), (980, 1288), (1788, 1288), (1788, rp["D5"][1])])
    wire(dht["GND"], left_gnds[0], WIRE["gnd"], via=[(930, dht["GND"][1]), (930, left_gnds[0][1])])

    # Button — D6 is on the right header
    wire(btn["D6"], rp["D6"], WIRE["btn"], via=[(1000, btn["D6"][1]), (1000, 1320), (1766, 1320), (1766, rp["D6"][1])])
    wire(btn["GND"], left_gnds[1] if len(left_gnds) > 1 else left_gnds[0], WIRE["gnd"], via=[(910, btn["GND"][1]), (910, (left_gnds[1] if len(left_gnds) > 1 else left_gnds[0])[1])])

    # Table
    table_y = 1380
    rounded(d, (80, table_y, 2720, 1840), 16, (255, 255, 255), LINE, 2)
    d.text((100, table_y + 16), "Bảng nối chân (nguồn sự thật — ưu tiên bảng này nếu dây giao nhau)", font=font(22, True), fill=INK)

    rows = [
        ("SSD1306 GND", "GND", "chung mass"),
        ("SSD1306 VCC", "3V3", "3.3V"),
        ("SSD1306 SCL", "D1 / GPIO5", "I2C clock"),
        ("SSD1306 SDA", "D2 / GPIO4", "I2C data"),
        ("DHT11 VCC", "3V3", "module 3 chân"),
        ("DHT11 DATA", "D5 / GPIO14", "trở kéo sẵn trên module"),
        ("DHT11 GND", "GND", ""),
        ("Nút", "D6 / GPIO12  —  GND", "nhấn 1 lần = nghe 5 giây"),
        ("MAX9814 VDD", "3V3", "GAIN và A/R để trống"),
        ("MAX9814 GND", "GND", ""),
        ("MAX9814 OUT", "A0", "ADC NodeMCU"),
        ("MAX98357 VIN", "Vin (5V USB)", "công suất loa 3W"),
        ("MAX98357 GND", "GND", "chung mass"),
        ("MAX98357 DIN", "RX / GPIO3", "I2S phần cứng, không dùng Serial"),
        ("MAX98357 BCLK", "D8 / GPIO15", "GPIO15 phải LOW lúc boot"),
        ("MAX98357 LRC", "D4 / GPIO2", "WS / LRCLK"),
        ("Loa + / −", "MAX98357 + / −", "không nối loa thẳng vào ESP"),
    ]
    col_f = font(15)
    y = table_y + 60
    d.text((110, y), "Module", font=font(15, True), fill=MUTED)
    d.text((620, y), "NodeMCU", font=font(15, True), fill=MUTED)
    d.text((1180, y), "Ghi chú", font=font(15, True), fill=MUTED)
    y += 8
    d.line((100, y + 20, 2700, y + 20), fill=(220, 224, 230), width=1)
    y += 28
    for a, b, c in rows:
        d.text((110, y), a, font=col_f, fill=INK)
        d.text((620, y), b, font=col_f, fill=ESP)
        d.text((1180, y), c, font=col_f, fill=MUTED)
        y += 22

    im.save(OUT / "wiring.png", "PNG", optimize=True)


if __name__ == "__main__":
    draw_architecture()
    draw_wiring()
    print("wrote", OUT / "architecture.png")
    print("wrote", OUT / "wiring.png")
