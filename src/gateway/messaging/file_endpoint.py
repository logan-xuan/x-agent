"""
File upload/download API endpoints for the x-agent2 AI assistant system.

This module handles file operations for the chat system including:
- File uploads with validation
- File downloads
- File management
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import os
from typing import Optional
import shutil
from datetime import datetime
import uuid
from pathlib import Path

router = APIRouter(prefix="/files", tags=["files"])

# Configure upload directory
UPLOAD_DIR = Path("workspace/user-files")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Maximum file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",  # Images
    ".txt", ".csv", ".pdf", ".json",  # Documents
    ".doc", ".docx", ".xls", ".xlsx",  # Office
    ".zip", ".rar", ".tar", ".gz"  # Archives
}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(...)
):
    """
    Upload a file to the system.

    Args:
        file: The file to upload
        session_id: The session ID to associate with the file

    Returns:
        JSON response with upload details
    """
    # Validate file size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024):.2f} MB"
        )

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_ext}' is not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Create session directory
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(exist_ok=True)

    # Generate unique filename to prevent conflicts
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = session_dir / unique_filename

    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "status": "success",
            "file_path": str(file_path),
            "filename": unique_filename,
            "original_filename": file.filename,
            "size": len(file_content),
            "extension": file_ext,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {str(e)}"
        )


@router.get("/download/{session_id}/{filename}")
async def download_file(
    session_id: str,
    filename: str
):
    """
    Download a file by session ID and filename.

    Args:
        session_id: The session ID associated with the file
        filename: The filename to download

    Returns:
        File download response
    """
    file_path = UPLOAD_DIR / session_id / filename

    # Validate the file path to prevent directory traversal
    if not file_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(
            status_code=400,
            detail="Invalid file path"
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    def iterfile():
        with open(file_path, 'rb') as f:
            yield from f

    return StreamingResponse(
        iterfile(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.delete("/delete/{session_id}/{filename}")
async def delete_file(
    session_id: str,
    filename: str
):
    """
    Delete a file by session ID and filename.

    Args:
        session_id: The session ID associated with the file
        filename: The filename to delete

    Returns:
        JSON response with deletion status
    """
    file_path = UPLOAD_DIR / session_id / filename

    # Validate the file path to prevent directory traversal
    if not file_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(
            status_code=400,
            detail="Invalid file path"
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    try:
        file_path.unlink()
        return {
            "status": "success",
            "message": "File deleted successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file: {str(e)}"
        )


@router.get("/list/{session_id}")
async def list_files(
    session_id: str
):
    """
    List all files associated with a session.

    Args:
        session_id: The session ID to list files for

    Returns:
        JSON response with list of files
    """
    session_dir = UPLOAD_DIR / session_id

    if not session_dir.exists():
        return {
            "session_id": session_id,
            "files": [],
            "count": 0
        }

    files = []
    for file_path in session_dir.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            files.append({
                "filename": file_path.name,
                "size": stat.st_size,
                "extension": file_path.suffix,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x["modified_at"], reverse=True)

    return {
        "session_id": session_id,
        "files": files,
        "count": len(files)
    }


@router.get("/info/{session_id}/{filename}")
async def get_file_info(
    session_id: str,
    filename: str
):
    """
    Get information about a specific file.

    Args:
        session_id: The session ID associated with the file
        filename: The filename to get info for

    Returns:
        JSON response with file information
    """
    file_path = UPLOAD_DIR / session_id / filename

    # Validate the file path to prevent directory traversal
    if not file_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(
            status_code=400,
            detail="Invalid file path"
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    stat = file_path.stat()
    return {
        "filename": filename,
        "session_id": session_id,
        "size": stat.st_size,
        "extension": file_path.suffix,
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "is_image": file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    }


# Register the router in the main app
def register_file_routes(app):
    """
    Register file routes with the main application.

    Args:
        app: The FastAPI application instance
    """
    app.include_router(router)