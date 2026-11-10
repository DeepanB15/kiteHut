from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import repositories
from .database import init_db

app = FastAPI(
    title="RepoLens API",
    description="AI-powered repository intelligence and engineering analysis platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repositories.router, prefix="", tags=["repositories"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "repolens-api"}

@app.on_event("startup")
def startup():
    init_db()
