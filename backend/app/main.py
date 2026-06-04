from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .utils.db import get_db, engine, Base
from .models import Job
from .schemas import JobCreate, JobResponse
from .config import settings
from arq import create_pool
import os

app = FastAPI(title="ClipFlow API")

# CORS for frontend (localhost dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount clip directory for serving finished videos
os.makedirs(settings.CLIP_DIR, exist_ok=True)
app.mount("/clips", StaticFiles(directory=settings.CLIP_DIR), name="clips")

# Create tables on startup
Base.metadata.create_all(bind=engine)

@app.on_event("startup")
async def startup():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise Exception("REDIS_URL environment variable not set")
    app.state.redis = await create_pool(redis_url)

@app.on_event("shutdown")
async def shutdown():
    if app.state.redis:
        await app.state.redis.close()

@app.post("/api/jobs", response_model=JobResponse)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = Job(youtube_url=payload.youtube_url)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue background task (requires running ARQ worker)
    # For now, we'll just simulate; real enqueue would be:
    # await app.state.redis.enqueue_job("process_job", job.id, job.youtube_url)
    # Since we don't have a worker yet, we skip actual processing
    return job

@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = JobResponse(
        id=job.id,
        youtube_url=job.youtube_url,
        status=job.status,
        start_time=job.start_time,
        end_time=job.end_time,
        clip_url=f"/clips/{os.path.basename(job.clip_path)}" if job.clip_path else None,
        error=job.error
    )
    return response