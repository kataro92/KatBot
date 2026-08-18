"""Tests for web search helpers and live source quality."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.web_search import (  # noqa: E402
    _clean_query,
    _looks_fx,
    _looks_news,
    _looks_weather,
    _weather_city,
    search_web,
)


def _check(cond: bool, name: str) -> int:
    if cond:
        print("PASS", name)
        return 0
    print("FAIL", name)
    return 1


def test_helpers() -> int:
    fail = 0
    fail += _check(_clean_query("Python là gì") == "Python", "clean definition")
    fail += _check(_clean_query("tìm kiếm tin tức AI hôm nay") == "AI", "clean news")
    fail += _check(_weather_city("nhiệt độ Hà Nội hôm nay") == "Ha Noi", "city hanoi")
    fail += _check(_weather_city("thoi tiet Da Nang") == "Da Nang", "city danang")
    fail += _check(_weather_city("Python là gì") is None, "no city")
    fail += _check(_looks_weather("nhiệt độ Hà Nội hôm nay"), "weather intent")
    fail += _check(_looks_fx("tỷ giá USD hôm nay"), "fx intent")
    fail += _check(_looks_news("tin tức AI hôm nay"), "news intent")
    fail += _check(not _looks_weather("Python là gì"), "not weather")
    return fail


def test_live() -> int:
    fail = 0
    cases = [
        ("nhiệt độ Hà Nội hôm nay", ("°C", "Hà Nội", "Ha Noi")),
        ("thời tiết hôm nay", ("°C",)),
        ("tỷ giá USD hôm nay", ("USD", "VND")),
        ("Python là gì", ("lập trình", "programming")),
        ("tìm kiếm tin tức AI hôm nay", ("Tin:", "AI", "trí tuệ")),
        ("Tổng thống Mỹ hiện tại", ("Tổng thống", "Trump", "Hoa Kỳ", "president")),
    ]
    for query, needles in cases:
        try:
            result = search_web(query, max_results=5)
        except Exception as exc:
            print("FAIL live", query, exc)
            fail += 1
            continue
        print("\n-----", query)
        print(result)
        low = result.lower()
        if result.startswith("Khong tim thay") or not any(n.lower() in low for n in needles):
            print("FAIL live relevance", query)
            fail += 1
        else:
            print("PASS live", query)
    return fail


def main() -> int:
    fail = test_helpers()
    fail += test_live()
    if fail:
        print(f"\n{fail} failed")
        return 1
    print("\nAll web search tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
