"""
ARQ worker entry point.
Run with: arq worker.WorkerSettings --queue clipflow
"""

from arq import Worker
from arq.connections import RedisSettings
from backend.app.tasks import process_job

async def startup(ctx):
    print("Worker started")

async def shutdown(ctx):
    print("Worker shutting down")

class WorkerSettings:
    functions = [process_job]
    redis_settings = RedisSettings(host="localhost", port=6379)
    on_startup = startup
    on_shutdown = shutdown