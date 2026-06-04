"""
Trims a video to the given segment and crops/resizes to 9:16 (1080×1920).
"""

import ffmpeg
from pathlib import Path
from ..config import settings
import os
import uuid

def trim_and_crop(
    input_path: Path,
    start: float,
    end: float,
    output_dir: str = None,
    target_width: int = 1080,
    target_height: int = 1920,
) -> Path:
    """
    Trims video from start to end (seconds), then resizes+crops to vertical 9:16.
    Returns path to the final MP4.
    """
    if output_dir is None:
        output_dir = settings.CLIP_DIR
    os.makedirs(output_dir, exist_ok=True)

    job_id = uuid.uuid4().hex[:8]
    output_path = Path(output_dir) / f"clip_{job_id}.mp4"

    (
        ffmpeg
        .input(str(input_path), ss=start, t=end - start)
        .filter("scale", target_width, -2)          # scale width to 1080, keep aspect ratio
        .filter("crop", target_width, target_height) # crop to 1080×1920 (center crop)
        .output(str(output_path), vcodec="libx264", acodec="aac", preset="fast", crf=23)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path