import subprocess
import json
import os
import uuid
import base64
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from ..config import settings

def download_video(url: str, output_dir: Optional[str] = None) -> Tuple[Path, dict]:
    if output_dir is None:
        output_dir = settings.DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Decode cookies from environment variable
    cookies_b64 = os.getenv("YOUTUBE_COOKIES_BASE64", "")
    cookie_path = None
    if cookies_b64:
        cookie_data = base64.b64decode(cookies_b64).decode("utf-8")
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write(cookie_data)
        tmp.close()
        cookie_path = tmp.name

    job_id = uuid.uuid4().hex[:10]
    output_template = str(Path(output_dir) / f"{job_id}_%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        # Use the web client (needed for cookies) with cookies and JS runtime
        "--extractor-args", "youtube:player_client=web",
        # Reliable format: best video+audio under 720p, merged as mp4
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "--print-json",
        "--no-playlist",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "--sleep-interval", "3",
        "--max-sleep-interval", "15",
        # Reference deno by name (it’s in PATH now)
        "--js-runtimes", "deno",
        "-o", output_template,
    ]

    if cookie_path:
        cmd += ["--cookies", cookie_path]

    cmd.append(url)

    process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if cookie_path:
        os.unlink(cookie_path)

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