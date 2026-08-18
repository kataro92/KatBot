"""Sensor + web context injected into Ollama chat."""

from __future__ import annotations

from .config import SYSTEM_PROMPT_VI
from .hub import hub

_LOCAL_HINTS = (
    "nhiệt",
    "nhiet",
    "độ ẩm",
    "do am",
    "humid",
    "cảm biến",
    "cam bien",
    "dht",
    "trong phòng",
    "trong phong",
    "ở đây",
    "o day",
    "tại chỗ",
    "tai cho",
    "trong nhà",
    "trong nha",
    "mấy độ",
    "may do",
    "bao nhiêu độ",
    "bao nhieu do",
)

_WEB_HINTS = (
    "tìm kiếm",
    "tim kiem",
    "search",
    "google",
    "web",
    "internet",
    "tin tức",
    "tin tuc",
    "mới nhất",
    "moi nhat",
    "latest",
    "news",
    "wiki",
    "wikipedia",
    "tỷ giá",
    "ty gia",
    "giá ",
    "gia ",
    "hôm nay",
    "hom nay",
    "bóng đá",
    "bong da",
    "ai là",
    "ai la",
    "là ai",
    "la ai",
    "là gì",
    "la gi",
    "cho biết",
    "cho biet",
    "tra cứu",
    "tra cuu",
    "thời tiết",
    "thoi tiet",
)

_CITY_HINTS = (
    "hà nội",
    "ha noi",
    "sài gòn",
    "sai gon",
    "hồ chí minh",
    "ho chi minh",
    "đà nẵng",
    "da nang",
    "thành phố",
    "thanh pho",
    "tỉnh",
    "tinh ",
    "ngoài trời",
    "ngoai troi",
)


def sensor_summary() -> str | None:
    if hub.temp is None and hub.humidity is None:
        if not hub.device_online:
            return "ESP chua ket noi, chua co so lieu DHT11"
        return "ESP online nhung chua doc duoc DHT11"
    parts: list[str] = []
    if hub.temp is not None:
        parts.append(f"nhiet do {hub.temp:.1f}°C")
    if hub.humidity is not None:
        parts.append(f"do am {hub.humidity:.0f}%")
    online = "online" if hub.device_online else "offline"
    state = hub.state or "unknown"
    return f"{', '.join(parts)} (ESP {online}, trang thai {state})"


def build_system_prompt() -> str:
    prompt = (
        f"{SYSTEM_PROMPT_VI} "
        "Ban la Meo Bot co cam bien DHT11 tren ESP-12F. "
        "Khi user hoi nhiet do hoac do am trong phong/tai cho, tra loi bang so lieu cam bien hien tai. "
        "Neu chua co so lieu, noi ro la chua do duoc."
    )
    reading = sensor_summary()
    if reading:
        prompt += f" So lieu cam bien hien tai: {reading}."
    return prompt


def mentions_local_sensor(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in _LOCAL_HINTS)


def wants_web_search(text: str, *, enabled: bool = True) -> bool:
    if not enabled:
        return False
    t = (text or "").lower().strip()
    if not t:
        return False
    has_city = any(c in t for c in _CITY_HINTS)
    if mentions_local_sensor(t) and not has_city and not any(h in t for h in _WEB_HINTS):
        return False
    if any(h in t for h in _WEB_HINTS):
        return True
    if has_city and any(
        w in t
        for w in (
            "thoi tiet",
            "thời tiết",
            "nhiệt",
            "nhiet",
            "mưa",
            "mua",
            "hôm nay",
            "hom nay",
        )
    ):
        return True
    if "?" in t and len(t) > 18:
        return True
    return False


def compose_from_facts(user_text: str, facts: str) -> str:
    q = (user_text or "").strip()
    info = (facts or "").strip()
    return (
        f"Câu hỏi của người dùng:\n{q}\n\n"
        f"Thông tin đã tìm được:\n{info}\n\n"
        "Hãy viết một câu trả lời hoàn chỉnh, tự nhiên, dễ thương bằng tiếng Việt để đọc thành tiếng. "
        "Chỉ dùng thông tin trên. Không bịa. Không nêu link. Không nói rằng bạn đang tìm kiếm. "
        "Chỉ nói câu trả lời."
    )


def enrich_user_message(user_text: str, web_context: str | None = None) -> str:
    text = (user_text or "").strip()
    if web_context and web_context.strip():
        return compose_from_facts(text, web_context)
    return text
