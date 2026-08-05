import logging
from typing import List
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage

from src.schemas import ChatRequest, ChatResponse
from src.graph.workflow import app_graph
from src.config import settings
from src.services.img_storage import upload_multiple_files_to_s3


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cobalt Cross Travel Insurance RAG Chat Backend API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.LOCAL_FRONTEND_CLIENT_URL,
        settings.EXTERNAL_FRONTEND_CLIENT_URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    try:
        config = {"configurable": {"thread_id": payload.thread_id}}
        
        if payload.service_category == "inquiry" and payload.claim_stage is None:
            try:
                app_graph.update_state(config, {"claim_stage": None})
            except Exception:
                pass
        
        output = app_graph.invoke(
            {
                "messages": [HumanMessage(content=payload.message)],
                "user_input": payload.message,
                "service_category": payload.service_category,
                "claim_category": payload.claim_category,
                "claim_description": payload.claim_description,
                "claim_stage": payload.claim_stage,
                "image_urls": payload.image_urls,
            },
            config=config
        )
        
        return ChatResponse(
            thread_id=payload.thread_id,
            response=output.get("final_response", ""),
            service_category=output.get("service_category"),
            claim_category=output.get("claim_category"),
            claim_description=output.get("claim_description"),
            session_closed=bool(output.get("session_closed", False)),
            claim_stage=output.get("claim_stage"),
            audit_report=output.get("audit_report"),
        )
        
    except Exception as e:
        logger.error("Exception processing conversation payload: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload")
async def upload_images_endpoint(
    files: List[UploadFile] = File(...),
    thread_id: str = "unknown",
):
    """
    Accept incoming multi-part binary file streams, store them in the private
    S3 claims bucket, and return time-limited pre-signed URLs for downstream
    OCR processing.
    """
    urls = upload_multiple_files_to_s3(files, thread_id=thread_id)
    return {"image_urls": urls}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}