import logging
from pinecone import Pinecone
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.config import settings

logger = logging.getLogger(__name__)


# Initialize components
pc = Pinecone(api_key=settings.PINECONE_API_KEY)
index = pc.Index(settings.PINECONE_INDEX_NAME)

embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    output_dimensionality=1536,
    google_api_key=settings.GEMINI_API_KEY
)

def query_policy_chunks(query: str, top_k: int = 5, policy_tier: str | None = None):
    """Query Pinecone and return matched snippets with metadata for citations and auditing."""
    query_vector = embeddings.embed_query(query)

    query_kwargs = {
        "vector": query_vector,
        "top_k": top_k,
        "include_metadata": True,
    }
    # if policy_tier:
    #     query_kwargs["filter"] = {"policy_tier": {"$eq": policy_tier}}

    response = index.query(**query_kwargs)

    logger.info("=" * 40)
    logger.info("RAW PINECONE MATCHES FOR QUERY: '%s'", query)
    if response.matches:
        for i, match in enumerate(response.matches):
            logger.info("  Match [%s]:", i + 1)
            logger.info("    ID: %s", match.id)
            logger.info("    Similarity Score: %.4f", match.score)

            text_preview = match.metadata.get('text', '')[:150].replace('\n', ' ')
            logger.info("    Metadata Text Preview: %s...", text_preview)
    else:
        logger.info("  No matches found in Pinecone.")
    logger.info("=" * 40)

    chunks = []
    if response.matches:
        for match in response.matches:
            metadata = match.metadata or {}
            chunks.append(
                {
                    "id": match.id,
                    "score": float(match.score),
                    "text": metadata.get("text", ""),
                    # "page": metadata.get("page"),
                    # "section": metadata.get("section"),
                    # "policy_tier": metadata.get("policy_tier"),
                }
            )

    return chunks


def query_vector_db(query: str, top_k: int = 3):
    """Legacy helper used by older flows: returns texts and max score."""
    chunks = query_policy_chunks(query=query, top_k=top_k)
    docs = [chunk.get("text", "") for chunk in chunks]
    max_score = chunks[0]["score"] if chunks else 0.0
    return docs, max_score