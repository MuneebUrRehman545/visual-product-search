from sentence_transformers import SentenceTransformer

# ==========================================================
# Lazy Model Loading
#
# The model is NOT loaded at import time. Loading it eagerly
# (as soon as this module is imported) blocks app startup for
# 30s-3min depending on the server's resources/network, which
# causes deployment platforms' health checks to time out and
# mark the app as "unhealthy" even though it would eventually
# start fine.
#
# Instead, the model loads on first actual use (first upload
# or chat request). The app starts instantly and passes health
# checks immediately; only the very first request pays the
# model-loading cost.
# ==========================================================

_model = None


def get_model():
    global _model

    if _model is None:
        print("Loading embedding model (first use)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("Embedding model loaded.")

    return _model


def generate_embeddings(chunks):
    model = get_model()
    embeddings = model.encode(chunks)
    return embeddings
