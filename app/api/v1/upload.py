from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import os
import uuid
from pathlib import Path
from datetime import datetime

try:
    import boto3
except Exception:  # pragma: no cover - optional dependency in dev
    boto3 = None

from ...lib.security import get_current_user
from ...models.user import User

router = APIRouter(prefix="/api/v1/upload", tags=["upload"])

# Create uploads directory if it doesn't exist
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().strip("\"").strip("'")


def _upload_to_s3_if_configured(content: bytes, filename: str, content_type: str | None, user_id: str) -> dict | None:
    aws_access_key = _clean_env_value(os.getenv("AWS_ACCESS_KEY"))
    aws_secret_key = _clean_env_value(os.getenv("AWS_SECRET_KEY"))
    aws_region = _clean_env_value(os.getenv("AWS_REGION"))
    bucket = _clean_env_value(os.getenv("AWS_S3_BUCKET"))

    has_s3_config = bool(aws_access_key and aws_secret_key and aws_region and bucket)
    if not has_s3_config or boto3 is None:
        return None

    s3_key = f"uploads/{user_id}/{filename}"

    client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )

    client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=content,
        ContentType=content_type or "application/octet-stream",
    )

    s3_url = f"https://{bucket}.s3.{aws_region}.amazonaws.com/{s3_key}"
    return {"url": s3_url, "key": s3_key, "storage": "s3"}


def validate_file(file: UploadFile) -> bool:
    """Validate file type and size"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    return True


@router.post("/image", status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload an image file.
    
    - Accepts: JPG, JPEG, PNG, GIF, WebP
    - Max size: 10MB
    - Returns: URL path to access the image
    """
    try:
        # Validate file
        validate_file(file)
        
        # Read file content
        content = await file.read()
        
        # Check file size
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
            )
        
        # Generate unique filename
        file_ext = Path(file.filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        
        s3_result = _upload_to_s3_if_configured(
            content=content,
            filename=unique_filename,
            content_type=file.content_type,
            user_id=str(current_user.uid),
        )

        if s3_result is not None:
            file_url = s3_result["url"]
            storage = s3_result["storage"]
        else:
            # Fallback to local uploads when S3 is not configured.
            user_upload_dir = UPLOAD_DIR / str(current_user.uid)
            user_upload_dir.mkdir(exist_ok=True)

            file_path = user_upload_dir / unique_filename
            with open(file_path, "wb") as f:
                f.write(content)

            file_url = f"/uploads/{current_user.uid}/{unique_filename}"
            storage = "local"
        
        return {
            "url": file_url,
            "filename": unique_filename,
            "original_filename": file.filename,
            "size": len(content),
            "uploaded_at": datetime.utcnow().isoformat(),
            "storage": storage,
        }
    
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500, 
            detail="Failed to upload file"
        )


@router.post("/profile-image", status_code=201)
async def upload_profile_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a profile image for the current user.
    Replaces previous profile image if one exists.
    """
    try:
        # Validate file
        validate_file(file)
        
        # Read file content
        content = await file.read()
        
        # Check file size
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
            )
        
        # Generate unique filename with profile prefix
        file_ext = Path(file.filename).suffix.lower()
        unique_filename = f"profile_{uuid.uuid4()}{file_ext}"
        
        s3_result = _upload_to_s3_if_configured(
            content=content,
            filename=unique_filename,
            content_type=file.content_type,
            user_id=str(current_user.uid),
        )

        if s3_result is not None:
            file_url = s3_result["url"]
            storage = s3_result["storage"]
        else:
            # Fallback to local uploads when S3 is not configured.
            user_upload_dir = UPLOAD_DIR / str(current_user.uid)
            user_upload_dir.mkdir(exist_ok=True)

            # Clean up old profile images (optional)
            for existing_file in user_upload_dir.glob("profile_*"):
                try:
                    existing_file.unlink()
                except Exception:
                    pass

            file_path = user_upload_dir / unique_filename
            with open(file_path, "wb") as f:
                f.write(content)

            file_url = f"/uploads/{current_user.uid}/{unique_filename}"
            storage = "local"
        
        return {
            "url": file_url,
            "filename": unique_filename,
            "original_filename": file.filename,
            "size": len(content),
            "uploaded_at": datetime.utcnow().isoformat(),
            "storage": storage,
        }
    
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500, 
            detail="Failed to upload profile image"
        )
