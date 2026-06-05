import subprocess
import json
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

def download_video(url: str, output_dir: Optional[str] = None,
                   start: Optional[float] = None, end: Optional[float] = None) -> Tuple[Path, dict]:
    """
    Download a YouTube video, optionally just a section.
    Uses the Android client to avoid bot detection.
    """
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    job_id = uuid.uuid4().hex[:10]
    outtmpl = str(Path(output_dir) / f"{job_id}_%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=android",
        "-f", "best[height<=720]",
        "--print-json",
        "--no-playlist",
        "--user-agent", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        "--sleep-interval", "3",
        "--max-sleep-interval", "15",
        "-o", outtmpl,
    ]

    if start is not None and end is not None:
        # Download only the specified section
        cmd += ["--download-sections", f"*{start}-{end}"]

    cmd.append(url)

    process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if process.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {process.stderr}")

    # Extract metadata from the last JSON line
    lines = process.stdout.strip().split("\n")
    info_json = lines[-1]
    metadata = json.loads(info_json)

    # Find the downloaded file
    downloaded = None
    for f in Path(output_dir).glob(f"{job_id}_*"):
        if f.suffix in (".mp4", ".mkv", ".webm"):
            downloaded = f
            break
    if not downloaded:
        raise FileNotFoundError("Downloaded video not found")

    return downloaded, metadata


def fetch_transcript(url: str) -> Optional[str]:
    """
    Retrieve YouTube auto‑generated subtitles (SRT) without downloading the video.
    Returns raw SRT text, or None if unavailable.
    """
    try:
        cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android",
            "--skip-download",
            "--write-auto-subs",
            "--sub-format", "srt",
            "--output", "-",           # print SRT to stdout
            "--no-playlist",
            "--user-agent", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
            url
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if process.returncode == 0:
            # The output contains yt-dlp info lines and then the SRT content.
            # Find the first subtitle block (starts with a digit).
            lines = process.stdout.splitlines()
            srt_start = 0
            for i, line in enumerate(lines):
                if line.strip().isdigit():
                    srt_start = i
                    break
            return "\n".join(lines[srt_start:])
        return None
    except Exception:
        return None