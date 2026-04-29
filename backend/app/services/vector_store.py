import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class VectorStoreService:
    """ChromaDB vector store service for RAG. Falls back to in-memory if ChromaDB unavailable."""

    def __init__(self):
        self.client = None
        self.content_collection = None
        self.syllabi_collection = None
        self._initialized = False
        self._use_memory = False
        self._memory_store: Dict[str, List[Dict]] = {"content_items": [], "syllabi": []}

    def initialize(self):
        try:
            import chromadb
            from app.config import settings
            self.client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT
            )
            self.content_collection = self.client.get_or_create_collection(
                name="content_items",
                metadata={"hnsw:space": "cosine"}
            )
            self.syllabi_collection = self.client.get_or_create_collection(
                name="syllabi",
                metadata={"hnsw:space": "cosine"}
            )
            self._initialized = True
            logger.info("ChromaDB vector store initialized successfully")
        except Exception as e:
            logger.warning(f"ChromaDB not available, using in-memory fallback: {e}")
            self._use_memory = True
            self._initialized = True

    def upsert_content(self, doc_id: str, text: str, metadata: Dict):
        if not self._initialized:
            self.initialize()

        if self._use_memory:
            self._memory_store["content_items"] = [
                d for d in self._memory_store["content_items"] if d["id"] != doc_id
            ]
            self._memory_store["content_items"].append({
                "id": doc_id, "text": text, "metadata": metadata
            })
            return

        try:
            self.content_collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata]
            )
        except Exception as e:
            logger.error(f"Failed to upsert content: {e}")
            self._memory_store["content_items"].append({
                "id": doc_id, "text": text, "metadata": metadata
            })

    def upsert_syllabus(self, doc_id: str, text: str, metadata: Dict):
        if not self._initialized:
            self.initialize()

        if self._use_memory:
            self._memory_store["syllabi"] = [
                d for d in self._memory_store["syllabi"] if d["id"] != doc_id
            ]
            self._memory_store["syllabi"].append({
                "id": doc_id, "text": text, "metadata": metadata
            })
            return

        try:
            self.syllabi_collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata]
            )
        except Exception as e:
            logger.error(f"Failed to upsert syllabus: {e}")

    def search(self, query: str, collection: str = "content_items",
               where: Optional[Dict] = None, n_results: int = 3) -> List[Dict]:
        if not self._initialized:
            self.initialize()

        if self._use_memory:
            return self._memory_search(query, collection, where, n_results)

        try:
            col = self.content_collection if collection == "content_items" else self.syllabi_collection
            params = {"query_texts": [query], "n_results": n_results}
            if where:
                params["where"] = where

            results = col.query(**params)

            docs = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    docs.append({
                        "id": results["ids"][0][i] if results.get("ids") else "",
                        "text": doc[:500],  # truncate to 500 chars
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "distance": results["distances"][0][i] if results.get("distances") else 0
                    })
            return docs
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return self._memory_search(query, collection, where, n_results)

    def _memory_search(self, query: str, collection: str,
                       where: Optional[Dict] = None, n_results: int = 3) -> List[Dict]:
        """Simple keyword-based fallback search."""
        store = self._memory_store.get(collection, [])
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for doc in store:
            if where:
                match = all(doc.get("metadata", {}).get(k) == v for k, v in where.items())
                if not match:
                    continue

            text_lower = doc["text"].lower()
            score = sum(1 for w in query_words if w in text_lower)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"id": d["id"], "text": d["text"][:500], "metadata": d.get("metadata", {}), "distance": 0}
            for _, d in scored[:n_results]
        ]


vector_store_service = VectorStoreService()
