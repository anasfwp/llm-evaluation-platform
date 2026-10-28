from fastapi import APIRouter

from app.api.v1.endpoints import comparisons, datasets, models, projects, runs

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(datasets.router)
api_router.include_router(models.router)
api_router.include_router(runs.router)
api_router.include_router(comparisons.router)
