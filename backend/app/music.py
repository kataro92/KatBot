"""Search a track and decode a short clip for the ESP speaker."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import settings
from .tts import PLAY_HZ, prepare_playback
from .web_search import _fold

log = logging.getLogger("meobot.music")


class _YtdlpLog:
    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            return
        log.debug("%s", msg)

    def info(self, msg: str) -> None:
        log.debug("%s", msg)

    def warning(self, msg: str) -> None:
        log.debug("%s", msg)

    def error(self, msg: str) -> None:
        log.debug("%s", msg)


_MUSIC_RE = re.compile(
    r"""
    (?:
        (?:hay|hay)\s+(?:phat|hat|nghe)                 # hãy phát / hãy hát / hãy nghe
        |
        (?:phat|hat|nghe|bat|mo|play)\s+
        (?:nhac|bai(?:\s+hat)?|ca\s*khuc|song|music)    # phát nhạc, hát bài, nghe bài hát
        |
        (?:hat|phat)\s+bai                              # hát bài / phát bài
        |
        play\s+(?:music|song|nhac)
        |
        \bkaraoke\b
    )
    """,
    re.I | re.X,
)
_PHAT_NOT_MUSIC = re.compile(
    r"\bphat\s*(trien|bieu|hien|hanh|minh|tan|dong|song|thanh|ngon)\b",
    re.I,
)
_MUSIC_VERB = re.compile(r"\b(phat|hat|nghe|bat|mo|play)\b", re.I)
_MUSIC_NOUN = re.compile(r"\b(nhac|bai|ca\s*khuc|karaoke|song|music)\b", re.I)
_MUSIC_FILLER = re.compile(
    r"\b("
    r"hay noi|hãy nói|cho minh|cho mình|giup minh|giúp mình|"
    r"con meo oi|con mèo ơi|meo oi|mèo ơi|oi|ơi"
    r")\b",
    re.I,
)
_MUSIC_STRIP = re.compile(
    r"\b("
    r"hay phat nhac|hay hat nhac|hay phat bai hat|hay hat bai hat|"
    r"hay phat bai|hay hat bai|hay phat|hay hat|hay nghe|"
    r"phat nhac|phat bai hat|phat bai|hat bai hat|hat bai|"
    r"nghe nhac|nghe bai hat|nghe bai|"
    r"bat nhac|bat bai hat|bat bai|"
    r"mo nhac|mo bai hat|mo bai|"
    r"play music|play song|play|"
    r"ca khuc|bai hat|nhac|"
    r"giup minh|di|nhe|voi|cho em|cho minh"
    r")\b",
    re.I,
)


def looks_music(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    t = _fold(_MUSIC_FILLER.sub(" ", raw))
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t in {"nhac", "hat", "play", "karaoke"}:
        return True
    if t.startswith("play "):
        return True
    has_noun = bool(_MUSIC_NOUN.search(t))
    if _PHAT_NOT_MUSIC.search(t) and not has_noun:
        return False
    if _MUSIC_RE.search(t):
        return True
    if _MUSIC_VERB.search(t) and has_noun:
        return True
    return False


def music_query(text: str) -> str:
    t = _MUSIC_FILLER.sub(" ", text or "")
    folded = _fold(t)
    folded = re.sub(r"[^\w\s]", " ", folded)
    prev = None
    while prev != folded:
        prev = folded
        folded = _MUSIC_STRIP.sub(" ", folded)
        folded = re.sub(r"\s+", " ", folded).strip()
    # Keep original letters for the leftover tokens (accents) when possible.
    keep = set(folded.split())
    if keep:
        original_tokens = re.findall(r"[^\s.,!?]+", t)
        leftover = [tok for tok in original_tokens if _fold(tok) in keep]
        q = " ".join(leftover).strip(" .,!?")
        if q:
            return q
    return folded or "nhạc pop việt nam"


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or ""


def _find_node() -> str:
    found = shutil.which("node")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for candidate in (
        local / "Programs" / "nodejs" / "node.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    versions = local / "cursor-agent" / "versions"
    if versions.is_dir():
        dirs = sorted(
            (p for p in versions.iterdir() if p.is_dir() and (p / "node.exe").is_file()),
            key=lambda p: p.name,
            reverse=True,
        )
        if dirs:
            return str(dirs[0] / "node.exe")
    return ""


def _js_runtimes() -> dict:
    deno = shutil.which("deno")
    if deno:
        return {"deno": {"path": deno}}
    node = _find_node()
    if node:
        return {"node": {"path": node}}
    return {"deno": {}}


def _pcm_from_file(path: Path) -> bytes:
    import miniaudio

    decoded = miniaudio.decode_file(
        str(path),
        nchannels=1,
        sample_rate=PLAY_HZ,
        output_format=miniaudio.SampleFormat.SIGNED16,
    )
    raw = bytes(decoded.samples)
    max_bytes = settings.music_max_seconds * PLAY_HZ * 2
    if len(raw) > max_bytes:
        raw = raw[: max_bytes - (max_bytes % 2)]
    return prepare_playback(raw)


def _first_audio(folder: Path) -> Path | None:
    for ext in ("*.mp3", "*.m4a", "*.opus", "*.ogg", "*.webm", "*.wav"):
        found = list(folder.glob(ext))
        if found:
            return found[0]
    return None


def _base_ydl_opts(tmp: Path) -> dict:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("Can ffmpeg de tai nhac (pip install imageio-ffmpeg)")
    return {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
        "logger": _YtdlpLog(),
        "outtmpl": str(tmp / "track.%(ext)s"),
        "ffmpeg_location": ffmpeg,
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
        "js_runtimes": _js_runtimes(),
        "remote_components": ["ejs:github"],
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        },
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
    }


def _search_urls(spec: str, n: int) -> list[str]:
    import yt_dlp

    with yt_dlp.YoutubeDL(
        {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "noplaylist": True,
            "ignoreerrors": True,
            "logger": _YtdlpLog(),
        }
    ) as ydl:
        info = ydl.extract_info(spec, download=False)
    urls: list[str] = []
    for entry in (info or {}).get("entries") or []:
        if not entry:
            continue
        url = entry.get("url") or entry.get("webpage_url") or ""
        vid = entry.get("id") or ""
        ie = (entry.get("ie_key") or entry.get("extractor_key") or "").lower()
        if url.startswith("http"):
            urls.append(url)
        elif vid and "soundcloud" in ie:
            urls.append(f"https://soundcloud.com/{vid}" if "/" in vid else url or vid)
        elif vid:
            urls.append(f"https://www.youtube.com/watch?v={vid}")
    return urls[:n]


def _dedupe_urls(urls: list[str], n: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        clean = (url or "").strip()
        key = clean.rstrip("/").lower()
        if not clean.startswith(("http://", "https://")) or key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if n is not None and len(out) >= n:
            break
    return out


def _web_music_urls(query: str, *, site: str | None = None, n: int = 8) -> list[str]:
    """Use web search for platforms without a yt-dlp search pseudo-URL."""
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    search = f"{query} site:{site}" if site else f"{query} nghe nhạc"
    for backend in ("startpage", "brave", "duckduckgo"):
        try:
            with DDGS(timeout=15) as ddgs:
                items = ddgs.text(
                    search,
                    region=settings.web_search_region,
                    max_results=max(n, 8),
                    backend=backend,
                )
        except Exception as exc:
            log.info("Music web search %s failed: %s", backend, exc)
            continue
        urls = [
            str(item.get("href") or item.get("url") or "").strip()
            for item in (items or [])
            if isinstance(item, dict)
        ]
        if site:
            urls = [url for url in urls if site in urlparse(url).netloc.lower()]
        found = _dedupe_urls(urls, n)
        if found:
            return found
    return []


def _platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "zingmp3.vn" in host:
        return "zingmp3"
    if "soundcloud.com" in host:
        return "soundcloud"
    return "other"


def _discover_music_urls(query: str) -> dict[str, list[str]]:
    """Search every supported source first; selection happens by fixed priority."""

    def youtube() -> list[str]:
        urls: list[str] = []
        for spec in (f"ytsearch8:{query}", f"ytsearch5:{query} lyrics"):
            urls.extend(_search_urls(spec, 8))
        return _dedupe_urls(urls, 10)

    def zing() -> list[str]:
        return _web_music_urls(query, site="zingmp3.vn", n=8)

    def soundcloud() -> list[str]:
        return _dedupe_urls(_search_urls(f"scsearch8:{query}", 8), 8)

    def other() -> list[str]:
        urls = _web_music_urls(query, n=12)
        return [url for url in urls if _platform(url) == "other"]

    jobs = {
        "youtube": youtube,
        "zingmp3": zing,
        "soundcloud": soundcloud,
        "other": other,
    }
    found: dict[str, list[str]] = {name: [] for name in jobs}
    with ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix="music-search") as pool:
        futures = {name: pool.submit(fn) for name, fn in jobs.items()}
        for name, future in futures.items():
            try:
                found[name] = future.result()
            except Exception as exc:
                log.info("Music search %s failed: %s", name, exc)
    log.info(
        "Music candidates: %s",
        ", ".join(f"{name}={len(found[name])}" for name in jobs),
    )
    return found


def _download_url(url: str, extra: dict) -> tuple[str, bytes]:
    import yt_dlp

    tmp = Path(tempfile.mkdtemp(prefix="katbot-music-"))
    try:
        opts = _base_ydl_opts(tmp)
        opts.update(extra)
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
            except yt_dlp.utils.DownloadError as exc:
                raise RuntimeError(str(exc).splitlines()[-1][:200]) from exc
            if info and info.get("entries"):
                info = next((e for e in info["entries"] if e), None)
            if not info:
                raise RuntimeError("Khong lay duoc metadata")
            if info.get("is_drm") or info.get("drm"):
                raise RuntimeError("DRM")
            title = info.get("title") or url
        audio = _first_audio(tmp)
        if audio is None:
            raise RuntimeError("Khong tai duoc file am thanh")
        return title, _pcm_from_file(audio)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _try_urls(label: str, urls: list[str], extra: dict) -> tuple[str, bytes] | None:
    for url in urls:
        try:
            title, pcm = _download_url(url, extra)
            log.info("Music via %s: %s", label, title)
            return title, pcm
        except Exception as exc:
            msg = str(exc)
            if "DRM" in msg or "drm" in msg.lower():
                log.info("Skip DRM %s", url)
                continue
            if "403" in msg or "format is not available" in msg or "reloaded" in msg:
                log.info("Skip blocked %s (%s)", url, msg.splitlines()[-1][:80])
                continue
            log.info("Skip %s: %s", label, msg.splitlines()[-1][:120])
    return None


def _archive_fetch(query: str) -> tuple[str, bytes]:
    q = " ".join(query.split())
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        r = client.get(
            "https://archive.org/advancedsearch.php",
            params=[
                ("q", f"({q}) AND mediatype:audio"),
                ("fl[]", "identifier"),
                ("fl[]", "title"),
                ("rows", "5"),
                ("page", "1"),
                ("output", "json"),
            ],
        )
        r.raise_for_status()
        docs = ((r.json().get("response") or {}).get("docs")) or []
        last = "Archive.org khong co bai"
        for doc in docs:
            ident = doc.get("identifier")
            title = doc.get("title") or query
            try:
                meta = client.get(f"https://archive.org/metadata/{ident}")
                meta.raise_for_status()
                files = (meta.json().get("files")) or []
                name = ""
                for f in files:
                    n = (f.get("name") or "").lower()
                    if n.endswith((".mp3", ".ogg", ".m4a")):
                        name = f.get("name") or ""
                        break
                if not name:
                    continue
                audio = client.get(f"https://archive.org/download/{ident}/{name}")
                audio.raise_for_status()
            except Exception as exc:
                last = str(exc)
                continue
            tmp = Path(tempfile.mkdtemp(prefix="katbot-ia-"))
            try:
                ext = Path(name).suffix or ".mp3"
                path = tmp / f"track{ext}"
                path.write_bytes(audio.content)
                return str(title), _pcm_from_file(path)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    raise RuntimeError(last)


def fetch_track_pcm(query: str) -> tuple[str, bytes]:
    try:
        import yt_dlp  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Chua cai yt-dlp (pip install yt-dlp)") from exc

    candidates = _discover_music_urls(query)
    runtimes = _js_runtimes()
    log.info(
        "YouTube via yt-dlp js=%s urls=%s",
        ",".join(runtimes),
        len(candidates["youtube"]),
    )
    hit = _try_urls(
        "youtube",
        candidates["youtube"],
        {
            "format": "bestaudio/best",
            "extractor_args": {
                "youtube": {"player_client": ["web_safari", "android", "mweb", "web"]}
            },
        },
    )
    if hit:
        return hit

    hit = _try_urls(
        "zingmp3",
        candidates["zingmp3"],
        {"format": "bestaudio/best"},
    )
    if hit:
        return hit

    hit = _try_urls(
        "soundcloud",
        candidates["soundcloud"],
        {"format": "bestaudio/best"},
    )
    if hit:
        return hit

    hit = _try_urls(
        "other",
        candidates["other"],
        {"format": "bestaudio/best"},
    )
    if hit:
        return hit

    try:
        title, pcm = _archive_fetch(query)
        log.info("Music via archive.org: %s", title)
        return title, pcm
    except Exception as exc:
        raise RuntimeError(
            f"Khong tai duoc nhac (YouTube/Zing MP3/SoundCloud/other). {exc}"
        ) from exc
