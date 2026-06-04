import os

class Settings:
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "/tmp/clipflow_downloads")
    CLIP_DIR: str = os.getenv("CLIP_DIR", "/tmp/clipflow_clips")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")   # kept for reference, not used with HF
    HF_API_TOKEN: str = os.getenv("HF_API_TOKEN", "")

settings = Settings()