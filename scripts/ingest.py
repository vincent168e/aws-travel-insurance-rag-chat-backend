"""Policy document ingestion pipeline.

Reads one or more PDF files from an S3 bucket prefix, chunks them, generates
embeddings via Gemini, and upserts vectors into Pinecone.

Usage:
  # Ingest all PDFs from the default S3 prefix
  python scripts/ingest.py --bucket dev-travel-insurance-claims-123456789012 --prefix policies/

  # Ingest with a custom policy tier label
  python scripts/ingest.py --bucket my-bucket --prefix policies/ --policy-tier "Premium Plan"

  # Reset the Pinecone index before ingesting (full re-index)
  python scripts/ingest.py --bucket my-bucket --reset-index

  # Adjust chunking parameters
  python scripts/ingest.py --bucket my-bucket --chunk-size 800 --chunk-overlap 150

Environment variables required:
  GEMINI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME, AWS_REGION
"""

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pinecone import Pinecone, ServerlessSpec

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Ensure the src package is importable
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.config import settings
from src.database.pinecone_client import embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_POLICY_TIER = "Single-trip solutions Canada package"
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
BATCH_SIZE = 50  # Upsert vectors in batches of 50 to limit memory pressure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


def list_pdf_keys(bucket: str, prefix: str) -> list[str]:
    """Return S3 object keys ending in .pdf under the given prefix."""
    s3 = _s3_client()
    keys: list[str] = []

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".pdf"):
                keys.append(key)

    if not keys:
        logger.warning("No PDF files found in s3://%s/%s", bucket, prefix)

    return keys


def download_pdf(bucket: str, key: str, dest: Path) -> None:
    """Download a single S3 object to a local temporary path."""
    s3 = _s3_client()
    logger.info("Downloading s3://%s/%s → %s", bucket, key, dest)
    s3.download_file(bucket, key, str(dest))


def ensure_index(pc: Pinecone, index_name: str, reset: bool) -> None:
    """Create the Pinecone index if missing; optionally delete and recreate."""
    existing = pc.list_indexes().names()

    if reset and index_name in existing:
        logger.info("Resetting Pinecone index '%s'...", index_name)
        pc.delete_index(index_name)

    if index_name not in pc.list_indexes().names():
        logger.info("Creating Pinecone index '%s' (1536-d, cosine)...", index_name)
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )


def process_pdf(
    pdf_path: Path,
    source_key: str,
    policy_tier: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict]:
    """Load, chunk, and embed a single PDF. Returns list of (id, vector, metadata)."""
    logger.info("Loading PDF: %s", source_key)
    loader = PyPDFLoader(str(pdf_path))
    documents = loader.load()
    logger.info("  Pages loaded: %d", len(documents))

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = text_splitter.split_documents(documents)
    logger.info("  Chunks produced: %d", len(chunks))

    vectors: list[dict] = []
    for i, chunk in enumerate(chunks):
        vector = embeddings.embed_query(chunk.page_content)
        chunk_id = f"{Path(source_key).stem}__chunk_{i}"
        metadata = {
            "text": chunk.page_content,
            "page": chunk.metadata.get("page", 0),
            "source": source_key,
            "policy_tier": policy_tier,
        }
        vectors.append({"id": chunk_id, "values": vector, "metadata": metadata})

    return vectors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_ingestion(
    bucket: str,
    prefix: str,
    policy_tier: str,
    chunk_size: int,
    chunk_overlap: int,
    reset_index: bool,
) -> None:
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index_name = settings.PINECONE_INDEX_NAME

    ensure_index(pc, index_name, reset=reset_index)
    index = pc.Index(index_name)

    pdf_keys = list_pdf_keys(bucket, prefix)
    if not pdf_keys:
        logger.error("No PDFs to ingest. Exiting.")
        sys.exit(1)

    logger.info("Found %d PDF(s) to ingest under s3://%s/%s", len(pdf_keys), bucket, prefix)

    total_chunks = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        for pdf_key in pdf_keys:
            local_path = tmp / Path(pdf_key).name
            download_pdf(bucket, pdf_key, local_path)

            vectors = process_pdf(
                local_path,
                source_key=pdf_key,
                policy_tier=policy_tier,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            # Upsert in batches
            for batch_start in range(0, len(vectors), BATCH_SIZE):
                batch = vectors[batch_start : batch_start + BATCH_SIZE]
                index.upsert(vectors=[(v["id"], v["values"], v["metadata"]) for v in batch])
                logger.info(
                    "  Upserted batch %d/%d for '%s'",
                    batch_start // BATCH_SIZE + 1,
                    (len(vectors) + BATCH_SIZE - 1) // BATCH_SIZE,
                    pdf_key,
                )

            total_chunks += len(vectors)

    logger.info(
        "Ingestion complete: %d PDF(s) → %d chunks upserted to Pinecone index '%s'.",
        len(pdf_keys),
        total_chunks,
        index_name,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest policy PDFs from S3 into Pinecone.",
    )
    parser.add_argument(
        "--bucket",
        required=True,
        help="S3 bucket name containing policy PDFs.",
    )
    parser.add_argument(
        "--prefix",
        default="policies/",
        help="S3 key prefix to scan for PDFs (default: 'policies/').",
    )
    parser.add_argument(
        "--policy-tier",
        default=DEFAULT_POLICY_TIER,
        help=f"Policy tier label stored in chunk metadata (default: '{DEFAULT_POLICY_TIER}').",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Text splitter chunk size (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help=f"Text splitter chunk overlap (default: {DEFAULT_CHUNK_OVERLAP}).",
    )
    parser.add_argument(
        "--reset-index",
        action="store_true",
        help="Delete and recreate the Pinecone index before ingesting.",
    )

    args = parser.parse_args()

    run_ingestion(
        bucket=args.bucket,
        prefix=args.prefix,
        policy_tier=args.policy_tier,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        reset_index=args.reset_index,
    )