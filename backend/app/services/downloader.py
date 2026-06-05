import requests
import json
import re
import os
import uuid
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

# Reliable public Invidious instances
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://invidious.snopyta.org",
    "https://yewtu.be",
    "https://inv.riverside.rocks",
]

def extract_video_id(raw_url: str) -> str:
    """
    Extracts an 11‑character YouTube video ID from any URL,
    including google.com redirects, youtu.be short links, and /shorts/.
    """
    # 1) If it's a google.com/url?url=... redirect, decode the inner URL
    parsed = urlparse(raw_url)
    if "google.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        inner_url = query.get("url", [None])[0] or query.get("q", [None])[0]
        if inner_url:
            raw_url = unquote(inner_url)

    # 2) Direct YouTube video ID patterns
    patterns = [
        r'(?:v=|/shorts/)([\w-]{11})',   # /watch?v= or /shorts/
        r'youtu\.be/([\w-]{11})',         # youtu.be/
        r'/embed/([\w-]{11})',            # /embed/
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_url)
        if match:
            return match.group(1)

    # 3) Last resort: find any 11‑char alphanumeric+underscore-dash string
    match = re.search(r'([\w-]{11})', raw_url)
    if match and len(match.group(1)) == 11:
        return match.group(1)

    raise ValueError(f"Could not extract video ID from URL: {raw_url}")

def _get_video_info(url: str):
    video_id = extract_video_id(url)

    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            resp = requests.get(api_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                streams = data.get("formatStreams", []) + data.get("adaptiveFormats", [])
                selected = None
                # Prefer 720p mp4
                for s in streams:
                    if s.get("container") == "mp4" and s.get("qualityLabel", "").startswith("720"):
                        selected = s
                        break
                if not selected:
                    for s in streams:
                        if s.get("container") == "mp4":
                            selected = s
                            break
                if not selected and streams:
                    selected = streams[0]
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

    with requests.get(info["download_url"], stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    metadata = {
        "title": info["title"],
        "duration": info["duration"],
        "heatmap": None,
    }

    return file_path, metadata