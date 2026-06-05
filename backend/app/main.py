print("✅✅✅ HELLO FROM PYTHON", flush=True)

import os
import uuid
import threading
import traceback
import shutil
import re
from pathlib import Path
from datetime import timedelta

try:
    from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from sqlalchemy.orm import Session
    from .utils.db import get_db, engine, Base
    from .models import Job
    from .schemas import JobCreate, JobResponse
    from .config import settings
    print("✅ ALL IMPORTS SUCCESSFUL", flush=True)

    app = FastAPI(title="ClipFlow API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    os.makedirs(settings.CLIP_DIR, exist_ok=True)
    app.mount("/clips", StaticFiles(directory=settings.CLIP_DIR), name="clips")
    Base.metadata.create_all(bind=engine)

    # ---------- HEALTH CHECK ----------
    @app.api_route("/", methods=["GET", "HEAD"])
    def root():
        return {"status": "alive"}

    # ---------- SRT PARSER ----------
    def parse_srt(srt_text: str) -> list:
        """
        Convert SRT content to a list of word dicts (like transcriber output).
        We'll approximate word‑level timestamps by spreading words across the subtitle block.
        """
        words = []
        # Split into blocks (each block: index, timestamp line, text lines)
        blocks = re.split(r'\n\s*\n', srt_text.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            # Second line should be the timestamp "00:00:01,000 --> 00:00:04,000"
            time_match = re.search(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
            if not time_match:
                continue
            start_str, end_str = time_match.groups()
            start = _srt_time_to_seconds(start_str)
            end = _srt_time_to_seconds(end_str)
            # Text lines (could be multiple)
            text = " ".join(lines[2:])
            # Split text into words and distribute them evenly across the time span
            word_list = text.split()
            if not word_list:
                continue
            word_duration = (end - start) / len(word_list)
            for i, w in enumerate(word_list):
                word_start = start + i * word_duration
                word_end = word_start + word_duration
                words.append({
                    "word": w,
                    "start": word_start,
                    "end": word_end,
                    "score": 0.9
                })
        return words

    def _srt_time_to_seconds(srt_time: str) -> float:
        """Convert '00:00:01,234' -> 1.234 seconds"""
        h, m, s_ms = srt_time.split(":")
        s, ms = s_ms.split(",")
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

    # ---------- PIPELINE FOR YOUTUBE URL (transcript first) ----------
    def run_pipeline(job_id: str, youtube_url: str):
        from .utils.db import SessionLocal
        from .services.downloader import fetch_transcript, download_video
        from .services.transcriber import transcribe
        from .services.clip_selector import select_best_clip
        from .services.trimmer import trim_and_crop
        from .services.captioner import burn_captions

        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return

            # 1. Try to get transcript first (tiny, never blocked)
            job.status = "fetching transcript"
            db.commit()
            srt = fetch_transcript(youtube_url)

            if srt:
                words = parse_srt(srt)
                # Fake metadata (heatmap not available)
                metadata = {"duration": 0, "heatmap": None}
                start, end = select_best_clip(None, metadata, words)
                job.start_time = start
                job.end_time = end

                # 2. Download only that segment
                job.status = "downloading clip"
                db.commit()
                video_path, _ = download_video(youtube_url, settings.DOWNLOAD_DIR,
                                               start=start, end=end)
            else:
                # Fallback: full download + transcribe (or use user upload)
                # This triggers only if auto‑subs are disabled or missing.
                job.status = "downloading full video"
                db.commit()
                video_path, metadata = download_video(youtube_url)
                words = transcribe(video_path)
                start, end = select_best_clip(video_path, metadata, words)

            # 3. Trim & crop to 9:16
            job.status = "trimming"
            db.commit()
            trimmed = trim_and_crop(video_path, start, end, settings.CLIP_DIR)

            # 4. Burn captions (using the words we have)
            job.status = "captioning"
            db.commit()
            final_clip = burn_captions(trimmed, words, settings.CLIP_DIR)
            job.clip_path = str(final_clip)

            job.status = "done"
            db.commit()

        except Exception as e:
            db.rollback()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.status = "error"
                    job.error = str(e)
                    db.commit()
            except:
                pass
            traceback.print_exc()
        finally:
            db.close()

    # ---------- PIPELINE FOR UPLOADED FILE (unchanged) ----------
    def run_pipeline_with_file(job_id: str, file_path: str):
        from .utils.db import SessionLocal
        from .services.transcriber import transcribe
        from .services.clip_selector import select_best_clip
        from .services.trimmer import trim_and_crop
        from .services.captioner import burn_captions

        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return
            video_path = Path(file_path)

            job.status = "transcribing"
            db.commit()
            words = transcribe(video_path)

            metadata = {"duration": 0, "heatmap": None}

            job.status = "selecting"
            db.commit()
            start, end = select_best_clip(video_path, metadata, words)
            job.start_time = start
            job.end_time = end

            job.status = "trimming"
            db.commit()
            trimmed = trim_and_crop(video_path, start, end, settings.CLIP_DIR)

            job.status = "captioning"
            db.commit()
            final_clip = burn_captions(trimmed, words, settings.CLIP_DIR)
            job.clip_path = str(final_clip)

            job.status = "done"
            db.commit()

        except Exception as e:
            db.rollback()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.status = "error"
                    job.error = str(e)
                    db.commit()
            except:
                pass
            traceback.print_exc()
        finally:
            db.close()
            try:
                os.unlink(file_path)
            except:
                pass

    # ---------- YOUTUBE URL ENDPOINT ----------
    @app.post("/api/jobs", response_model=JobResponse)
    def create_job_from_url(payload: JobCreate, db: Session = Depends(get_db)):
        job = Job(youtube_url=payload.youtube_url)
        db.add(job)
        db.commit()
        db.refresh(job)

        thread = threading.Thread(target=run_pipeline, args=(job.id, job.youtube_url))
        thread.start()
        return job

    # ---------- FILE UPLOAD ENDPOINT ----------
    @app.post("/api/jobs/upload", response_model=JobResponse)
    async def create_job_from_upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
        upload_dir = "/tmp/clipflow_uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_ext = Path(file.filename).suffix
        local_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(upload_dir, local_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        job = Job(youtube_url=f"upload:{file.filename}")
        db.add(job)
        db.commit()
        db.refresh(job)

        thread = threading.Thread(target=run_pipeline_with_file, args=(job.id, file_path))
        thread.start()
        return job

    # ---------- JOB STATUS ----------
    @app.get("/api/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str, db: Session = Depends(get_db)):
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobResponse(
            id=job.id,
            youtube_url=job.youtube_url,
            status=job.status,
            start_time=job.start_time,
            end_time=job.end_time,
            clip_url=f"/clips/{os.path.basename(job.clip_path)}" if job.clip_path else None,
            error=job.error,
        )

    print("✅ APP FULLY READY", flush=True)

except Exception as e:
    print(f"❌ STARTUP ERROR: {e}", flush=True)
    raise