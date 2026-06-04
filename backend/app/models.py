from sqlalchemy import Column, String, Float, Text
from .utils.db import Base
import uuid

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    youtube_url = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, processing, done, error
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    video_path = Column(String, nullable=True)
    clip_path = Column(String, nullable=True)
    error = Column(Text, nullable=True)