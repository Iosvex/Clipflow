"""
downloads a YouTube video + metadata using yt-dlp.
Returns the video file path and parsed heatmap data (if available).
"""

import subprocess
import json
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    """
    Download best 720p (or lower) video that has audio.
    Returns (video_path, metadata_dict).
    metadata_dict includes 'heatmap' list (if the video has Most Replayed data).
    """
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    job_id = uuid.uuid4().hex[:10]
    output_template = str(Path(output_dir) / f"{job_id}_%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "--print-json",          # dump full video info
        "--no-playlist",
        "-o", output_template,
        url
    ]

    process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if process.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {process.stderr}")

    # The last line of stdout is the JSON metadata
    lines = process.stdout.strip().split("\n")
    info_json = lines[-1]   # might be multiple lines if we used --print-json multiple times; we didn't
    metadata = json.loads(info_json)

    # Find the actual downloaded file
    downloaded_path = None
    for file in Path(output_dir).glob(f"{job_id}_*"):
        if file.suffix in (".mp4", ".mkv", ".webm"):
            downloaded_path = file
            break
    if not downloaded_path:
        raise FileNotFoundError("Downloaded video not found")

    return downloaded_path, metadata