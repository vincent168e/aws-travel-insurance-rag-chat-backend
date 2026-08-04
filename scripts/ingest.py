import sys
import urllib.request
from pathlib import Path
from pinecone import Pinecone, ServerlessSpec

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.config import settings
from src.database.pinecone_client import embeddings

PDF_URL = "https://qc.bluecross.ca/en/dam/jcr:7db443db-b794-4de0-aa1f-a849a941d89f/travel_insurance_policy_11QVV0196A_2022-10.pdf"
LOCAL_PDF_PATH = "public/blue_cross_policy.pdf"
POLICY_TIER = "Single-trip solutions Canada package"

def run_ingestion():
    # 1. Initialize Pinecone Index if it doesn't exist
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    
    if settings.PINECONE_INDEX_NAME not in pc.list_indexes().names():
        print(f"Creating Pinecone index: {settings.PINECONE_INDEX_NAME}...")
        pc.create_index(
            name=settings.PINECONE_INDEX_NAME,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )

    index = pc.Index(settings.PINECONE_INDEX_NAME)

    # 2. Download and Load PDF
    print("Downloading Blue Cross Policy PDF...")
    urllib.request.urlretrieve(PDF_URL, LOCAL_PDF_PATH)
    
    loader = PyPDFLoader(LOCAL_PDF_PATH)
    documents = loader.load()
    
    # 3. Chunking Document
    print("Chunking documents...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(documents)
    
    # 4. Generate Embeddings & Push to Pinecone
    print(f"Embedding and uploading {len(chunks)} fragments to Pinecone...")
    for i, chunk in enumerate(chunks):
        vector = embeddings.embed_query(chunk.page_content)
        metadata = {
            "text": chunk.page_content,
            "page": chunk.metadata.get("page", 0),
            "policy_tier": POLICY_TIER,
        }
        index.upsert(vectors=[(f"doc_chunk_{i}", vector, metadata)])
        
    print("Ingestion sequence finalized successfully!")

if __name__ == "__main__":
    run_ingestion()