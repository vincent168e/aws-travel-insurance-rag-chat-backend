import logging
import uuid
from typing import List

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile, HTTPException

from src.config import settings

logger = logging.getLogger(__name__)

# Lazy-initialized S3 client — defers until first call so config is loaded
_s3_client = None


def _get_s3_client():
    """Return a cached boto3 S3 client, creating one if needed."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=settings.AWS_REGION)
    return _s3_client


def _generate_presigned_url(object_key: str, expiration: int = 3600) -> str:
    """Generate a time-limited pre-signed URL for reading a private S3 object."""
    s3 = _get_s3_client()
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_CLAIM_BUCKET, "Key": object_key},
            ExpiresIn=expiration,
        )
        return url
    except (BotoCoreError, ClientError) as exc:
        logger.error("Failed to generate pre-signed URL for key '%s': %s", object_key, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate access URL for uploaded file.",
        )


def upload_file_to_s3(
    file: UploadFile,
    thread_id: str = "unknown",
    target_prefix: str = "attachments",
) -> str:
    """
    Upload a single file stream to the private S3 claims bucket.

    Object key pattern: {prefix}/{thread_id}/{uuid}.{ext}
    Returns a pre-signed URL valid for 1 hour so downstream nodes (OCR) can
    fetch the image without requiring public bucket access.
    """
    s3 = _get_s3_client()

    # Derive a safe file extension
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    object_key = f"{target_prefix}/{thread_id}/{uuid.uuid4().hex}.{ext}"

    try:
        # Seek to start in case the stream has been partially consumed
        file.file.seek(0)
        s3.put_object(
            Bucket=settings.S3_CLAIM_BUCKET,
            Key=object_key,
            Body=file.file,
            ContentType=file.content_type or "application/octet-stream",
        )
        logger.info("Uploaded '%s' → s3://%s/%s", filename, settings.S3_CLAIM_BUCKET, object_key)
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failure for '%s': %s", filename, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed uploading file '{filename}'. Please try again.",
        )

    return _generate_presigned_url(object_key)


def upload_multiple_files_to_s3(
    files: List[UploadFile],
    thread_id: str = "unknown",
    target_prefix: str = "attachments",
) -> List[str]:
    """
    Upload a collection of files to S3 and return their pre-signed URLs.
    """
    uploaded_urls: List[str] = []
    for file in files:
        url = upload_file_to_s3(file, thread_id=thread_id, target_prefix=target_prefix)
        uploaded_urls.append(url)
    return uploaded_urls