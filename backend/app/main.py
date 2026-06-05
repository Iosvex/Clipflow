print("✅✅✅ HELLO FROM PYTHON", flush=True)

import os
import uuid
import threading
import traceback
import shutil
import requests
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .utils.db import get_db, engine, Base
from .models import Job
from .schemas import JobCreate, JobResponse
from .config import settings

app = FastAPI(title="ClipFlow API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
os.makedirs(settings.CLIP_DIR, exist_ok=True)
app.mount("/clips", StaticFiles(directory=settings.CLIP_DIR), name="clips")
Base.metadata.create_all(bind=engine)

# ---------- HEALTH CHECK ----------
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "alive"}

# ---------- Hugging Face Space URL ----------
HF_SPACE_URL = os.getenv("HF_SPACE_URL", "https://vexcukt-clipflow-processor.hf.space")
PROCESS_ENDPOINT = f"{HF_SPACE_URL}/api/predict"

# ---------- PROCESSING FUNCTION (sends video to Space) ----------
def process_via_space(job_id: str, video_path: str):
    from .utils.db import SessionLocal
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        # Send video to Space (Gradio API expects a file in the request)
        with open(video_path, "rb") as f:
            files = {"file": f}
            response = requests.post(PROCESS_ENDPOINT, files=files, timeout=600)

        if response.status_code != 200:
            raise Exception(f"Space API returned {response.status_code}: {response.text}")

        result = response.json()
        if "data" not in result or not result["data"]:
            raise Exception("Empty response from Space")

        # The Space returns a relative path or full URL for the output file
        file_ref = result["data"][0]
        if file_ref.startswith("http"):
            download_url = file_ref
        else:
            download_url = f"{HF_SPACE_URL.rstrip('/')}{file_ref}"

        # Download the finished clip to our clips directory
        clip_name = f"clip_{uuid.uuid4().hex}.mp4"
        clip_path = os.path.join(settings.CLIP_DIR, clip_name)
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(clip_path, "wb") as out_file:
                for chunk in r.iter_content(chunk_size=8192):
                    out_file.write(chunk)

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

# ---------- YOUTUBE URL ENDPOINT (optional – keep if you still want it) ----------
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