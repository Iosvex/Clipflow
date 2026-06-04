"""
Placeholder for Instagram / TikTok auto-upload.
We will integrate instagrapi and tiktok-uploader here later.
"""

from pathlib import Path

def upload_to_instagram(video_path: Path, username: str, password: str):
    """
    (Future) Upload a video as a Reel using instagrapi.
    Requires valid session cookies.
    """
    raise NotImplementedError("Instagram upload not yet integrated")

def upload_to_tiktok(video_path: Path, session_file: Path):
    """
    (Future) Upload a video to TikTok using tiktok-uploader.
    Requires a saved browser session.
    """
    raise NotImplementedError("TikTok upload not yet integrated")