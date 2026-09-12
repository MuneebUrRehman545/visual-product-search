import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()


# ==========================================================
# Qdrant Configuration
# ==========================================================

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

if not QDRANT_URL:
    raise ValueError("QDRANT_URL is missing from .env")

if not QDRANT_API_KEY:
    raise ValueError("QDRANT_API_KEY is missing from .env")


# ==========================================================
# Collection Name
# ==========================================================

COLLECTION_NAME = "rag_documents"


# ==========================================================
# Qdrant Client
# ==========================================================

if QDRANT_URL == ":memory:":
    client = QdrantClient(location=":memory:")
    from qdrant_client.http.models import Distance, VectorParams
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
else:
    client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY
    )


# ==========================================================
# Connection Test
# ==========================================================

def test_connection():

    try:
        collections = client.get_collections()

        print("=" * 60)
        print("QDRANT CONNECTION SUCCESSFUL")
        print("=" * 60)

        print("Available collections:")

        for collection in collections.collections:
            print("-", collection.name)

        print("=" * 60)

        return True

    except Exception as e:

        print("=" * 60)
        print("QDRANT CONNECTION ERROR")
        print("=" * 60)

        print(type(e).__name__)
        print(str(e))

        print("=" * 60)

        return False


# ==========================================================
# Get Collection Information
# ==========================================================

def get_collection_info():

    try:

        return client.get_collection(
            collection_name=COLLECTION_NAME
        )

    except Exception as e:

        print(
            f"Could not get collection information: {e}"
        )

        return None


# ==========================================================
# Check Whether Collection Exists
# ==========================================================

def collection_exists():

    try:

        collections = client.get_collections()

        return any(
            collection.name == COLLECTION_NAME
            for collection in collections.collections
        )

    except Exception as e:

        print(
            f"Error checking collection: {e}"
        )

        return False


# ==========================================================
# Delete Entire Knowledge Base
# ==========================================================
#
# IMPORTANT:
# This deletes ALL stored document vectors.
#
# We will use this ONCE to remove the old Faizan,
# resume and other test document vectors.
#
# DO NOT call this automatically during startup.
#
# ==========================================================

def clear_knowledge_base():

    try:

        if collection_exists():

            client.delete_collection(
                collection_name=COLLECTION_NAME
            )

            print("=" * 60)
            print("KNOWLEDGE BASE CLEARED")
            print("=" * 60)

        else:

            print(
                "Knowledge base collection does not exist."
            )

        return True

    except Exception as e:

        print("=" * 60)
        print("FAILED TO CLEAR KNOWLEDGE BASE")
        print("=" * 60)

        print(type(e).__name__)
        print(str(e))

        print("=" * 60)

        return False
