import os
import sys
import threading
import traceback
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .utils.db import get_db, engine, Base
from .models import Job
from .schemas import JobCreate, JobResponse
from .config import settings

# Print startup info so we can see if uvicorn even loads this file
print("🔧 Starting ClipFlow main.py", flush=True)

app = FastAPI(title="ClipFlow API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve finished clips
os.makedirs(settings.CLIP_DIR, exist_ok=True)
app.mount("/clips", StaticFiles(directory=settings.CLIP_DIR), name="clips")

# Create tables on startup
Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------
# HEALTH CHECK – accepts GET and HEAD (Render will use HEAD)
# ------------------------------------------------------------
@app.get("/")
def root_get():
    return {"status": "alive"}

@app.head("/")
def root_head():
    # Return empty 200 response for HEAD requests
    return {}

# ------------------------------------------------------------
# BACKGROUND PIPELINE (unchanged)
# ------------------------------------------------------------
def run_pipeline(job_id: str, youtube_url: str):
    from .utils.db import SessionLocal
    from .services.downloader import download_video
    from .services.transcriber import transcribe
    from .services.clip_selector import select_best_clip
    from .services.trimmer import trim_and_crop
    from .services.captioner import burn_captions

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        job.status = "downloading"
        db.commit()
        video_path, metadata = download_video(youtube_url, settings.DOWNLOAD_DIR)
        job.video_path = str(video_path)

        job.status = "transcribing"
        db.commit()
        words = transcribe(video_path)

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
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error = str(e)
            db.commit()
        traceback.print_exc()
    finally:
        db.close()


@app.post("/api/jobs", response_model=JobResponse)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = Job(youtube_url=payload.youtube_url)
    db.add(job)
    db.commit()
    db.refresh(job)

    thread = threading.Thread(target=run_pipeline, args=(job.id, job.youtube_url))
    thread.start()
    return job


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
        error=job.error
    )