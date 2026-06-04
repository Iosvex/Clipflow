from pydantic import BaseModel, HttpUrl
from typing import Optional

class JobCreate(BaseModel):
    youtube_url: str

class JobResponse(BaseModel):
    id: str
    youtube_url: str
    status: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    clip_url: Optional[str] = None
    error: Optional[str] = None