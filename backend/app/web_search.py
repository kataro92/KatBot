"""Fresh answers without an API key: weather, FX, Wikipedia, news, then web."""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from urllib.parse import quote

import httpx

from .config import settings

log = logging.getLogger("meobot.web_search")

_HTTP_TIMEOUT = 8.0
_UA = "KatBot/1.0 (local Arduino chatbot; educational)"

_FILLER_RE = re.compile(
    r"\b(tìm kiếm|tim kiem|search|google|wikipedia|wiki|"
    r"cho biết|cho biet|tra cứu|tra cuu|giúp mình|giup minh|"
    r"trên mạng|tren mang|trên web|tren web)\b",
    re.I,
)
_QUESTION_RE = re.compile(
    r"\b(là gì|la gi|là ai|la ai|thế nào|the nao|như thế nào|nhu the nao)\b",
    re.I,
)
_FRESH_RE = re.compile(
    r"\b(hôm nay|hom nay|hiện tại|hien tai|mới nhất|moi nhat|latest|now)\b",
    re.I,
)
_NEWS_RE = re.compile(
    r"\b(tin tức|tin tuc|news|bóng đá|bong da)\b",
    re.I,
)
_WEATHER_RE = re.compile(
    r"\b(thời tiết|thoi tiet|nhiệt độ|nhiet do|mưa|mua|nắng|nang|"
    r"dự báo|du bao|độ ẩm|do am)\b",
    re.I,
)
_FX_RE = re.compile(
    r"\b(tỷ giá|ty gia|usd|vnd|dollar|đô la|do la|euro|yen|forex|nhdt)\b",
    re.I,
)

# Longest match first. Values are Open-Meteo geocoding names.
_CITIES: tuple[tuple[str, str], ...] = (
    ("ho chi minh", "Ho Chi Minh City"),
    ("thanh pho ho chi minh", "Ho Chi Minh City"),
    ("tp. ho chi minh", "Ho Chi Minh City"),
    ("tp ho chi minh", "Ho Chi Minh City"),
    ("tp.hcm", "Ho Chi Minh City"),
    ("tp hcm", "Ho Chi Minh City"),
    ("sai gon", "Ho Chi Minh City"),
    ("ha noi", "Ha Noi"),
    ("hanoi", "Ha Noi"),
    ("da nang", "Da Nang"),
    ("hai phong", "Hai Phong"),
    ("can tho", "Can Tho"),
    ("nha trang", "Nha Trang"),
    ("vung tau", "Vung Tau"),
    ("quy nhon", "Quy Nhon"),
    ("thai nguyen", "Thai Nguyen"),
    ("nam dinh", "Nam Dinh"),
    ("ha long", "Ha Long"),
    ("da lat", "Da Lat"),
    ("bien hoa", "Bien Hoa"),
    ("hue", "Hue"),
    ("vinh", "Vinh"),
)

_WMO = {
    0: "trời quang",
    1: "chủ yếu quang mây",
    2: "mây rải rác",
    3: "nhiều mây",
    45: "sương mù",
    48: "sương mù đóng băng",
    51: "mưa phùn nhẹ",
    53: "mưa phùn",
    55: "mưa phùn đậm",
    61: "mưa nhỏ",
    63: "mưa vừa",
    65: "mưa to",
    71: "tuyết nhẹ",
    73: "tuyết",
    75: "tuyết to",
    80: "mưa rào",
    81: "mưa rào vừa",
    82: "mưa rào mạnh",
    95: "dông",
    96: "dông có mưa đá",
    99: "dông mạnh có mưa đá",
}


def _fold(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn").lower()


def _clean_query(query: str) -> str:
    t = _FILLER_RE.sub(" ", query)
    t = _QUESTION_RE.sub(" ", t)
    t = _FRESH_RE.sub(" ", t)
    t = _NEWS_RE.sub(" ", t)
    t = re.sub(r"[?!.]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or query.strip()


def _news_query(query: str) -> str:
    t = _FILLER_RE.sub(" ", query)
    t = re.sub(r"[?!.]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or query.strip()


def _looks_weather(query: str) -> bool:
    return bool(_WEATHER_RE.search(query) or _WEATHER_RE.search(_fold(query)))


def _looks_fx(query: str) -> bool:
    return bool(_FX_RE.search(query) or _FX_RE.search(_fold(query)))


def _looks_news(query: str) -> bool:
    return bool(_NEWS_RE.search(query) or _NEWS_RE.search(_fold(query)))


def _looks_fresh(query: str) -> bool:
    return bool(_FRESH_RE.search(query) or _FRESH_RE.search(_fold(query)))


def _weather_city(query: str) -> str | None:
    folded = f" {_fold(query)} "
    for needle, city in _CITIES:
        if f" {needle} " in folded or folded.strip() == needle:
            return city
    if _looks_weather(query):
        # "thanh pho"/"tinh" alone is not a place; skip geocode noise.
        return None
    return None


def _tokens(query: str) -> set[str]:
    folded = _fold(query)
    toks = {t for t in re.findall(r"[a-z0-9]+", folded) if len(t) > 2}
    if toks:
        return toks
    return {t for t in re.findall(r"[a-z0-9]+", folded) if len(t) >= 2}


def _relevant(query: str, title: str, body: str) -> bool:
    acronyms = re.findall(r"\b[A-Z]{2,5}\b", query)
    if acronyms:
        blob = f"{title} {body}"
        return any(a in blob for a in acronyms)
    toks = _tokens(query)
    if not toks:
        return True
    title_f = f" {_fold(title)} "
    short = len(_fold(query)) <= 4 or (len(toks) == 1 and all(len(t) <= 3 for t in toks))
    if short:
        return any(f" {t} " in title_f for t in toks)
    blob = _fold(f"{title} {body}")
    hits = sum(1 for t in toks if t in blob)
    return hits >= min(2, len(toks))


def _trim(text: str, n: int = 280) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= n:
        return t
    cut = t[: n - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


@lru_cache(maxsize=1)
def _primp_client():
    try:
        import primp
    except ImportError:
        return None
    return primp.Client(impersonate="random", timeout=int(_HTTP_TIMEOUT))


def _http() -> httpx.Client:
    return httpx.Client(
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )


def _weather(city: str) -> str | None:
    try:
        with _http() as client:
            geo = client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": "1", "language": "vi"},
            )
            geo.raise_for_status()
            results = geo.json().get("results") or []
            if not results:
                return None
            g = results[0]
            wx = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": g["latitude"],
                    "longitude": g["longitude"],
                    "current": (
                        "temperature_2m,relative_humidity_2m,"
                        "apparent_temperature,weather_code,wind_speed_10m"
                    ),
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "forecast_days": "1",
                    "timezone": g.get("timezone") or "Asia/Ho_Chi_Minh",
                },
            )
            wx.raise_for_status()
            data = wx.json()
    except Exception as exc:
        log.warning("Weather lookup failed: %s", exc)
        return None

    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(cur.get("weather_code") or 0)
    sky = _WMO.get(code, f"mã thời tiết {code}")
    name = g.get("name") or city
    line = (
        f"Thời tiết {name} lúc {cur.get('time', '?')}: "
        f"{cur.get('temperature_2m')}°C (cảm nhận {cur.get('apparent_temperature')}°C), "
        f"{sky}, ẩm {cur.get('relative_humidity_2m')}%, "
        f"gió {cur.get('wind_speed_10m')} km/h"
    )
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    if tmax is not None and tmin is not None:
        line += f". Trong ngày: {tmin}–{tmax}°C"
    return line


def _fx() -> str | None:
    try:
        with _http() as client:
            r = client.get("https://open.er-api.com/v6/latest/USD")
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        log.warning("FX lookup failed: %s", exc)
        return None
    if data.get("result") != "success":
        return None
    vnd = (data.get("rates") or {}).get("VND")
    if not vnd:
        return None
    updated = data.get("time_last_update_utc") or ""
    return f"Tỷ giá: 1 USD = {vnd:,.0f} VND (cập nhật {updated})".replace(",", ".")


def _wiki_lang(query: str, lang: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    last_exc: Exception | None = None
    hits: list[dict] = []
    for attempt in range(2):
        client = _primp_client()
        if client is None:
            return []
        try:
            r = client.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": str(max(limit, 3)),
                    "format": "json",
                    "utf8": "1",
                },
            )
            if r.status_code != 200:
                raise RuntimeError(f"wikipedia {lang} HTTP {r.status_code}")
            hits = (r.json().get("query") or {}).get("search") or []
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            _primp_client.cache_clear()
    if last_exc:
        log.info("Wikipedia search failed (%s): %s", lang, last_exc)
        return []
    if not hits:
        return []

    client = _primp_client()
    if client is None:
        return []

    out: list[str] = []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        try:
            s = client.get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
                + quote(title.replace(" ", "_"), safe="()_-")
            )
            if s.status_code != 200:
                continue
            page = s.json()
        except Exception:
            continue
        if page.get("type") == "disambiguation":
            continue
        extract = (page.get("extract") or page.get("description") or "").strip()
        page_title = (page.get("title") or title).strip()
        if not extract:
            continue
        # Keep the first hit; later hits must look related.
        if out and not _relevant(query, page_title, extract):
            continue
        url = ((page.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
        line = f"Wikipedia: {page_title} — {_trim(extract)}"
        if url:
            line += f" ({url})"
        out.append(line)
        if len(out) >= limit:
            break
    return out


def _wikipedia(query: str, limit: int) -> list[str]:
    hits = _wiki_lang(query, "vi", limit)
    if len(hits) < limit:
        hits.extend(_wiki_lang(query, "en", limit - len(hits)))
    return hits


def _ddg_instant(query: str) -> str | None:
    try:
        with _http() as client:
            r = client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        log.info("DuckDuckGo instant failed: %s", exc)
        return None

    heading = (data.get("Heading") or "").strip()
    abstract = (data.get("AbstractText") or "").strip()
    answer = re.sub(r"<[^>]+>", "", data.get("Answer") or "").strip()
    body = answer or abstract
    if not body:
        return None
    if heading.isupper() and 2 <= len(heading) <= 8 and heading.lower() != query.strip().lower():
        return None
    if heading and not _relevant(query, heading, body):
        return None
    label = heading or "DuckDuckGo"
    url = (data.get("AbstractURL") or "").strip()
    line = f"{label}: {_trim(body)}"
    if url:
        line += f" ({url})"
    return line


def _fmt_hit(item: dict, *, prefix: str = "") -> str | None:
    title = (item.get("title") or "").strip()
    body = (item.get("body") or item.get("snippet") or item.get("excerpt") or "").strip()
    href = (item.get("href") or item.get("url") or item.get("link") or "").strip()
    if not title and not body:
        return None
    line = title
    if body:
        line = f"{title}: {_trim(body)}" if title else _trim(body)
    if href:
        line = f"{line} ({href})"
    if prefix:
        line = f"{prefix}{line}"
    return line.strip()


def _ddgs_news(query: str, n: int) -> list[str]:
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    try:
        with DDGS(timeout=int(_HTTP_TIMEOUT)) as ddgs:
            items = ddgs.news(query, region=settings.web_search_region, max_results=max(n, 8))
    except Exception as exc:
        log.info("News search failed: %s", exc)
        return []
    raw: list[str] = []
    filtered: list[str] = []
    for item in items or []:
        line = _fmt_hit(item, prefix="Tin: ")
        if not line:
            continue
        raw.append(line)
        title = (item.get("title") or "").strip()
        body = (item.get("body") or item.get("excerpt") or "").strip()
        if _relevant(query, title, body):
            filtered.append(line)
        if len(filtered) >= n:
            break
    return (filtered or raw)[:n]


def _google_cse(query: str, n: int) -> list[str]:
    key = (settings.google_api_key or "").strip()
    cx = (settings.google_cse_id or "").strip()
    if not key or not cx:
        return []
    try:
        with _http() as client:
            r = client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": key,
                    "cx": cx,
                    "q": query,
                    "num": str(min(n, 10)),
                    "hl": "vi",
                    "gl": "vn",
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        log.info("Google CSE failed: %s", exc)
        return []
    out: list[str] = []
    for item in data.get("items") or []:
        line = _fmt_hit(
            {
                "title": item.get("title"),
                "body": (item.get("snippet") or ""),
                "href": item.get("link"),
            }
        )
        if line:
            out.append(line)
        if len(out) >= n:
            break
    return out


def _ddgs_text(query: str, n: int) -> list[str]:
    google = _google_cse(query, n)
    if google:
        return google
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    backends = ("startpage", "brave", "duckduckgo", "wikipedia")
    for backend in backends:
        try:
            with DDGS(timeout=int(_HTTP_TIMEOUT)) as ddgs:
                items = ddgs.text(
                    query,
                    region=settings.web_search_region,
                    max_results=n,
                    backend=backend,
                )
        except Exception as exc:
            log.info("Text search %s failed: %s", backend, exc)
            continue
        out: list[str] = []
        for item in items or []:
            line = _fmt_hit(item)
            if line:
                out.append(line)
        if out:
            return out
    return []


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = _fold(re.sub(r"\s+", " ", line))[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def search_web(query: str, max_results: int | None = None) -> str:
    q = (query or "").strip()
    if not q:
        return ""
    n = max_results or settings.web_search_max_results
    cleaned = _clean_query(q)
    city = None
    if _looks_weather(q):
        city = _weather_city(q) or (settings.weather_city or "Ha Noi").strip()
    structured = bool(city) or _looks_fx(q)
    news_intent = _looks_news(q)
    blocks: list[str] = []

    if city:
        w = _weather(city)
        if w:
            blocks.append(w)
    if _looks_fx(q):
        fx = _fx()
        if fx:
            blocks.append(fx)

    wiki_lines: list[str] = []
    if not structured and not news_intent:
        wiki_q = cleaned or q
        wiki_limit = 1 if _QUESTION_RE.search(q) else min(2, n)
        wiki_lines = _wikipedia(wiki_q, limit=wiki_limit)
        if not wiki_lines and wiki_q != q:
            wiki_lines = _wikipedia(q, limit=wiki_limit)
        if not wiki_lines:
            ia = _ddg_instant(wiki_q)
            if ia:
                wiki_lines.append(ia)

    news_lines: list[str] = []
    if not structured and (news_intent or _looks_fresh(q) or not (blocks or wiki_lines)):
        nq = cleaned or _news_query(q)
        if _looks_fresh(q) and "moi nhat" not in _fold(nq):
            nq = f"{nq} mới nhất".strip()
        news_lines = _ddgs_news(nq, n)

    if news_intent or _looks_fresh(q):
        blocks.extend(news_lines)
        blocks.extend(wiki_lines)
    else:
        blocks.extend(wiki_lines)
        blocks.extend(news_lines)

    if not blocks:
        blocks.extend(_ddgs_text(cleaned or q, n))

    blocks = _dedupe(blocks)[:n]
    if not blocks:
        return "Khong tim thay ket qua."
    return "\n".join(f"- {b}" for b in blocks)


def weather_answer(query: str) -> str | None:
    if not _looks_weather(query):
        return None
    city = _weather_city(query) or (settings.weather_city or "Ha Noi").strip()
    return _weather(city)


def fx_answer(query: str) -> str | None:
    if not _looks_fx(query):
        return None
    return _fx()


def spoken_from_context(context: str | None) -> str:
    if not context:
        return ""
    line = context.strip().splitlines()[0].lstrip("- ").strip()
    line = re.sub(r"\s*\(https?://[^)]+\)\s*", "", line)
    line = re.sub(r"^(Wikipedia|Tin|DuckDuckGo):\s*", "", line)
    return _trim(line, 180)
