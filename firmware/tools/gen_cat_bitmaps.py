"""Build PROGMEM 1-bit sprites from repo-root ref_cat.png."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "ref_cat.png"
OUT_H = ROOT / "firmware" / "KatBot" / "cat_bitmaps.h"
PREVIEW = ROOT / "firmware" / "build" / "oled_preview"

CAT_W = 40
CAT_H = 46
SCALE = 4


def cell_lum(im: Image.Image, cx: int, cy: int) -> float:
    lums: list[float] = []
    for yy in range(cy, cy + SCALE):
        for xx in range(cx, cx + SCALE):
            r, g, b, a = im.getpixel((xx, yy))
            if a >= 16:
                lums.append((r + g + b) / 3.0)
    return sum(lums) / len(lums) if lums else -1.0


def sample_grid() -> list[list[int]]:
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    gw, gh = w // SCALE, h // SCALE
    grid = [[cell_lum(im, x * SCALE, y * SCALE) for x in range(gw)] for y in range(gh)]
    minx = gw
    miny = gh
    maxx = -1
    maxy = -1
    for y in range(gh):
        for x in range(gw):
            if grid[y][x] >= 5:
                minx = min(minx, x)
                miny = min(miny, y)
                maxx = max(maxx, x)
                maxy = max(maxy, y)
    srcw = maxx - minx + 1
    srch = maxy - miny + 1
    bits = [[0] * CAT_W for _ in range(CAT_H)]
    hi = [[0] * CAT_W for _ in range(CAT_H)]
    for y in range(CAT_H):
        for x in range(CAT_W):
            sx = min(srcw - 1, int(x * srcw / CAT_W))
            sy = min(srch - 1, int(y * srch / CAT_H))
            v = grid[miny + sy][minx + sx]
            if v >= 5:
                bits[y][x] = 1
            if v >= 90:
                hi[y][x] = 1
    return bits, hi


def clone(bits: list[list[int]]) -> list[list[int]]:
    return [row[:] for row in bits]


EYES = ((10, 19), (23, 19))


def fill_disk(bits: list[list[int]], cx: int, cy: int, r: int, val: int = 1) -> None:
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r:
                put(bits, x, y, val)


def clear_eye_area(bits: list[list[int]]) -> None:
    for cx, cy in EYES:
        fill_disk(bits, cx, cy, 5, 0)


def draw_eyes(
    bits: list[list[int]],
    *,
    radius: int = 4,
    pupil_dx: int = 0,
    pupil_dy: int = 0,
    closed: bool = False,
) -> None:
    clear_eye_area(bits)
    if closed:
        for cx, cy in EYES:
            for x in range(cx - 3, cx + 4):
                put(bits, x, cy, 1)
        return
    for cx, cy in EYES:
        fill_disk(bits, cx, cy, radius, 1)
        px, py = cx + pupil_dx, cy + 1 + pupil_dy
        fill_disk(bits, px, py, 1, 0)
        put(bits, cx - 1, cy - 2, 1)


def put(bits: list[list[int]], x: int, y: int, val: int = 1) -> None:
    if 0 <= x < CAT_W and 0 <= y < CAT_H:
        bits[y][x] = val


def open_mouth(bits: list[list[int]]) -> None:
    # Small U mouth in the muzzle gap under the eyes.
    for x, y in (
        (16, 26),
        (17, 27),
        (18, 28),
        (19, 28),
        (20, 28),
        (21, 27),
        (22, 26),
        (18, 27),
        (19, 27),
        (20, 27),
    ):
        put(bits, x, y, 1)


def alert_ears(bits: list[list[int]]) -> None:
    for x, y in ((7, 0), (8, 0), (32, 0), (33, 0), (6, 1), (34, 1)):
        put(bits, x, y, 1)


def shift_tail(bits: list[list[int]], dy: int) -> list[list[int]]:
    out = clone(bits)
    for y in range(CAT_H):
        for x in range(28, CAT_W):
            out[y][x] = 0
    for y in range(CAT_H):
        for x in range(28, CAT_W):
            if bits[y][x]:
                put(out, x, y + dy, 1)
    return out


def pack(bits: list[list[int]]) -> list[int]:
    row_bytes = (CAT_W + 7) // 8
    data: list[int] = []
    for y in range(CAT_H):
        for b in range(row_bytes):
            v = 0
            for bit in range(8):
                x = b * 8 + bit
                if x < CAT_W and bits[y][x]:
                    v |= 0x80 >> bit
            data.append(v)
    return data


def save_preview(name: str, bits: list[list[int]]) -> None:
    PREVIEW.mkdir(parents=True, exist_ok=True)
    im = Image.new("1", (CAT_W, CAT_H), 0)
    for y in range(CAT_H):
        for x in range(CAT_W):
            im.putpixel((x, y), 1 if bits[y][x] else 0)
    im.resize((CAT_W * 4, CAT_H * 4), Image.Resampling.NEAREST).save(PREVIEW / f"{name}.png")


def c_array(name: str, data: list[int]) -> str:
    lines = [f"static const uint8_t PROGMEM {name}[] = {{"]
    row_bytes = (CAT_W + 7) // 8
    for y in range(CAT_H):
        chunk = data[y * row_bytes : (y + 1) * row_bytes]
        lines.append("  " + ", ".join(f"0x{v:02X}" for v in chunk) + ",")
    lines.append("};")
    return "\n".join(lines)


def main() -> None:
    base, _hi = sample_grid()
    idle = clone(base)
    draw_eyes(idle)

    idle2 = shift_tail(idle, -1)

    blink = clone(base)
    draw_eyes(blink, closed=True)

    listen = clone(base)
    draw_eyes(listen, radius=5)
    alert_ears(listen)

    think = clone(base)
    draw_eyes(think, pupil_dy=-1)

    speak = clone(base)
    draw_eyes(speak)
    open_mouth(speak)

    wifi = clone(base)
    draw_eyes(wifi, pupil_dx=-1)

    poses = {
        "cat_idle": idle,
        "cat_idle2": idle2,
        "cat_blink": blink,
        "cat_listen": listen,
        "cat_think": think,
        "cat_speak": speak,
        "cat_wifi": wifi,
    }
    for name, bits in poses.items():
        save_preview(name, bits)

    body = [
        "#pragma once",
        "#include <Arduino.h>",
        "",
        f"#define CAT_BMP_W {CAT_W}",
        f"#define CAT_BMP_H {CAT_H}",
        "",
    ]
    for name, bits in poses.items():
        body.append(c_array(name, pack(bits)))
        body.append("")
    OUT_H.write_text("\n".join(body), encoding="utf-8")
    print("wrote", OUT_H)
    print("previews", PREVIEW)


if __name__ == "__main__":
    main()
