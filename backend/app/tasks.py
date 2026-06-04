"""
Background job pipeline using ARQ (async Redis queue).
"""

from pathlib import Path
from .services.downloader import download_video
from .services.transcriber import transcribe
from .services.clip_selector import select_best_clip
from .services.trimmer import trim_and_crop
from .services.captioner import burn_captions
from .utils.db import SessionLocal
from .models import Job
from .config import settings

async def process_job(job_id: str, youtube_url: str):
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return

    try:
        # 1. Download
        job.status = "downloading"
        db.commit()
        video_path, metadata = download_video(youtube_url, settings.DOWNLOAD_DIR)
        job.video_path = str(video_path)

        # 2. Transcribe
        job.status = "transcribing"
        db.commit()
        words = transcribe(video_path)

        # 3. Select best clip
        job.status = "selecting"
        db.commit()
        start, end = select_best_clip(video_path, metadata, words)
        job.start_time = start
        job.end_time = end

        # 4. Trim & crop
        job.status = "trimming"
        db.commit()
        trimmed = trim_and_crop(video_path, start, end, settings.CLIP_DIR)

        # 5. Burn captions
        job.status = "captioning"
        db.commit()
        final_clip = burn_captions(trimmed, words, settings.CLIP_DIR)
        job.clip_path = str(final_clip)

        job.status = "done"
        db.commit()

    except Exception as e:
        job.status = "error"
        job.error = str(e)
        db.commit()
    finally:
        db.close()