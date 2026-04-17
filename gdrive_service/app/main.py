from fastapi import FastAPI

from app.api.routes import health, resources


app = FastAPI(title="DiscoHack Google Drive API Proxy")

app.include_router(health.router)
app.include_router(resources.router)
