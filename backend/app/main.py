print("✅✅✅ HELLO FROM PYTHON", flush=True)

import os
import uuid
import threading
import traceback
import shutil
from pathlib import Path

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

    # ---------- PIPELINE FOR UPLOADED FILE ----------
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