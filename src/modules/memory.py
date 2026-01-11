import sys
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional

import faiss
import numpy as np
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_CONFIG, EMBEDDING_CONFIG


class EnhancedConversationMemory:
    """
    Enhanced conversation memory with FAISS vector storage for entity indexing.
    Compatible with LangChain 1.x (no deprecated memory classes).
    """
    
    def __init__(
        self,
        token_limit: int = 10000,
        faiss_index_path: str = "faiss_index"
    ):
        """
        Initialize the enhanced conversation memory.
        
        Args:
            token_limit: Maximum tokens before summarization
            faiss_index_path: Path to store FAISS index
        """
        self.token_limit = token_limit
        self.faiss_index_path = Path(faiss_index_path)
        self.faiss_index_path.mkdir(exist_ok=True)
        
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3
        )
        
        self.embeddings = self._init_embeddings()
        self.use_embeddings = self.embeddings is not None
        
        self.messages: List[BaseMessage] = []
        self.summary: str = ""
        self.max_messages_before_summary = 10
        
        self.entity_store: List[Dict[str, Any]] = []
        self.faiss_index: Optional[faiss.Index] = None
        self.embedding_dimension = 384  # all-MiniLM-L6-v2 dimension
        
        self._load_faiss_index()
    
    def _init_embeddings(self):
        """Initialize HuggingFace embeddings."""
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            return HuggingFaceEmbeddings(
                model_name=EMBEDDING_CONFIG["model_name"],
                model_kwargs=EMBEDDING_CONFIG["model_kwargs"],
                encode_kwargs=EMBEDDING_CONFIG["encode_kwargs"]
            )
        except ImportError:
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings as CommunityHFEmbeddings
                return CommunityHFEmbeddings(model_name=EMBEDDING_CONFIG["model_name"])
            except Exception as e:
                print(f"Warning: Failed to initialize embeddings: {e}. Falling back to simple storage.")
        except Exception as e:
            print(f"Warning: Failed to initialize embeddings: {e}. Falling back to simple storage.")
        return None
    
    def _load_faiss_index(self):
        """Load existing FAISS index or create a new one."""
        index_file = self.faiss_index_path / "index.faiss"
        metadata_file = self.faiss_index_path / "metadata.pkl"
        
        try:
            if index_file.exists() and metadata_file.exists():
                self.faiss_index = faiss.read_index(str(index_file))
                with open(metadata_file, 'rb') as f:
                    self.entity_store = pickle.load(f)
                print(f"Loaded FAISS index with {len(self.entity_store)} entities")
            else:
                self.faiss_index = faiss.IndexFlatL2(self.embedding_dimension)
                print("Created new FAISS index")
        except Exception as e:
            print(f"Warning: Failed to load FAISS index: {e}. Creating new index.")
            self.faiss_index = faiss.IndexFlatL2(self.embedding_dimension)
    
    def _save_faiss_index(self):
        """Save FAISS index and metadata to disk."""
        try:
            index_file = self.faiss_index_path / "index.faiss"
            metadata_file = self.faiss_index_path / "metadata.pkl"
            
            faiss.write_index(self.faiss_index, str(index_file))
            with open(metadata_file, 'wb') as f:
                pickle.dump(self.entity_store, f)
        except Exception as e:
            print(f"Warning: Failed to save FAISS index: {e}")
    
    def add_message(self, message: str, role: str = "user") -> None:
        """
        Add a message to the conversation memory.
        
        Args:
            message: The message content
            role: The role ('user' or 'assistant')
        """
        if role == "user":
            self.messages.append(HumanMessage(content=message))
        else:
            self.messages.append(AIMessage(content=message))
        
        if len(self.messages) > self.max_messages_before_summary:
            self._summarize_messages()
    
    def _summarize_messages(self) -> None:
        """Summarize older messages to keep context manageable."""
        try:
            if len(self.messages) <= self.max_messages_before_summary:
                return
            
            messages_to_summarize = self.messages[:-5]
            recent_messages = self.messages[-5:]
            
            conversation_text = "\n".join([
                f"{msg.type}: {msg.content}" 
                for msg in messages_to_summarize
            ])
            
            summary_prompt = ChatPromptTemplate.from_messages([
                ("system", "Summarize the following conversation concisely, preserving key requirements, decisions, and context:"),
                ("human", "{conversation}")
            ])
            
            chain = summary_prompt | self.llm
            result = chain.invoke({"conversation": conversation_text})
            
            if self.summary:
                self.summary = f"{self.summary}\n\nAdditional context: {result.content}"
            else:
                self.summary = result.content
            
            self.messages = recent_messages
            
        except Exception as e:
            print(f"Warning: Failed to summarize messages: {e}")
    
    def get_summary(self) -> str:
        """
        Get a summary of the current conversation.
        
        Returns:
            Summary string of the conversation history
        """
        try:
            parts = []
            
            if self.summary:
                parts.append(f"Previous context: {self.summary}")
            
            if self.messages:
                recent_history = "\n".join([
                    f"{msg.type}: {msg.content}" 
                    for msg in self.messages
                ])
                parts.append(f"Recent conversation:\n{recent_history}")
            
            if parts:
                return "\n\n".join(parts)
            
            return "No conversation history yet."
        except Exception as e:
            print(f"Warning: Failed to get summary: {e}")
            return "No conversation history available."
    
    def store_entity(self, entity_text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store a key entity with vector embedding in FAISS.
        
        Args:
            entity_text: The text content of the entity
            metadata: Additional metadata about the entity
            
        Returns:
            True if successful, False otherwise
        """
        if not self.use_embeddings or self.embeddings is None:
            self.entity_store.append({
                "text": entity_text,
                "metadata": metadata or {},
                "embedding": None
            })
            return True
        
        try:
            embedding = self.embeddings.embed_query(entity_text)
            embedding_array = np.array([embedding], dtype=np.float32)
            
            self.faiss_index.add(embedding_array)
            
            self.entity_store.append({
                "text": entity_text,
                "metadata": metadata or {},
                "embedding": embedding
            })
            
            self._save_faiss_index()
            return True
            
        except Exception as e:
            print(f"Warning: Failed to store entity with embedding: {e}. Using fallback.")
            self.entity_store.append({
                "text": entity_text,
                "metadata": metadata or {},
                "embedding": None
            })
            return False
    
    def retrieve_entities(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve similar entities using FAISS similarity search.
        
        Args:
            query: The search query
            top_k: Number of top results to return
            
        Returns:
            List of entity dictionaries with text and metadata
        """
        if not self.use_embeddings or self.embeddings is None or len(self.entity_store) == 0:
            return self.entity_store[:top_k]
        
        try:
            query_embedding = self.embeddings.embed_query(query)
            query_array = np.array([query_embedding], dtype=np.float32)
            
            k = min(top_k, len(self.entity_store))
            distances, indices = self.faiss_index.search(query_array, k)
            
            results = []
            for idx in indices[0]:
                if 0 <= idx < len(self.entity_store):
                    results.append(self.entity_store[idx])
            
            return results
            
        except Exception as e:
            print(f"Warning: Failed to retrieve entities with FAISS: {e}. Using fallback.")
            return self.entity_store[:top_k]
    
    def clear_memory(self):
        """Clear all conversation memory and entities."""
        self.messages = []
        self.summary = ""
        self.entity_store = []
        self.faiss_index = faiss.IndexFlatL2(self.embedding_dimension)
        self._save_faiss_index()
    
    def get_conversation_context(self) -> str:
        """
        Get formatted conversation context for LLM input.
        
        Returns:
            Formatted conversation context string
        """
        summary = self.get_summary()
        
        if len(self.entity_store) > 0:
            entities_text = "\n\nKey Entities:\n" + "\n".join([
                f"- {entity['text']}" 
                for entity in self.entity_store[-5:]
            ])
            return summary + entities_text
        
        return summary
