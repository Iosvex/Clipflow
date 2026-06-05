print("✅✅✅ HELLO FROM PYTHON", flush=True)

import os
import uuid
import threading
import traceback
import shutil
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .utils.db import get_db, engine, Base
from .models import Job
from .schemas import JobCreate, JobResponse
from .config import settings

from gradio_client import Client, handle_file

app = FastAPI(title="ClipFlow API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
os.makedirs(settings.CLIP_DIR, exist_ok=True)
app.mount("/clips", StaticFiles(directory=settings.CLIP_DIR), name="clips")
Base.metadata.create_all(bind=engine)

# ---------- HEALTH CHECK ----------
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "alive"}

# ---------- Hugging Face Space connection ----------
SPACE_NAME = os.getenv("SPACE_NAME", "vexcukt/clipflow-processor")

def process_via_space(job_id: str, video_path: str):
    from .utils.db import SessionLocal
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        # Connect to the Space using the Gradio client
        client = Client(SPACE_NAME)

        # Call the process_video function on the Space
        # handle_file() marks the local path as a file input
        result = client.predict(
            video_file=handle_file(video_path),
            api_name="/process_video"
        )

        # The result is the path to the processed file (already downloaded by the client)
        # result is a string path to the local downloaded file
        if not result or not os.path.exists(result):
            raise Exception("Space did not return a valid file")

        # Move/copy to our clips directory
        clip_name = f"clip_{uuid.uuid4().hex}.mp4"
        clip_path = os.path.join(settings.CLIP_DIR, clip_name)
        shutil.move(result, clip_path)

        job.clip_path = clip_path
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
            os.unlink(video_path)
        except:
            pass

# ---------- UPLOAD ENDPOINT ----------
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

    thread = threading.Thread(target=process_via_space, args=(job.id, file_path))
    thread.start()
    return job

# ---------- YOUTUBE URL ENDPOINT ----------
@app.post("/api/jobs", response_model=JobResponse)
def create_job_from_url(payload: JobCreate, db: Session = Depends(get_db)):
    from .services.downloader import download_video
    job = Job(youtube_url=payload.youtube_url)
    db.add(job)
    db.commit()
    db.refresh(job)

    def dl_and_process():
        try:
            video_path, _ = download_video(payload.youtube_url)
            process_via_space(job.id, str(video_path))
        except Exception as e:
            session = SessionLocal()
            try:
                j = session.query(Job).filter(Job.id == job.id).first()
                if j:
                    j.status = "error"
                    j.error = str(e)
                    session.commit()
            finally:
                session.close()

    thread = threading.Thread(target=dl_and_process)
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