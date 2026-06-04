"""
ARQ worker entry point.
Run with: arq worker.WorkerSettings --queue clipflow
"""

from arq import Worker
from arq.connections import RedisSettings
from backend.app.tasks import process_job
import os
import urllib.parse

async def startup(ctx):
    print("Worker started")

async def shutdown(ctx):
    print("Worker shutting down")

# Parse Redis URL into RedisSettings
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
parsed = urllib.parse.urlparse(redis_url)
redis_settings = RedisSettings(
    host=parsed.hostname,
    port=parsed.port or (6380 if parsed.scheme == "rediss" else 6379),
    password=parsed.password,
    ssl=parsed.scheme == "rediss",
)

class WorkerSettings:
    functions = [process_job]
    redis_settings = redis_settings
    on_startup = startup
    on_shutdown = shutdown