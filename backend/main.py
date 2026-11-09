import logging
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

logging.basicConfig(level=logging.INFO,
                                 format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                                 datefmt='%Y-%m-%d %H:%M:%S',
                                 stream=sys.stdout
                                 )

logger = logging.getLogger(__name__) # Пример использования логера: logger.info("Some info")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title='Test_name', lifespan=lifespan)
START_TIME = datetime.now(UTC)


@app.get("/health", tags=["system"])
async def health_check():
    now = datetime.now(UTC)
    return {
        "status": "ok",
        "version": app.version,
        "uptime_seconds": round((now - START_TIME).total_seconds(), 2),
        "timestamp": now.isoformat(),
    }
