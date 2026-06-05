import requests
import json
import re
import os
import uuid
import subprocess
import tempfile
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from typing import Optional, Tuple, List
from ..config import settings

# ------------------------------------------------------------
# 1.  Universal video ID extractor (handles any link)
# ------------------------------------------------------------
def extract_video_id(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if "google.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        inner = query.get("url", [None])[0] or query.get("q", [None])[0]
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
    if m and len(m.group(1)) == 11:
        return m.group(1)
    raise ValueError(f"Could not extract video ID from: {raw_url}")

# ------------------------------------------------------------
# 2.  Fetch fresh, healthy Invidious instances
# ------------------------------------------------------------
def _get_healthy_instances() -> List[str]:
    try:
        resp = requests.get("https://api.invidious.io/instances.json", timeout=10)
        if resp.status_code == 200:
            instances = []
            for item in resp.json():
                if item.get("type") == "https" and item.get("api"):
                    instances.append(item["uri"])   # already like "https://..."
            if instances:
                return instances[:10]   # top 10
    except Exception:
        pass
    # Fallback list if the API is down
    return [
        "https://vid.puffyan.us",
        "https://inv.riverside.rocks",
        "https://yewtu.be",
        "https://invidious.snopyta.org",
    ]

# ------------------------------------------------------------
# 3.  Try Invidious first (now with fresh instances)
# ------------------------------------------------------------
def _download_via_invidious(video_id: str, output_dir: str) -> Tuple[Path, dict]:
    instances = _get_healthy_instances()
    for instance in instances:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            resp = requests.get(api_url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            streams = data.get("formatStreams", []) + data.get("adaptiveFormats", [])
            selected = None
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
            if not selected or "url" not in selected:
                continue

            # Download the stream
            job_id = uuid.uuid4().hex[:10]
            title = data.get("title", "video")
            safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:50]
            ext = selected.get("container", "mp4")
            file_path = Path(output_dir) / f"{job_id}_{safe_title}.{ext}"
            with requests.get(selected["url"], stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            metadata = {
                "title": title,
                "duration": data.get("lengthSeconds", 0),
                "heatmap": None,
            }
            return file_path, metadata
        except Exception:
            continue
    raise RuntimeError("All Invidious instances failed (tried fresh list)")

# ------------------------------------------------------------
# 4.  Fallback to yt‑dlp (Android client, no cookies)
# ------------------------------------------------------------
def _download_via_ytdlp(url: str, output_dir: str) -> Tuple[Path, dict]:
    job_id = uuid.uuid4().hex[:10]
    output_template = str(Path(output_dir) / f"{job_id}_%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=android",
        "-f", "best[height<=720]",               # fallback format, no ext restriction
        "--print-json",
        "--no-playlist",
        "--user-agent", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
        "--sleep-interval", "3",
        "--max-sleep-interval", "15",
        "-o", output_template,
        url
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp fallback failed: {proc.stderr}")

    lines = proc.stdout.strip().split("\n")
    metadata = json.loads(lines[-1])

    # Find the downloaded file
    downloaded_path = None
    for f in Path(output_dir).glob(f"{job_id}_*"):
        if f.suffix in (".mp4", ".mkv", ".webm"):
            downloaded_path = f
            break
    if not downloaded_path:
        raise FileNotFoundError("Downloaded video not found (yt‑dlp fallback)")
    return downloaded_path, metadata

# ------------------------------------------------------------
# 5.  Main entry point (try Invidious first, then yt‑dlp)
# ------------------------------------------------------------
def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    video_id = extract_video_id(url)

    # Primary: Invidious (reliable, no blocks)
    try:
        return _download_via_invidious(video_id, output_dir)
    except Exception as e:
        print(f"Invidious failed: {e}", flush=True)

    # Fallback: yt‑dlp (Android client)
    return _download_via_ytdlp(url, output_dir)