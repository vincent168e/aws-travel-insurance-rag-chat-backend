import logging
from typing import List
from fastapi import UploadFile, HTTPException
import cloudinary
import cloudinary.uploader

from src.config import settings


logger = logging.getLogger(__name__)

# Core SDK Initialization orchestrated on module load
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)

def upload_file_to_cloudinary(file: UploadFile, target_folder: str = "travel-insurance-rag-chat/attachments") -> str:
    """
    Uploads a single file stream binary to Cloudinary.
    Returns the securely signed CDN URL string.
    """
    try:
        upload_result = cloudinary.uploader.upload(
            file.file,
            folder=target_folder,
        )
        
        secure_url = upload_result.get("secure_url")
        if not secure_url:
            raise ValueError("Upload sequence completed but no valid secure_url was returned by CDN.")
            
        return secure_url
        
    except Exception as e:
        logger.error("Cloudinary single asset upload failure for file '%s': %s", file.filename, str(e))
        raise HTTPException(
            status_code=500, 
            detail=f"Failed uploading file asset '{file.filename}': {str(e)}"
        )


def upload_multiple_files_to_cloudinary(files: List[UploadFile], target_folder: str = "travel-insurance-rag-chat/attachments") -> List[str]:
    """
    Iteratively uploads a collection of binary payload streams to the cloud provider.
    """
    uploaded_urls = []
    for file in files:
        url = upload_file_to_cloudinary(file, target_folder=target_folder)
        uploaded_urls.append(url)
    return uploaded_urls