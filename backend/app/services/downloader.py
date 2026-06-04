"""
Downloads a YouTube video + metadata using yt-dlp.
Returns the video file path and parsed heatmap data.
"""

import subprocess
import json
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    job_id = uuid.uuid4().hex[:10]
    output_template = str(Path(output_dir) / f"{job_id}_%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "--print-json",
        "--no-playlist",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "--sleep-interval", "3",
        "--max-sleep-interval", "15",
        "-o", output_template,
        url
    ]

    process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if process.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {process.stderr}")

    lines = process.stdout.strip().split("\n")
    info_json = lines[-1]
    metadata = json.loads(info_json)

    downloaded_path = None
    for file in Path(output_dir).glob(f"{job_id}_*"):
        if file.suffix in (".mp4", ".mkv", ".webm"):
            downloaded_path = file
            break
    if not downloaded_path:
        raise FileNotFoundError("Downloaded video not found")

    return downloaded_path, metadata