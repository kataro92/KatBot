"""Tests for tool routing and spoken fallbacks."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.music import looks_music, music_query
from app.tools import looks_time, run_tools
from app.web_search import spoken_from_context


def _check(cond: bool, name: str) -> int:
    if cond:
        print("PASS", name)
        return 0
    print("FAIL", name)
    return 1


def main() -> int:
    fail = 0
    fail += _check(looks_music("phát nhạc sơn tùng"), "music intent")
    fail += _check(music_query("phát nhạc sơn tùng") == "sơn tùng", "music query")
    fail += _check(looks_music("hãy phát"), "hay phat")
    fail += _check(looks_music("hãy hát"), "hay hat")
    fail += _check(looks_music("phát bài hát"), "phat bai hat")
    fail += _check(looks_music("hát bài"), "hat bai")
    fail += _check(looks_music("hát bài sơn tùng"), "hat bai artist")
    fail += _check(looks_music("hay phat bai hat con mua"), "folded hay phat")
    fail += _check(looks_music("mở nhạc"), "mo nhac")
    fail += _check("cơn mưa" in music_query("hãy phát bài hát cơn mưa"), "query hay phat title")
    fail += _check("sơn tùng" in music_query("hát bài sơn tùng"), "query hat bai artist")
    fail += _check(not looks_music("phát triển kinh tế"), "phat trien not music")
    fail += _check(not looks_music("thời tiết hôm nay"), "weather not music")
    fail += _check(looks_time("bây giờ mấy giờ"), "time intent")
    fail += _check(
        spoken_from_context("- Thời tiết Hà Nội lúc x: 27°C (https://x)") == "Thời tiết Hà Nội lúc x: 27°C",
        "spoken strip url",
    )

    fail += _check(run_tools("nhiệt độ bao nhiêu").kind == "none", "local sensor no weather tool")

    weather = run_tools("thời tiết hôm nay")
    print("\n----- thời tiết hôm nay")
    print(weather.kind, weather.spoken)
    fail += _check(weather.kind == "weather" and weather.spoken and "°C" in weather.spoken, "live weather tool")

    clock = run_tools("bây giờ mấy giờ")
    print("----- giờ", clock.spoken)
    fail += _check(clock.kind == "time" and clock.spoken and "Bây giờ" in clock.spoken, "time tool")

    if fail:
        print(f"\n{fail} failed")
        return 1
    print("\nAll tool tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
