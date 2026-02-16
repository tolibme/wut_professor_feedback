"""
Embedding service for WUT Feedback Bot.

Handles vector embeddings using ChromaDB and sentence-transformers
for semantic search and similarity matching.
"""

import hashlib
import logging
from typing import List, Dict, Any, Optional

import chromadb
# from chromadb.config import Settings  # Deprecated in newer versions
from sentence_transformers import SentenceTransformer

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """
    Service for vector embeddings and semantic search.
    
    Uses:
    - sentence-transformers for embedding generation
    - ChromaDB for vector storage and retrieval
    """
    
    # Collection name for feedbacks
    FEEDBACK_COLLECTION = "professor_feedbacks"
    
    def __init__(self, persist_dir: str = None):
        """
        Initialize embedding service.
        
        Args:
            persist_dir: Directory for ChromaDB persistence
        """
        self.persist_dir = persist_dir or Config.CHROMA_PERSIST_DIR
        
        # Silence noisy telemetry logger from ChromaDB
        logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

        # Initialize sentence transformer
        # Using multilingual model for RU/UZ/EN support
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        
        # Initialize ChromaDB client
        # Use PersistentClient for newer ChromaDB versions
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.FEEDBACK_COLLECTION,
            metadata={"description": "Professor feedback embeddings"}
        )
        
        logger.info(f"Embedding service initialized with {self.collection.count()} embeddings")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.
        
        Args:
            text: Text to embed
        
        Returns:
            List of floats representing the embedding
        """
        if not text:
            return []
        
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [e.tolist() for e in embeddings]
    
    def store_feedback_embedding(
        self,
        feedback_id: int,
        text: str,
        professor_id: int,
        professor_name: str,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """
        Store a feedback embedding in ChromaDB.
        
        Args:
            feedback_id: Database feedback ID
            text: Feedback text
            professor_id: Professor ID
            professor_name: Professor name
            metadata: Additional metadata
        """
        embedding = self.generate_embedding(text)
        if not embedding:
            logger.warning(f"Empty embedding for feedback {feedback_id}")
            return
        
        doc_id = f"feedback_{feedback_id}"
        
        # Prepare metadata
        doc_metadata = {
            "feedback_id": feedback_id,
            "professor_id": professor_id,
            "professor_name": professor_name,
            "text_hash": self._hash_text(text),
        }
        if metadata:
            doc_metadata.update(metadata)
        # ChromaDB metadata values must be non-None primitives
        doc_metadata = {
            key: value for key, value in doc_metadata.items()
            if value is not None
        }
        
        # Upsert to collection
        self.collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[doc_metadata],
        )
        
        logger.debug(f"Stored embedding for feedback {feedback_id}")
    
    def store_feedback_embeddings_batch(
        self,
        feedbacks: List[Dict[str, Any]],
    ) -> int:
        """
        Store multiple feedback embeddings efficiently.
        
        Args:
            feedbacks: List of feedback dicts with:
                - id: feedback ID
                - text: feedback text
                - professor_id: professor ID
                - professor_name: professor name
        
        Returns:
            Number of embeddings stored
        """
        if not feedbacks:
            return 0
        
        texts = [f['text'] for f in feedbacks]
        embeddings = self.generate_embeddings_batch(texts)
        
        ids = []
        metadatas = []
        documents = []
        valid_embeddings = []
        
        for feedback, embedding in zip(feedbacks, embeddings):
            if not embedding:
                continue
            
            ids.append(f"feedback_{feedback['id']}")
            documents.append(feedback['text'])
            valid_embeddings.append(embedding)
            metadatas.append({
                "feedback_id": feedback['id'],
                "professor_id": feedback['professor_id'],
                "professor_name": feedback['professor_name'],
                "text_hash": self._hash_text(feedback['text']),
            })
            metadatas[-1] = {
                key: value for key, value in metadatas[-1].items()
                if value is not None
            }
        
        if ids:
            self.collection.upsert(
                ids=ids,
                embeddings=valid_embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            logger.info(f"Stored {len(ids)} embeddings in batch")
        
        return len(ids)
    
    def search_similar_feedbacks(
        self,
        query: str,
        n_results: int = 10,
        professor_id: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for feedbacks similar to query.
        
        Args:
            query: Search query text
            n_results: Maximum results to return
            professor_id: Optional filter by professor
        
        Returns:
            List of matching feedbacks with scores
        """
        query_embedding = self.generate_embedding(query)
        if not query_embedding:
            return []
        
        # Build where clause
        where = None
        if professor_id:
            where = {"professor_id": professor_id}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        
        # Format results
        formatted = []
        if results['ids'] and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                formatted.append({
                    "id": doc_id,
                    "text": results['documents'][0][i] if results['documents'] else None,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results['distances'] else None,
                    "similarity": 1 - (results['distances'][0][i] if results['distances'] else 0),
                })
        
        return formatted
    
    def search_by_professor(
        self,
        professor_name: str,
        n_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search for feedbacks about a specific professor.
        
        Args:
            professor_name: Professor name to search
            n_results: Maximum results
        
        Returns:
            List of relevant feedbacks
        """
        # Use professor name as query for semantic match
        return self.search_similar_feedbacks(
            query=f"feedback about professor {professor_name}",
            n_results=n_results,
        )
    
    def get_feedback_by_id(self, feedback_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific feedback embedding by ID.
        
        Args:
            feedback_id: Feedback ID
        
        Returns:
            Feedback data or None
        """
        doc_id = f"feedback_{feedback_id}"
        
        try:
            result = self.collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"],
            )
            
            if result['ids']:
                return {
                    "id": result['ids'][0],
                    "text": result['documents'][0] if result['documents'] else None,
                    "metadata": result['metadatas'][0] if result['metadatas'] else {},
                }
        except Exception as e:
            logger.warning(f"Error getting feedback {feedback_id}: {e}")
        
        return None
    
    def delete_feedback_embedding(self, feedback_id: int) -> bool:
        """
        Delete a feedback embedding.
        
        Args:
            feedback_id: Feedback ID to delete
        
        Returns:
            True if deleted successfully
        """
        doc_id = f"feedback_{feedback_id}"
        
        try:
            self.collection.delete(ids=[doc_id])
            logger.debug(f"Deleted embedding for feedback {feedback_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting embedding {feedback_id}: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the embedding collection."""
        return {
            "total_embeddings": self.collection.count(),
            "collection_name": self.FEEDBACK_COLLECTION,
            "persist_directory": self.persist_dir,
        }
    
    def persist(self) -> None:
        """
        Persist database to disk.
        NOTE: PersistentClient handles this automatically, but keeping method for compatibility.
        """
        # self.client.persist()  # No longer needed/available in PersistentClient
        logger.info("Embedding database persisted (auto-handled)")
    
    @staticmethod
    def _hash_text(text: str) -> str:
        """Generate hash of text for deduplication."""
        return hashlib.md5(text.encode()).hexdigest()


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(persist_dir: str = None) -> EmbeddingService:
    """Get or create embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(persist_dir)
    return _embedding_service
