import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
from routes import chat, webhook, quiz
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VORA AI Stylist API", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)



app.include_router(chat.router, prefix="/api")
app.include_router(webhook.router, prefix="/webhook")
app.include_router(quiz.router, prefix="/api")





@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "vora-ai", "version": "1.0.0"}

@app.get("/")
async def root():
    return {"message": "VORA AI Stylist API is running"}

@app.on_event("startup")
async def startup_event():
    logger.info("VORA AI backend starting...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("VORA AI backend shutting down...")

# Note: Routers for chat and webhooks will be added in Phase 6

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)