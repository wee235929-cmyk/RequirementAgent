"""
RAG Indexer module with FAISS vector storage and GraphRAG integration.
"""
import sys
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS as FAISSVectorStore

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_CONFIG, EMBEDDING_CONFIG, RAG_CONFIG, RAG_INDEX_DIR
from utils import get_logger
from rag.parser import DocumentParser

logger = get_logger(__name__)


class RAGIndexer:
    """
    RAG Indexer with FAISS vector storage and optional GraphRAG integration.
    """
    
    def __init__(
        self,
        index_path: str = None,
        chunk_size: int = None,
        chunk_overlap: int = None
    ):
        self.index_path = Path(index_path) if index_path else RAG_INDEX_DIR
        self.index_path.mkdir(exist_ok=True)
        
        self.chunk_size = chunk_size or RAG_CONFIG["chunk_size"]
        self.chunk_overlap = chunk_overlap or RAG_CONFIG["chunk_overlap"]
        
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3
        )
        
        self.embeddings = self._init_embeddings()
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        self.parser = DocumentParser()
        self.vectorstore: Optional[FAISSVectorStore] = None
        self.documents: List[Document] = []
        self.indexed_files: Dict[str, Dict[str, Any]] = {}
        
        self.graphrag_available = False
        self.graph_index = None
        
        self._load_index()
    
    def _init_embeddings(self):
        """Initialize embeddings using config settings."""
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_CONFIG["model_name"],
                model_kwargs=EMBEDDING_CONFIG["model_kwargs"],
                encode_kwargs=EMBEDDING_CONFIG["encode_kwargs"]
            )
            logger.info("HuggingFace embeddings initialized successfully")
            return embeddings
        except ImportError:
            logger.warning("langchain-huggingface not installed, trying fallback...")
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings as CommunityHFEmbeddings
                embeddings = CommunityHFEmbeddings(model_name=EMBEDDING_CONFIG["model_name"])
                logger.info("Community HuggingFace embeddings initialized")
                return embeddings
            except Exception as e:
                logger.error(f"Failed to initialize embeddings: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
        return None
    
    def _load_index(self):
        """Load existing FAISS index if available."""
        faiss_path = self.index_path / "faiss_index"
        metadata_path = self.index_path / "metadata.json"
        
        try:
            if faiss_path.exists() and self.embeddings:
                self.vectorstore = FAISSVectorStore.load_local(
                    str(faiss_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info(f"Loaded existing FAISS index from {faiss_path}")
            
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    self.indexed_files = json.load(f)
                logger.info(f"Loaded metadata for {len(self.indexed_files)} indexed files")
        except Exception as e:
            logger.warning(f"Failed to load existing index: {e}")
    
    def _save_index(self):
        """Save FAISS index and metadata to disk."""
        try:
            if self.vectorstore:
                faiss_path = self.index_path / "faiss_index"
                self.vectorstore.save_local(str(faiss_path))
                logger.info(f"Saved FAISS index to {faiss_path}")
            
            metadata_path = self.index_path / "metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(self.indexed_files, f, indent=2, default=str)
            logger.info(f"Saved metadata for {len(self.indexed_files)} files")
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def index_documents(self, file_paths: List[str], progress_callback=None) -> Dict[str, Any]:
        """
        Index multiple documents with incremental updates.
        
        Args:
            file_paths: List of file paths to index
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary with indexing results
        """
        results = {
            "success": [],
            "failed": [],
            "skipped": [],
            "total_chunks": 0
        }
        
        new_documents = []
        
        for i, file_path in enumerate(file_paths):
            file_path = str(file_path)
            filename = Path(file_path).name
            
            if progress_callback:
                progress_callback(f"Processing {filename}... ({i+1}/{len(file_paths)})")
            
            if file_path in self.indexed_files:
                results["skipped"].append(filename)
                logger.info(f"Skipping already indexed file: {filename}")
                continue
            
            try:
                content, metadata = self.parser.parse_document(file_path)
                
                if not content or len(content.strip()) < 10:
                    results["failed"].append({"file": filename, "error": "No content extracted"})
                    continue
                
                chunks = self.text_splitter.split_text(content)
                
                for j, chunk in enumerate(chunks):
                    doc_metadata = {
                        **metadata,
                        "chunk_index": j,
                        "total_chunks": len(chunks)
                    }
                    new_documents.append(Document(page_content=chunk, metadata=doc_metadata))
                
                self.indexed_files[file_path] = {
                    "filename": filename,
                    "chunks": len(chunks),
                    "parser": metadata.get("parser", "unknown"),
                    "tables_count": len(metadata.get("tables", [])),
                    "images_count": len(metadata.get("images", []))
                }
                
                results["success"].append(filename)
                results["total_chunks"] += len(chunks)
                logger.info(f"✓ Indexed {filename}: {len(chunks)} chunks")
                
            except Exception as e:
                results["failed"].append({"file": filename, "error": str(e)})
                logger.error(f"✗ Failed to index {filename}: {e}")
        
        if new_documents:
            if progress_callback:
                progress_callback("Building vector index...")
            
            try:
                if self.vectorstore is None and self.embeddings:
                    self.vectorstore = FAISSVectorStore.from_documents(new_documents, self.embeddings)
                elif self.vectorstore and self.embeddings:
                    new_vectorstore = FAISSVectorStore.from_documents(new_documents, self.embeddings)
                    self.vectorstore.merge_from(new_vectorstore)
                
                self.documents.extend(new_documents)
                self._save_index()
                
                logger.info(f"✓ Vector index updated with {len(new_documents)} new chunks")
            except Exception as e:
                logger.error(f"Failed to build vector index: {e}")
                results["index_error"] = str(e)
        
        return results
    
    def build_graph_index(self, progress_callback=None) -> bool:
        """
        Build GraphRAG knowledge graph from indexed documents.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.documents:
            logger.warning("No documents to build graph from")
            return False
        
        try:
            if progress_callback:
                progress_callback("Initializing GraphRAG...")
            
            logger.info("GraphRAG integration - using simplified entity extraction")
            
            entities = []
            relationships = []
            
            if progress_callback:
                progress_callback("Extracting entities from documents...")
            
            entity_prompt = ChatPromptTemplate.from_messages([
                ("system", """Extract key entities (people, organizations, concepts, technologies, requirements) from the following text.
Return as JSON: {{"entities": ["entity1", "entity2", ...], "relationships": [["entity1", "relates_to", "entity2"], ...]}}"""),
                ("human", "{text}")
            ])
            
            chain = entity_prompt | self.llm
            
            sample_docs = self.documents[:min(10, len(self.documents))]
            
            for doc in sample_docs:
                try:
                    result = chain.invoke({"text": doc.page_content[:2000]})
                    content = result.content
                    
                    if "{" in content and "}" in content:
                        json_str = content[content.find("{"):content.rfind("}")+1]
                        data = json.loads(json_str)
                        entities.extend(data.get("entities", []))
                        relationships.extend(data.get("relationships", []))
                except Exception as e:
                    logger.warning(f"Entity extraction failed for chunk: {e}")
            
            self.graph_index = {
                "entities": list(set(entities)),
                "relationships": relationships,
                "document_count": len(self.documents)
            }
            
            graph_path = self.index_path / "graph_index.json"
            with open(graph_path, 'w') as f:
                json.dump(self.graph_index, f, indent=2)
            
            self.graphrag_available = True
            logger.info(f"✓ Graph index built: {len(entities)} entities, {len(relationships)} relationships")
            
            if progress_callback:
                progress_callback(f"Graph built: {len(set(entities))} entities")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to build graph index: {e}")
            self.graphrag_available = False
            return False
    
    def get_retriever(self, k: int = 5):
        """Get FAISS retriever."""
        if self.vectorstore:
            return self.vectorstore.as_retriever(search_kwargs={"k": k})
        return None
    
    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """Perform similarity search on the vector store."""
        if self.vectorstore:
            return self.vectorstore.similarity_search(query, k=k)
        return []
    
    def graph_search(self, query: str) -> Dict[str, Any]:
        """Search the knowledge graph for relevant entities and relationships."""
        if not self.graph_index:
            return {"entities": [], "relationships": [], "context": ""}
        
        query_lower = query.lower()
        relevant_entities = [
            e for e in self.graph_index.get("entities", [])
            if any(word in e.lower() for word in query_lower.split())
        ]
        
        relevant_relationships = [
            r for r in self.graph_index.get("relationships", [])
            if any(e.lower() in [r[0].lower(), r[2].lower()] for e in relevant_entities)
        ]
        
        context_parts = []
        if relevant_entities:
            context_parts.append(f"Related entities: {', '.join(relevant_entities[:10])}")
        if relevant_relationships:
            rel_strs = [f"{r[0]} {r[1]} {r[2]}" for r in relevant_relationships[:5]]
            context_parts.append(f"Relationships: {'; '.join(rel_strs)}")
        
        return {
            "entities": relevant_entities[:10],
            "relationships": relevant_relationships[:10],
            "context": "\n".join(context_parts)
        }
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the current index."""
        return {
            "indexed_files": len(self.indexed_files),
            "total_chunks": len(self.documents),
            "has_vectorstore": self.vectorstore is not None,
            "has_graph": self.graphrag_available,
            "files": list(self.indexed_files.keys())
        }
    
    def clear_index(self):
        """Clear all indexed data."""
        self.vectorstore = None
        self.documents = []
        self.indexed_files = {}
        self.graph_index = None
        self.graphrag_available = False
        
        if self.index_path.exists():
            shutil.rmtree(self.index_path)
            self.index_path.mkdir(exist_ok=True)
        
        logger.info("Index cleared")
