import os
from fastapi import FastAPI
from .core.config import settings
from .database import engine, Base
from .api.endpoints import regions, items, status, refresh
from .tasks.scheduler import init_scheduler
from .core.logging_config import setup_logging

setup_logging()

app = FastAPI(
    title="EVE Online Market Analysis API",
    description="API for analyzing the EVE Online market to find profitable items.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    # Only run database creation and scheduler init in a non-testing environment
    if os.environ.get("TESTING") != "1":
        Base.metadata.create_all(bind=engine)
        await init_scheduler()

app.include_router(regions.router, prefix=settings.API_V1_STR, tags=["regions"])
app.include_router(items.router, prefix=settings.API_V1_STR, tags=["items"])
app.include_router(status.router, prefix=settings.API_V1_STR, tags=["status"])
app.include_router(refresh.router, prefix=settings.API_V1_STR, tags=["refresh"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the EVE Online Market Analysis API"}