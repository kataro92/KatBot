"""Unit tests for sensor/web context helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.context import (
    build_system_prompt,
    compose_from_facts,
    enrich_user_message,
    mentions_local_sensor,
    sensor_summary,
    wants_web_search,
)
from app.hub import hub


def main() -> int:
    fail = 0

    hub.temp = 26.5
    hub.humidity = 55.0
    hub.device_online = True
    hub.state = "idle"

    s = sensor_summary() or ""
    if "26.5" not in s or "55" not in s:
        print("FAIL sensor_summary", s)
        fail += 1
    else:
        print("PASS sensor_summary")

    prompt = build_system_prompt()
    if "26.5" not in prompt or "DHT11" not in prompt:
        print("FAIL build_system_prompt", prompt[:120])
        fail += 1
    else:
        print("PASS build_system_prompt")

    if not mentions_local_sensor("nhiệt độ bao nhiêu"):
        print("FAIL mentions_local_sensor")
        fail += 1
    else:
        print("PASS mentions_local_sensor")

    if wants_web_search("nhiệt độ bao nhiêu"):
        print("FAIL wants_web_search local")
        fail += 1
    else:
        print("PASS wants_web_search local")

    if not wants_web_search("tìm kiếm tin tức AI hôm nay"):
        print("FAIL wants_web_search news")
        fail += 1
    else:
        print("PASS wants_web_search news")

    if not wants_web_search("nhiệt độ Hà Nội hôm nay"):
        print("FAIL wants_web_search city weather")
        fail += 1
    else:
        print("PASS wants_web_search city weather")

    if not wants_web_search("thời tiết hôm nay"):
        print("FAIL wants_web_search weather today")
        fail += 1
    else:
        print("PASS wants_web_search weather today")

    if not wants_web_search("Sơn Tùng MTP là ai"):
        print("FAIL wants_web_search la ai")
        fail += 1
    else:
        print("PASS wants_web_search la ai")

    composed = compose_from_facts(
        "thời tiết hôm nay",
        "- Thời tiết Hà Nội lúc 06:00: 26.1°C, mưa rào vừa",
    )
    if (
        "Câu hỏi của người dùng" in composed
        and "thời tiết hôm nay" in composed
        and "26.1°C" in composed
        and "Thông tin đã tìm được" in composed
    ):
        print("PASS compose_from_facts")
    else:
        print("FAIL compose_from_facts", composed[:200])
        fail += 1

    enriched = enrich_user_message("ai là chủ tịch nước", "- Lương Cường")
    if "ai là chủ tịch nước" not in enriched or "Lương Cường" not in enriched:
        print("FAIL enrich_user_message search", enriched[:200])
        fail += 1
    else:
        print("PASS enrich_user_message search")

    if enrich_user_message("xin chào") != "xin chào":
        print("FAIL enrich_user_message plain")
        fail += 1
    else:
        print("PASS enrich_user_message plain")

    if fail:
        print(f"{fail} failed")
        return 1
    print("All context tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
