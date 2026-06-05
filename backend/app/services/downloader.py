import requests
import json
import re
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

# List of reliable public Invidious instances (you can add more)
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://invidious.snopyta.org",
    "https://yewtu.be",
    "https://inv.riverside.rocks",
]

def _get_video_info(url: str):
    """Extract video metadata and direct download URL from an Invidious instance."""
    # Extract video ID from YouTube URL (works with shorts, /watch?v=, etc.)
    match = re.search(r"(?:v=|/shorts/)([a-zA-Z0-9_-]{11})", url)
    if not match:
        raise ValueError(f"Could not extract video ID from URL: {url}")
    video_id = match.group(1)

    # Try each instance until one works
    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            resp = requests.get(api_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Pick the best video stream (prefer 720p mp4)
                streams = data.get("formatStreams", []) + data.get("adaptiveFormats", [])
                # Filter streams: prefer mp4, then webm, max height 720
                selected = None
                for s in streams:
                    if s.get("container") == "mp4" and s.get("qualityLabel", "0").startswith("720"):
                        selected = s
                        break
                if not selected:
                    # fallback: first mp4 stream
                    for s in streams:
                        if s.get("container") == "mp4":
                            selected = s
                            break
                if not selected:
                    # ultimate fallback: first available stream
                    selected = streams[0] if streams else None
                if selected and "url" in selected:
                    return {
                        "title": data.get("title", "video"),
                        "duration": data.get("lengthSeconds", 0),
                        "download_url": selected["url"],
                        "ext": selected.get("container", "mp4"),
                    }
        except Exception:
            continue
    raise RuntimeError("All Invidious instances failed. Try again later.")

def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    info = _get_video_info(url)

    job_id = uuid.uuid4().hex[:10]
    safe_title = re.sub(r'[\\/*?:"<>|]', "", info["title"])[:50]
    ext = info.get("ext", "mp4")
    file_path = Path(output_dir) / f"{job_id}_{safe_title}.{ext}"

    # Download the video stream
    with requests.get(info["download_url"], stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # Construct minimal metadata (like yt-dlp would return)
    metadata = {
        "title": info["title"],
        "duration": info["duration"],
        "heatmap": None,   # Invidious doesn't provide heatmap, but our clip selector can fallback
    }

    return file_path, metadata