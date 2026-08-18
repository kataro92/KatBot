"""Search a track and decode a short clip for the ESP speaker."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

import httpx

from .config import settings
from .tts import PLAY_HZ, prepare_playback

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


def looks_music(text: str) -> bool:
    t = (text or "").lower()
    keys = (
        "phát nhạc",
        "phat nhac",
        "bật nhạc",
        "bat nhac",
        "mở nhạc",
        "mo nhac",
        "nghe nhạc",
        "nghe nhac",
        "phát bài",
        "phat bai",
        "bật bài",
        "bat bai",
        "mở bài",
        "mo bai",
        "nghe bài",
        "nghe bai",
        "play music",
        "play song",
    )
    if any(k in t for k in keys):
        return True
    return t.startswith("play ") or t.strip() in {"nhạc", "nhac", "play"}


def music_query(text: str) -> str:
    t = (text or "").strip()
    for k in (
        "phát nhạc",
        "phat nhac",
        "bật nhạc",
        "bat nhac",
        "mở nhạc",
        "mo nhac",
        "nghe nhạc",
        "nghe nhac",
        "phát bài",
        "phat bai",
        "bật bài",
        "bat bai",
        "mở bài hát",
        "mo bai hat",
        "mở bài",
        "mo bai",
        "nghe bài hát",
        "nghe bai hat",
        "nghe bài",
        "nghe bai",
        "play music",
        "play song",
        "play",
    ):
        t = t.replace(k, " ")
    for extra in ("giúp mình", "giup minh", "đi", "di", "nhé", "nhe", "với", "voi"):
        t = t.replace(extra, " ")
    t = " ".join(t.split()).strip(" .,!?")
    return t or "nhạc pop việt nam"


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

    sc_urls = _search_urls(f"scsearch5:{query}", 5)
    hit = _try_urls(
        "soundcloud",
        sc_urls,
        {"format": "bestaudio/best"},
    )
    if hit:
        return hit

    yt_queries = [f"ytsearch8:{query}", f"ytsearch5:{query} lyrics"]
    yt_urls: list[str] = []
    for spec in yt_queries:
        for url in _search_urls(spec, 8):
            if url not in yt_urls:
                yt_urls.append(url)
    runtimes = _js_runtimes()
    log.info("YouTube via yt-dlp js=%s urls=%s", ",".join(runtimes), len(yt_urls))
    hit = _try_urls(
        "youtube",
        yt_urls[:8],
        {
            "format": "bestaudio/best",
            "extractor_args": {
                "youtube": {"player_client": ["web_safari", "android", "mweb", "web"]}
            },
        },
    )
    if hit:
        return hit

    try:
        title, pcm = _archive_fetch(query)
        log.info("Music via archive.org: %s", title)
        return title, pcm
    except Exception as exc:
        raise RuntimeError(f"Khong tai duoc nhac (SoundCloud/YouTube/Archive). {exc}") from exc
