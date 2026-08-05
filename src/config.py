import os

# Only load .env for local development — in AWS ECS, env vars are injected
# by the task definition via Secrets Manager and environment overrides.
if os.getenv("ENV", "local") == "local":
    from dotenv import load_dotenv
    load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "blue-cross-travel")

    # AWS S3 (replaces Cloudinary)
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    S3_CLAIM_BUCKET: str = os.getenv("S3_CLAIM_BUCKET", "")

    # DynamoDB (replaces in-memory MemorySaver)
    DYNAMODB_TABLE: str = os.getenv("DYNAMODB_TABLE", "")

    # Frontend client URLs for CORS
    LOCAL_FRONTEND_CLIENT_URL: str = os.getenv("LOCAL_FRONTEND_CLIENT_URL", "http://localhost:3000")
    EXTERNAL_FRONTEND_CLIENT_URL: str = os.getenv("EXTERNAL_FRONTEND_CLIENT_URL", "")


settings = Settings()