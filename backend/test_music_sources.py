"""Deterministic tests for multi-platform music source priority."""

from __future__ import annotations

from unittest.mock import patch

from app import music


def check(condition: bool, name: str) -> int:
    print(("PASS" if condition else "FAIL"), name)
    return 0 if condition else 1


def main() -> int:
    failures = 0
    failures += check(
        music._platform("https://www.youtube.com/watch?v=x") == "youtube"
        and music._platform("https://zingmp3.vn/bai-hat/x.html") == "zingmp3"
        and music._platform("https://soundcloud.com/a/b") == "soundcloud"
        and music._platform("https://archive.org/details/x") == "other",
        "classify music platforms",
    )

    searched: list[str] = []

    def fake_ydl_search(spec: str, n: int) -> list[str]:
        searched.append(spec.split(":", 1)[0])
        if spec.startswith("scsearch"):
            return ["https://soundcloud.com/a/b"]
        return ["https://www.youtube.com/watch?v=x"]

    def fake_web_search(query: str, *, site: str | None = None, n: int = 8) -> list[str]:
        searched.append(site or "other")
        if site:
            return ["https://zingmp3.vn/bai-hat/x.html"]
        return ["https://archive.org/details/x"]

    with (
        patch.object(music, "_search_urls", side_effect=fake_ydl_search),
        patch.object(music, "_web_music_urls", side_effect=fake_web_search),
    ):
        discovered = music._discover_music_urls("test")
    failures += check(
        all(discovered[name] for name in ("youtube", "zingmp3", "soundcloud", "other"))
        and {"ytsearch8", "ytsearch5", "scsearch8", "zingmp3.vn", "other"}.issubset(searched),
        "search all supported platform groups",
    )

    candidates = {
        "youtube": ["https://youtube.test/1"],
        "zingmp3": ["https://zing.test/1"],
        "soundcloud": ["https://soundcloud.test/1"],
        "other": ["https://other.test/1"],
    }
    calls: list[str] = []

    def youtube_wins(label: str, urls: list[str], extra: dict):
        calls.append(label)
        return ("YT", b"pcm") if label == "youtube" else None

    with (
        patch.object(music, "_discover_music_urls", return_value=candidates),
        patch.object(music, "_try_urls", side_effect=youtube_wins),
    ):
        result = music.fetch_track_pcm("test")
    failures += check(result[0] == "YT" and calls == ["youtube"], "YouTube first")

    calls.clear()

    def zing_fallback(label: str, urls: list[str], extra: dict):
        calls.append(label)
        return ("Zing", b"pcm") if label == "zingmp3" else None

    with (
        patch.object(music, "_discover_music_urls", return_value=candidates),
        patch.object(music, "_try_urls", side_effect=zing_fallback),
    ):
        result = music.fetch_track_pcm("test")
    failures += check(
        result[0] == "Zing" and calls == ["youtube", "zingmp3"],
        "Zing MP3 fallback second",
    )

    calls.clear()

    def soundcloud_fallback(label: str, urls: list[str], extra: dict):
        calls.append(label)
        return ("SC", b"pcm") if label == "soundcloud" else None

    with (
        patch.object(music, "_discover_music_urls", return_value=candidates),
        patch.object(music, "_try_urls", side_effect=soundcloud_fallback),
    ):
        result = music.fetch_track_pcm("test")
    failures += check(
        result[0] == "SC" and calls == ["youtube", "zingmp3", "soundcloud"],
        "SoundCloud fallback third",
    )

    if failures:
        print(f"\n{failures} failed")
        return 1
    print("\nAll music source tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
