"""Route a user utterance to weather, FX, time, music, or web search."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .context import mentions_local_sensor, wants_web_search
from .music import fetch_track_pcm, looks_music, music_query
from .web_search import fx_answer, spoken_from_context, weather_answer, search_web
from .web_search import _fold, _looks_fx, _looks_weather, _weather_city

log = logging.getLogger("meobot.tools")

_TIME_RE = re.compile(
    r"\b(mấy giờ|may gio|bây giờ|bay gio|ngày bao nhiêu|ngay bao nhieu|"
    r"hôm nay ngày|hom nay ngay|thứ mấy|thu may)\b",
    re.I,
)


@dataclass
class ToolResult:
    kind: str
    context: str | None = None
    spoken: str | None = None
    music_pcm: bytes | None = None
    music_title: str | None = None


def looks_time(text: str) -> bool:
    return bool(_TIME_RE.search(text or ""))


def _time_answer() -> str:
    now = datetime.now(timezone(timedelta(hours=7)))
    weekdays = (
        "thứ hai",
        "thứ ba",
        "thứ tư",
        "thứ năm",
        "thứ sáu",
        "thứ bảy",
        "chủ nhật",
    )
    wd = weekdays[now.weekday()]
    return f"Bây giờ {now:%H:%M}, {wd} ngày {now.day} tháng {now.month} năm {now.year}."


def run_tools(text: str, *, search_enabled: bool = True) -> ToolResult:
    q = (text or "").strip()
    if not q:
        return ToolResult(kind="none")

    if looks_music(q):
        query = music_query(q)
        try:
            title, pcm = fetch_track_pcm(query)
        except Exception as exc:
            log.warning("Music tool failed: %s", exc)
            return ToolResult(
                kind="music",
                spoken=f"Chưa phát được nhạc: {exc}",
            )
        return ToolResult(
            kind="music",
            spoken=f"Đang phát {title}",
            music_pcm=pcm,
            music_title=title,
        )

    if looks_time(q) and not _looks_weather(q) and not _looks_fx(q):
        spoken = _time_answer()
        return ToolResult(kind="time", context=spoken, spoken=spoken)

    folded = _fold(q)
    outdoor = "thoi tiet" in folded or "ngoai troi" in folded or bool(_weather_city(q))
    if mentions_local_sensor(q) and not outdoor and not _looks_fx(q):
        return ToolResult(kind="none")

    if outdoor and _looks_weather(q):
        w = weather_answer(q)
        if w:
            return ToolResult(kind="weather", context=w, spoken=w)
        return ToolResult(kind="weather", spoken="Chưa lấy được thời tiết.")

    if _looks_fx(q):
        fx = fx_answer(q)
        if fx:
            return ToolResult(kind="fx", context=fx, spoken=fx)
        return ToolResult(kind="fx", spoken="Chưa lấy được tỷ giá.")

    if wants_web_search(q, enabled=search_enabled):
        ctx = search_web(q)
        spoken = spoken_from_context(ctx)
        if ctx.startswith("Khong tim thay"):
            spoken = "Không tìm thấy kết quả."
        return ToolResult(kind="search", context=ctx, spoken=spoken)

    return ToolResult(kind="none")
