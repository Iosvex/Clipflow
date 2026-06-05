import os
import uuid
from pathlib import Path
import ffmpeg
from ..config import settings

# Point ffmpeg to the static binary we downloaded
FFMPEG_BINARY = os.path.join(os.path.dirname(__file__), '..', 'ffmpeg')
FFPROBE_BINARY = os.path.join(os.path.dirname(__file__), '..', 'ffprobe')
os.environ["FFMPEG_BINARY"] = FFMPEG_BINARY
os.environ["FFPROBE_BINARY"] = FFPROBE_BINARY

def trim_and_crop(input_path: Path, start: float, end: float,
                  output_dir: str = None, target_width: int = 1080,
                  target_height: int = 1920) -> Path:
    if output_dir is None:
        output_dir = settings.CLIP_DIR
    os.makedirs(output_dir, exist_ok=True)

    job_id = uuid.uuid4().hex[:8]
    output_path = Path(output_dir) / f"clip_{job_id}.mp4"

    (
        ffmpeg
        .input(str(input_path), ss=start, t=end - start)
        .filter("scale", target_width, -2)
        .filter("crop", target_width, target_height)
        .output(str(output_path), vcodec="libx264", acodec="aac", preset="fast", crf=23)
        .overwrite_output()
        .run(cmd=FFMPEG_BINARY, quiet=True)
    )
    return output_path