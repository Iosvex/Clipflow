import os
import threading
import traceback
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from .utils.db import get_db, engine, Base
from .models import Job
from .schemas import JobCreate, JobResponse
from .config import settings

app = FastAPI(title="ClipFlow API")

# ------------------------------------------------------------
# MIDDLEWARE – catch all HEAD requests and return 200 (for Render health check)
# ------------------------------------------------------------
@app.middleware("http")
async def catch_head_requests(request: Request, call_next):
    if request.method == "HEAD":
        # Return a minimal 200 response so Render sees the service as healthy
        return JSONResponse(content={}, status_code=200)
    response = await call_next(request)
    return response

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

# (Optional) keep the root route for GET requests
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "alive", "service": "ClipFlow"}


# ------------------------------------------------------------
# BACKGROUND PIPELINE (thread‑based, no Redis/worker)
# ------------------------------------------------------------
def run_pipeline(job_id: str, youtube_url: str):
    # … (your existing pipeline code – unchanged)
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
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error = str(e)
            db.commit()
        traceback.print_exc()
    finally:
        db.close()


# ------------------------------------------------------------
# API ROUTES
# ------------------------------------------------------------
@app.post("/api/jobs", response_model=JobResponse)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = Job(youtube_url=payload.youtube_url)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Fire background thread
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