import requests
import json
import re
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    # 1. Extract video ID (supports all URL formats)
    video_id = None
    patterns = [
        r'(?:v=|/shorts/)([\w-]{11})',
        r'youtu\.be/([\w-]{11})',
        r'/embed/([\w-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            video_id = m.group(1)
            break
    if not video_id:
        # try google redirect
        from urllib.parse import urlparse, parse_qs, unquote
        parsed = urlparse(url)
        if "google.com" in parsed.netloc:
            query = parse_qs(parsed.query)
            inner = query.get("url", [None])[0] or query.get("q", [None])[0]
            if inner:
                url = unquote(inner)
                for p in patterns:
                    m = re.search(p, url)
                    if m:
                        video_id = m.group(1)
                        break
    if not video_id:
        raise ValueError(f"Could not extract video ID from URL: {url}")

    # 2. Use the free vevioz API to get video info & download links
    api_url = f"https://api.vevioz.com/@api/button/mp4/{video_id}"
    resp = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"vevioz API failed with status {resp.status_code}")

    data = resp.json()
    # The API returns an array of format objects, each with a 'url' and 'quality'
    if not isinstance(data, list) or len(data) == 0:
        raise RuntimeError("vevioz API returned empty data")

    # Pick the best quality: prefer 720p mp4, then highest available
    best = None
    for item in data:
        if "url" not in item:
            continue
        quality = item.get("quality", "")
        if "720" in quality:
            best = item
            break
    if not best:
        best = max(data, key=lambda x: int(re.sub(r'\D', '', x.get("quality", "0")) or 0))

    download_url = best["url"]
    title = f"video_{video_id}"  # API doesn't always give a title; we can fetch separately if needed

    # 3. Download the video
    job_id = uuid.uuid4().hex[:10]
    file_path = Path(output_dir) / f"{job_id}_{title}.mp4"

    with requests.get(download_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # 4. Minimal metadata (we can add title later via a second API call if needed)
    metadata = {
        "title": title,
        "duration": 0,           # vevioz can provide this if we request /api/videos/{id}
        "heatmap": None,
    }

    return file_path, metadata