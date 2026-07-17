"""Document upload endpoint for Session KB."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.models.schemas import UploadResponse
from backend.app.services.kb_service import get_kb_service
from src.utils.document_loader import SUPPORTED_EXTENSIONS
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> UploadResponse:
    """
    Build / replace the Session KB for ``session_id`` from an uploaded file.

    Accepts PDF, DOCX, TXT. Processing uses existing SessionKnowledgeBase.build.
    """
    filename = file.filename or ""
    if not filename.strip():
        raise HTTPException(status_code=400, detail="Uploaded file has no name")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Use PDF, DOCX, or TXT.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    service = get_kb_service()
    try:
        result = service.upload_to_session(session_id, filename, data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not result["success"]:
        logger.warning("Upload failed for session %s: %s", session_id, result["message"])
        raise HTTPException(status_code=400, detail=result["message"])

    return UploadResponse(**result)
