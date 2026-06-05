import logging
import time
import re
import os
import uuid
import requests
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

import yt_dlp

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 1. Universal video ID extractor (handles everything)
# ------------------------------------------------------------
def _extract_video_id(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if "google.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        inner = qs.get("url", [None])[0] or qs.get("q", [None])[0]
        if inner:
            raw_url = unquote(inner)
    patterns = [
        r'(?:v=|/shorts/)([\w-]{11})',
        r'youtu\.be/([\w-]{11})',
        r'/embed/([\w-]{11})',
    ]
    for p in patterns:
        m = re.search(p, raw_url)
        if m:
            return m.group(1)
    m = re.search(r'([\w-]{11})', raw_url)
    if m:
        return m.group(1)
    raise ValueError(f"Could not extract video ID from: {raw_url}")

# ------------------------------------------------------------
# 2. yt‑dlp with multiple clients and retries
# ------------------------------------------------------------
def _download_via_ytdlp(url: str, output_dir: str) -> Tuple[Path, dict]:
    # Normalize URL to a clean watch link (avoids google redirect headaches)
    try:
        video_id = _extract_video_id(url)
        clean_url = f"https://www.youtube.com/watch?v={video_id}"
    except ValueError:
        clean_url = url  # fallback

    # Client configurations to try, in order
    CLIENTS = [
        {"youtube:player_client": ["android"]},
        {"youtube:player_client": ["web"]},
        {"youtube:player_client": ["ios"]},
    ]

    job_id = uuid.uuid4().hex[:10]
    outtmpl = str(Path(output_dir) / f"{job_id}_%(title)s.%(ext)s")

    last_exception = None

    for client_cfg in CLIENTS:
        for attempt in range(2):  # up to 2 attempts per client
            try:
                ydl_opts = {
                    "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                    "outtmpl": outtmpl,
                    "extractor_args": client_cfg,
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "user_agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
                    "sleep_interval_requests": 3,
                    "max_sleep_interval_requests": 15,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)

                # Find the downloaded file
                downloaded = None
                for f in Path(output_dir).glob(f"{job_id}_*"):
                    if f.suffix in (".mp4", ".mkv", ".webm"):
                        downloaded = f
                        break
                if not downloaded:
                    raise FileNotFoundError("Downloaded file not found")

                logger.info(f"Downloaded using client {client_cfg}")
                return downloaded, {
                    "title": info.get("title", f"video_{job_id}"),
                    "duration": info.get("duration", 0),
                    "heatmap": None,
                }

            except Exception as e:
                last_exception = e
                logger.warning(f"yt‑dlp attempt {attempt+1} with {client_cfg} failed: {e}")
                time.sleep(2 ** attempt)   # exponential backoff

    raise RuntimeError(f"All yt‑dlp clients failed after retries. Last error: {last_exception}")

# ------------------------------------------------------------
# 3. yewtu.be direct fallback (no API, rarely blocked)
# ------------------------------------------------------------
def _download_via_yewtube(video_id: str, output_dir: str) -> Tuple[Path, dict]:
    for itag in ["22", "18"]:   # 720p, 360p
        try:
            url = f"https://yewtu.be/latest_version?id={video_id}&itag={itag}"
            resp = requests.get(url, stream=True, allow_redirects=True, timeout=30)
            if resp.status_code == 200 and "video/mp4" in resp.headers.get("content-type", ""):
                job_id = uuid.uuid4().hex[:10]
                file_path = Path(output_dir) / f"{job_id}_fallback_{itag}.mp4"
                with open(file_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"Downloaded via yewtu.be itag={itag}")
                return file_path, {
                    "title": f"video_{video_id}",
                    "duration": 0,
                    "heatmap": None,
                }
        except Exception as e:
            logger.warning(f"yewtu.be itag={itag} failed: {e}")
    raise RuntimeError("yewtu.be fallback failed")

# ------------------------------------------------------------
# 4. Main entry point
# ------------------------------------------------------------
def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Try yt‑dlp with multiple clients (android, web, ios)
    try:
        return _download_via_ytdlp(url, output_dir)
    except Exception as e:
        logger.exception("yt‑dlp completely failed")

    # Last resort: yewtu.be direct
    try:
        video_id = _extract_video_id(url)
        return _download_via_yewtube(video_id, output_dir)
    except Exception as e:
        logger.exception("All download methods exhausted")
        raise RuntimeError("Could not download video after trying all methods")