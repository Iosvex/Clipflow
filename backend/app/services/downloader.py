import requests
import re
import os
import uuid
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

# Try these Invidious instances first (they rarely block cloud IPs)
INVIDIOUS_INSTANCES = [
    "https://yewtu.be",
    "https://inv.nadeko.net",
    "https://vid.puffyan.us",
]

def _extract_video_id(raw_url: str) -> str:
    """Extracts the 11‑char YouTube video ID from any URL."""
    parsed = urlparse(raw_url)
    if "google.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        inner = query.get("url", [None])[0] or query.get("q", [None])[0]
        if inner:
            raw_url = unquote(inner)
    for pattern in [
        r'(?:v=|/shorts/)([\w-]{11})',
        r'youtu\.be/([\w-]{11})',
        r'/embed/([\w-]{11})',
    ]:
        match = re.search(pattern, raw_url)
        if match:
            return match.group(1)
    # Last chance: any 11‑char alphanumeric + underscore/dash
    match = re.search(r'([\w-]{11})', raw_url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract video ID from: {raw_url}")

def _download_direct(url: str, file_path: Path) -> None:
    """Stream a file from a direct URL to disk."""
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

def _try_vevioz(video_id: str, output_dir: str) -> Tuple[Path, dict]:
    """Primary: vevioz public API (no size limits)."""
    api_url = f"https://api.vevioz.com/@api/button/mp4/{video_id}"
    resp = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError("vevioz API not available")
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise RuntimeError("vevioz returned empty data")

    # Choose the best stream (prefer 720p, then highest quality)
    streams = [s for s in data if "url" in s]
    if not streams:
        raise RuntimeError("No valid stream in vevioz response")
    best = next((s for s in streams if "720" in s.get("quality", "")), streams[0])
    download_url = best["url"]

    title = "video"
    # Optionally fetch title from a secondary endpoint
    try:
        info = requests.get(f"https://api.vevioz.com/@api/v3/video/{video_id}", timeout=10).json()
        title = info.get("title", title)
    except:
        pass

    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:50]
    job_id = uuid.uuid4().hex[:10]
    file_path = Path(output_dir) / f"{job_id}_{safe_title}.mp4"
    _download_direct(download_url, file_path)

    return file_path, {
        "title": title,
        "duration": 0,
        "heatmap": None,
    }

def _try_yewtube_direct(video_id: str, output_dir: str) -> Tuple[Path, dict]:
    """Fallback: direct MP4 from yewtu.be (720p itag=22, 360p itag=18)."""
    # Try itag=22 first (720p), then 18 (360p)
    for itag in ["22", "18"]:
        try:
            url = f"https://yewtu.be/latest_version?id={video_id}&itag={itag}"
            # We need to follow redirects and get the final URL
            with requests.get(url, stream=True, allow_redirects=True, timeout=15) as resp:
                if resp.status_code == 200 and "video/mp4" in resp.headers.get("content-type", ""):
                    # Save file
                    job_id = uuid.uuid4().hex[:10]
                    file_path = Path(output_dir) / f"{job_id}_ytdirect_{itag}.mp4"
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
    raise RuntimeError("yewtu.be direct download failed")

def _try_invidious_api(video_id: str, output_dir: str) -> Tuple[Path, dict]:
    """Second fallback: try multiple Invidious instances via their API."""
    for instance in INVIDIOUS_INSTANCES:
        try:
            api = f"{instance}/api/v1/videos/{video_id}"
            resp = requests.get(api, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            streams = data.get("formatStreams", []) + data.get("adaptiveFormats", [])
            # Prefer 720p mp4
            selected = None
            for s in streams:
                if s.get("container") == "mp4" and s.get("qualityLabel", "").startswith("720"):
                    selected = s
                    break
            if not selected:
                selected = next((s for s in streams if s.get("container") == "mp4"), None)
            if not selected:
                selected = streams[0] if streams else None
            if not selected or "url" not in selected:
                continue
            title = data.get("title", f"video_{video_id}")
            safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:50]
            job_id = uuid.uuid4().hex[:10]
            file_path = Path(output_dir) / f"{job_id}_{safe_title}.mp4"
            _download_direct(selected["url"], file_path)
            return file_path, {
                "title": title,
                "duration": data.get("lengthSeconds", 0),
                "heatmap": None,
            }
        except Exception:
            continue
    raise RuntimeError("All Invidious APIs failed")

def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    video_id = _extract_video_id(url)

    # Strategy 1: vevioz (no size limit, usually works)
    try:
        return _try_vevioz(video_id, output_dir)
    except Exception as e:
        print(f"vevioz failed: {e}", flush=True)

    # Strategy 2: yewtu.be direct MP4 (fast, no API, almost never blocked)
    try:
        return _try_yewtube_direct(video_id, output_dir)
    except Exception as e:
        print(f"yewtu.be failed: {e}", flush=True)

    # Strategy 3: classical Invidious API (multiple instances)
    return _try_invidious_api(video_id, output_dir)