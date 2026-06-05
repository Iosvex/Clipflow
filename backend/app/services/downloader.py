import re
import os
import uuid
import requests
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

# ------------------------------------------------------------
# 1. Universal video ID extractor (handles Google redirects)
# ------------------------------------------------------------
def _extract_video_id(raw_url: str) -> str:
    # Unwrap google.com/url?url=...
    parsed = urlparse(raw_url)
    if "google.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        inner = qs.get("url", [None])[0] or qs.get("q", [None])[0]
        if inner:
            raw_url = unquote(inner)

    # Try all known patterns
    patterns = [
        r'(?:v=|/shorts/)([\w-]{11})',   # /watch?v= or /shorts/
        r'youtu\.be/([\w-]{11})',         # short link
        r'/embed/([\w-]{11})',            # embed
    ]
    for p in patterns:
        m = re.search(p, raw_url)
        if m:
            return m.group(1)

    # Fallback: any 11‑char alphanumeric + underscore / dash
    m = re.search(r'([\w-]{11})', raw_url)
    if m:
        return m.group(1)
    raise ValueError(f"Could not find video ID in: {raw_url}")

# ------------------------------------------------------------
# 2. Primary: yt‑dlp with Android client (no cookies, no blocks)
# ------------------------------------------------------------
def _download_via_ytdlp(url: str, output_dir: str) -> Tuple[Path, dict]:
    import yt_dlp

    job_id = uuid.uuid4().hex[:10]
    outtmpl = str(Path(output_dir) / f"{job_id}_%(title)s.%(ext)s")

    ydl_opts = {
        "format": "best[height<=720]",               # always available
        "outtmpl": outtmpl,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "user_agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
        "sleep_interval_requests": 3,
        "max_sleep_interval_requests": 15,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # The prepared filename might have the original title placeholder,
    # but yt‑dlp replaces it after download. We'll glob the file.
    downloaded = None
    for f in Path(output_dir).glob(f"{job_id}_*"):
        if f.suffix in (".mp4", ".mkv", ".webm"):
            downloaded = f
            break
    if not downloaded:
        raise FileNotFoundError("Could not find downloaded video")

    return downloaded, {
        "title": info.get("title", f"video_{job_id}"),
        "duration": info.get("duration", 0),
        "heatmap": None,
    }

# ------------------------------------------------------------
# 3. Fallback: yewtu.be direct MP4 (no API, rarely blocked)
# ------------------------------------------------------------
def _download_via_yewtube(video_id: str, output_dir: str) -> Tuple[Path, dict]:
    for itag in ["22", "18"]:   # 720p, then 360p
        try:
            url = f"https://yewtu.be/latest_version?id={video_id}&itag={itag}"
            resp = requests.get(url, stream=True, allow_redirects=True, timeout=20)
            if resp.status_code == 200 and "video/mp4" in resp.headers.get("content-type", ""):
                job_id = uuid.uuid4().hex[:10]
                file_path = Path(output_dir) / f"{job_id}_fallback_{itag}.mp4"
                with open(file_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return file_path, {
                    "title": f"video_{video_id}",
                    "duration": 0,
                    "heatmap": None,
                }
        except Exception:
            continue
    raise RuntimeError("yewtu.be fallback failed")

# ------------------------------------------------------------
# 4. Main entry point
# ------------------------------------------------------------
def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    # 1. Primary: yt‑dlp (Android client)
    try:
        return _download_via_ytdlp(url, output_dir)
    except Exception as e:
        print(f"yt‑dlp failed: {e}", flush=True)

    # 2. Fallback: yewtu.be direct (requires video ID only)
    video_id = _extract_video_id(url)
    return _download_via_yewtube(video_id, output_dir)