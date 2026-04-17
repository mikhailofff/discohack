from fastapi import FastAPI

app = FastAPI(title="DiscoHack WebDAV API")


@app.get("/")
async def read_root():
    return {"status": "working", "message": "Hello from discohack!"}