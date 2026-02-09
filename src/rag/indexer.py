"""
RAG Indexer - 文档索引器

提供文档的解析、分块、向量化和索引功能。

主要功能：
    - 文档解析：支持 PDF、Word、Markdown、TXT 等格式
    - 文本分块：使用递归字符分割器进行智能分块
    - 向量索引：使用 FAISS 进行高效的向量存储和检索
    - 图索引：可选的 Neo4j 图存储，用于实体关系检索
    - 文件去重：基于文件名+大小的去重机制
    - 持久化：支持索引的保存和加载

配置项（来自 RAG_CONFIG）：
    - chunk_size: 分块大小（默认 1000）
    - chunk_overlap: 分块重叠（默认 200）
    - top_k: 检索返回数量（默认 5）
"""
import sys
import re
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS as FAISSVectorStore

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LLM_CONFIG, EMBEDDING_CONFIG, RAG_CONFIG, RAG_INDEX_DIR, NEO4J_CONFIG
from utils import get_logger
from rag.parser import DocumentParser
from rag.neo4j_store import Neo4jGraphStore, create_neo4j_store

logger = get_logger(__name__)


class RAGIndexer:
    """
    RAG Indexer with FAISS vector storage and optional GraphRAG integration.
    Supports file deduplication by filename+size and JSON import/export.
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
        self._graph_doc_count = 0
        
        # Neo4j graph store (optional, enabled via config)
        self.neo4j_store: Neo4jGraphStore = None
        self.use_neo4j = NEO4J_CONFIG.get("enabled", False)
        
        if self.use_neo4j:
            self._init_neo4j()
        
        self._load_index()
    
    def _init_neo4j(self):
        """Initialize Neo4j graph store if enabled."""
        try:
            self.neo4j_store = create_neo4j_store()
            if self.neo4j_store and self.neo4j_store.connected:
                logger.info("Neo4j graph store initialized successfully")
                self.graphrag_available = True
            else:
                logger.warning("Neo4j enabled but connection failed, falling back to JSON storage")
                self.use_neo4j = False
        except Exception as e:
            logger.warning(f"Failed to initialize Neo4j: {e}, falling back to JSON storage")
            self.use_neo4j = False
    
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
        documents_path = self.index_path / "documents.json"
        
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
            
            if documents_path.exists():
                with open(documents_path, 'r', encoding='utf-8') as f:
                    docs_data = json.load(f)
                self.documents = [
                    Document(page_content=d["content"], metadata=d["metadata"])
                    for d in docs_data
                ]
                logger.info(f"Loaded {len(self.documents)} document chunks for keyword search")
            
            # Load graph index - prefer Neo4j if enabled, otherwise use JSON
            if self.use_neo4j and self.neo4j_store and self.neo4j_store.connected:
                # Load graph stats from Neo4j
                neo4j_stats = self.neo4j_store.get_stats()
                if neo4j_stats.get("entity_count", 0) > 0:
                    self.graphrag_available = True
                    self._graph_doc_count = neo4j_stats.get("entity_count", 0)
                    # Keep graph_index as cache for compatibility
                    self.graph_index = self.neo4j_store.export_to_dict()
                    logger.info(f"Loaded graph from Neo4j: {neo4j_stats.get('entity_count', 0)} entities, {neo4j_stats.get('relationship_count', 0)} relationships")
            else:
                # Fallback to JSON file
                graph_path = self.index_path / "graph_index.json"
                if graph_path.exists():
                    with open(graph_path, 'r') as f:
                        self.graph_index = json.load(f)
                    self.graphrag_available = True
                    self._graph_doc_count = self.graph_index.get("document_count", 0)
                    logger.info(f"Loaded graph index from JSON with {len(self.graph_index.get('entities', []))} entities")
        except Exception as e:
            logger.warning(f"Failed to load existing index: {e}")
    
    def _save_index(self):
        """Save FAISS index, metadata, and documents to disk."""
        try:
            if self.vectorstore:
                faiss_path = self.index_path / "faiss_index"
                self.vectorstore.save_local(str(faiss_path))
                logger.info(f"Saved FAISS index to {faiss_path}")
            
            metadata_path = self.index_path / "metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(self.indexed_files, f, indent=2, default=str)
            logger.info(f"Saved metadata for {len(self.indexed_files)} files")
            
            if self.documents:
                documents_path = self.index_path / "documents.json"
                docs_data = [
                    {"content": doc.page_content, "metadata": doc.metadata}
                    for doc in self.documents
                ]
                with open(documents_path, 'w', encoding='utf-8') as f:
                    json.dump(docs_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved {len(self.documents)} document chunks")
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def _get_file_key(self, filename: str, file_size: int) -> str:
        """Generate a unique key for file deduplication based on filename and size."""
        return f"{filename}::{file_size}"
    
    def _is_file_indexed(self, filename: str, file_size: int) -> bool:
        """Check if a file with the same name and size is already indexed."""
        file_key = self._get_file_key(filename, file_size)
        for path, meta in self.indexed_files.items():
            existing_key = self._get_file_key(meta.get("filename", ""), meta.get("file_size", 0))
            if existing_key == file_key:
                return True
        return False
    
    def index_documents(self, file_paths: List[str], progress_callback=None) -> Dict[str, Any]:
        """
        Index multiple documents with incremental updates.
        Deduplicates files by filename + file size.
        
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
            path_obj = Path(file_path)
            filename = path_obj.name
            
            if progress_callback:
                progress_callback(f"Processing {filename}... ({i+1}/{len(file_paths)})")
            
            try:
                file_size = path_obj.stat().st_size
            except Exception:
                file_size = 0
            
            if self._is_file_indexed(filename, file_size):
                results["skipped"].append(filename)
                logger.info(f"Skipping duplicate file (same name+size): {filename}")
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
                    "file_size": file_size,
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
    
    def build_graph_index(self, progress_callback=None, force_rebuild: bool = False) -> bool:
        """
        Build or update GraphRAG knowledge graph from indexed documents.
        Supports incremental updates when new documents are added.
        Uses Neo4j if enabled, otherwise falls back to JSON file storage.
        
        Args:
            progress_callback: Optional callback for progress updates
            force_rebuild: If True, rebuild from scratch; otherwise, only process new docs
            
        Returns:
            True if successful, False otherwise
        """
        if not self.documents:
            logger.warning("No documents to build graph from")
            return False
        
        try:
            if progress_callback:
                progress_callback("Initializing GraphRAG...")
            
            # Determine storage backend
            storage_type = "Neo4j" if self.use_neo4j and self.neo4j_store else "JSON"
            logger.info(f"GraphRAG integration - using {storage_type} storage")
            
            # Handle force rebuild
            if force_rebuild:
                if self.use_neo4j and self.neo4j_store:
                    self.neo4j_store.clear_graph()
                entities = []
                relationships = []
                start_idx = 0
                self.graph_index = None
            else:
                if self.graph_index:
                    entities = list(self.graph_index.get("entities", []))
                    relationships = list(self.graph_index.get("relationships", []))
                    start_idx = self._graph_doc_count
                else:
                    entities = []
                    relationships = []
                    start_idx = 0
            
            if start_idx >= len(self.documents):
                logger.info("Graph is already up to date with all documents")
                return True
            
            new_docs = self.documents[start_idx:]
            logger.info(f"Processing {len(new_docs)} new documents for graph (starting from index {start_idx})")
            
            if progress_callback:
                progress_callback(f"Extracting entities from {len(new_docs)} new documents...")
            
            entity_prompt = ChatPromptTemplate.from_messages([
                ("system", """Extract all  entities (people, organizations, concepts, technologies, requirements,Table Number,etc) from the following text. Do not lose any entity.
Return as JSON: {{"entities": ["entity1", "entity2", ...], "relationships": [["entity1", "relates_to", "entity2"], ...]}}"""),
                ("human", "{text}")
            ])
            
            chain = entity_prompt | self.llm
            
            sample_docs = new_docs[:min(20, len(new_docs))]
            
            # Collect new entities and relationships from this batch
            new_entities = []
            new_relationships = []
            
            for i, doc in enumerate(sample_docs):
                try:
                    if progress_callback and i % 5 == 0:
                        progress_callback(f"Processing document {i+1}/{len(sample_docs)}...")
                    
                    result = chain.invoke({"text": doc.page_content[:2000]})
                    content = result.content
                    
                    if "{" in content and "}" in content:
                        json_str = content[content.find("{"):content.rfind("}")+1]
                        data = json.loads(json_str)
                        extracted_entities = data.get("entities", [])
                        extracted_relationships = data.get("relationships", [])
                        
                        new_entities.extend(extracted_entities)
                        new_relationships.extend(extracted_relationships)
                        
                        # If using Neo4j, add to database immediately
                        if self.use_neo4j and self.neo4j_store:
                            source_doc = doc.metadata.get("filename", "unknown")
                            self.neo4j_store.add_entities(extracted_entities, source_doc)
                            self.neo4j_store.add_relationships(extracted_relationships, source_doc)
                            
                except Exception as e:
                    logger.warning(f"Entity extraction failed for chunk: {e}")
            
            # Merge with existing entities/relationships
            entities.extend(new_entities)
            relationships.extend(new_relationships)
            
            # Update local graph_index cache
            self.graph_index = {
                "entities": list(set(entities)),
                "relationships": relationships,
                "document_count": len(self.documents)
            }
            self._graph_doc_count = len(self.documents)
            
            # Only save to JSON file if NOT using Neo4j (Neo4j is the primary storage)
            if not (self.use_neo4j and self.neo4j_store and self.neo4j_store.connected):
                graph_path = self.index_path / "graph_index.json"
                with open(graph_path, 'w') as f:
                    json.dump(self.graph_index, f, indent=2)
            
            self.graphrag_available = True
            
            unique_entities = len(set(entities))
            logger.info(f"✓ Graph index updated ({storage_type}): {unique_entities} entities, {len(relationships)} relationships")
            
            if progress_callback:
                progress_callback(f"Graph updated: {unique_entities} entities")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to build graph index: {e}")
            self.graphrag_available = False
            return False
    
    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """Perform similarity search on the vector store."""
        if self.vectorstore:
            return self.vectorstore.similarity_search(query, k=k)
        return []
    
    def graph_search(self, query: str) -> Dict[str, Any]:
        """
        Search the knowledge graph for relevant entities and relationships.
        Uses Neo4j if enabled, otherwise falls back to JSON-based search.
        """
        # Use Neo4j if available and connected
        if self.use_neo4j and self.neo4j_store and self.neo4j_store.connected:
            return self.neo4j_store.graph_search(query)
        
        # Fallback to JSON-based search
        if not self.graph_index:
            return {"entities": [], "relationships": [], "context": "", "found": False}
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        id_pattern = re.compile(r'[A-Z]{2,}-\d+', re.IGNORECASE)
        query_ids = set(id_pattern.findall(query))
        
        relevant_entities: Set[str] = set()
        
        for entity in self.graph_index.get("entities", []):
            entity_lower = entity.lower()
            
            entity_ids = set(id_pattern.findall(entity))
            if query_ids and entity_ids:
                if any(qid.upper() == eid.upper() for qid in query_ids for eid in entity_ids):
                    relevant_entities.add(entity)
                    continue
            
            if any(word in entity_lower for word in query_words if len(word) > 2):
                relevant_entities.add(entity)
                continue
            
            if any(word in query_lower for word in entity_lower.split() if len(word) > 2):
                relevant_entities.add(entity)
        
        relevant_relationships = [
            r for r in self.graph_index.get("relationships", [])
            if any(e.lower() in [r[0].lower(), r[2].lower()] for e in relevant_entities)
        ]
        
        context_parts = []
        if relevant_entities:
            context_parts.append(f"Related entities: {', '.join(list(relevant_entities)[:15])}")
        if relevant_relationships:
            rel_strs = [f"{r[0]} {r[1]} {r[2]}" for r in relevant_relationships[:10]]
            context_parts.append(f"Relationships: {'; '.join(rel_strs)}")
        
        return {
            "entities": list(relevant_entities)[:15],
            "relationships": relevant_relationships[:15],
            "context": "\n".join(context_parts),
            "found": len(relevant_entities) > 0
        }
    
    def keyword_search(self, query: str, k: int = 5) -> List[Document]:
        """
        Perform keyword-based search on documents for exact matches.
        Useful for finding specific IDs, codes, or terms that may not match semantically.
        """
        if not self.documents:
            return []
        
        query_lower = query.lower()
        id_pattern = re.compile(r'[A-Z]{2,}-\d+', re.IGNORECASE)
        query_ids = [qid.upper() for qid in id_pattern.findall(query)]
        
        scored_docs = []
        for doc in self.documents:
            content_lower = doc.page_content.lower()
            score = 0
            
            if query_ids:
                doc_ids = [did.upper() for did in id_pattern.findall(doc.page_content)]
                for qid in query_ids:
                    if qid in doc_ids:
                        score += 10
            
            for word in query_lower.split():
                if len(word) > 2 and word in content_lower:
                    score += 1
            
            if score > 0:
                scored_docs.append((score, doc))
        
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored_docs[:k]]
    
    def hybrid_search(self, query: str, k: int = 5, use_graph: bool = True) -> Dict[str, Any]:
        """
        Perform search with graph-first strategy:
        1. If graph is available and use_graph=True, search graph first
        2. Always perform similarity + keyword search for document retrieval
        3. Graph provides additional context but doesn't replace document search
        
        Args:
            query: Search query
            k: Number of results per search type
            use_graph: Whether to include graph search
            
        Returns:
            Dictionary with combined results and context
        """
        result = {
            "documents": [],
            "graph_context": "",
            "graph_entities": [],
            "search_methods_used": []
        }
        
        if use_graph and self.graphrag_available:
            graph_result = self.graph_search(query)
            result["graph_context"] = graph_result.get("context", "")
            result["graph_entities"] = graph_result.get("entities", [])
            if graph_result.get("found"):
                result["search_methods_used"].append("graph_search")
        
        seen_content = set()
        combined_docs = []
        
        if self.vectorstore:
            vector_docs = self.similarity_search(query, k=k)
            for doc in vector_docs:
                content_hash = hash(doc.page_content[:200])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    combined_docs.append((doc, "vector"))
            if vector_docs:
                result["search_methods_used"].append("vector_similarity")
        
        keyword_docs = self.keyword_search(query, k=k)
        for doc in keyword_docs:
            content_hash = hash(doc.page_content[:200])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                combined_docs.append((doc, "keyword"))
        if keyword_docs:
            result["search_methods_used"].append("keyword_match")
        
        result["documents"] = [doc for doc, _ in combined_docs[:k * 2]]
        
        logger.info(f"Hybrid search: {len(result['documents'])} docs via {result['search_methods_used']}")
        return result
    
    def graph_first_search(self, query: str, k: int = 5) -> Dict[str, Any]:
        """
        Graph-first search strategy:
        1. Search graph for entities and relationships
        2. If graph finds relevant entities, use them to enhance similarity search
        3. If graph finds nothing, fall back to pure similarity + keyword search
        
        This ensures table content is always retrievable while graph provides context.
        
        Args:
            query: Search query
            k: Number of results
            
        Returns:
            Dictionary with documents and graph context
        """
        result = {
            "documents": [],
            "graph_context": "",
            "graph_entities": [],
            "search_methods_used": [],
            "graph_enhanced": False
        }
        
        if self.graphrag_available:
            graph_result = self.graph_search(query)
            result["graph_context"] = graph_result.get("context", "")
            result["graph_entities"] = graph_result.get("entities", [])
            if graph_result.get("found"):
                result["search_methods_used"].append("graph_search")
                result["graph_enhanced"] = True
        
        seen_content = set()
        combined_docs = []
        
        if self.vectorstore:
            vector_docs = self.similarity_search(query, k=k)
            for doc in vector_docs:
                content_hash = hash(doc.page_content[:200])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    combined_docs.append((doc, "vector"))
            if vector_docs:
                result["search_methods_used"].append("vector_similarity")
        
        keyword_docs = self.keyword_search(query, k=k)
        for doc in keyword_docs:
            content_hash = hash(doc.page_content[:200])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                combined_docs.append((doc, "keyword"))
        if keyword_docs:
            result["search_methods_used"].append("keyword_match")
        
        result["documents"] = [doc for doc, _ in combined_docs[:k * 2]]
        
        logger.info(f"Graph-first search: {len(result['documents'])} docs, graph_enhanced={result['graph_enhanced']}, methods={result['search_methods_used']}")
        return result
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the current index."""
        stats = {
            "indexed_files": len(self.indexed_files),
            "total_chunks": len(self.documents),
            "has_vectorstore": self.vectorstore is not None,
            "has_graph": self.graphrag_available,
            "files": list(self.indexed_files.keys()),
            "graph_storage": "neo4j" if self.use_neo4j and self.neo4j_store else "json"
        }
        
        # Add Neo4j-specific stats if available
        if self.use_neo4j and self.neo4j_store and self.neo4j_store.connected:
            neo4j_stats = self.neo4j_store.get_stats()
            stats["neo4j_connected"] = True
            stats["neo4j_entity_count"] = neo4j_stats.get("entity_count", 0)
            stats["neo4j_relationship_count"] = neo4j_stats.get("relationship_count", 0)
        else:
            stats["neo4j_connected"] = False
        
        return stats
    
    def clear_index(self):
        """Clear all indexed data including Neo4j graph if enabled."""
        self.vectorstore = None
        self.documents = []
        self.indexed_files = {}
        self.graph_index = None
        self.graphrag_available = False
        self._graph_doc_count = 0
        
        # Clear Neo4j graph if enabled
        if self.use_neo4j and self.neo4j_store:
            self.neo4j_store.clear_graph()
        
        if self.index_path.exists():
            shutil.rmtree(self.index_path)
            self.index_path.mkdir(exist_ok=True)
        
        logger.info("Index cleared (including Neo4j graph)" if self.use_neo4j else "Index cleared")
    
    def export_index_json(self, output_path: str = None) -> str:
        """
        Export the current index (documents and metadata) to a JSON file.
        This allows users to reload the parsed data without re-parsing.
        
        Args:
            output_path: Optional path for the output file
            
        Returns:
            Path to the exported JSON file
        """
        if not output_path:
            output_path = str(self.index_path / "exported_index.json")
        
        export_data = {
            "version": "1.0",
            "indexed_files": self.indexed_files,
            "documents": [
                {
                    "page_content": doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in self.documents
            ],
            "graph_index": self.graph_index
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"✓ Exported index to {output_path}")
        return output_path
    
    def import_index_json(self, json_path: str, progress_callback=None) -> Dict[str, Any]:
        """
        Import a previously exported index JSON file.
        This allows users to skip document parsing if they have pre-parsed data.
        
        Args:
            json_path: Path to the JSON file to import
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with import results
        """
        results = {
            "success": False,
            "documents_imported": 0,
            "files_imported": 0,
            "error": None
        }
        
        try:
            if progress_callback:
                progress_callback("Loading JSON file...")
            
            with open(json_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            if "documents" not in import_data:
                results["error"] = "Invalid JSON format: missing 'documents' field"
                return results
            
            if progress_callback:
                progress_callback("Importing documents...")
            
            new_documents = []
            for doc_data in import_data.get("documents", []):
                doc = Document(
                    page_content=doc_data.get("page_content", ""),
                    metadata=doc_data.get("metadata", {})
                )
                new_documents.append(doc)
            
            if new_documents:
                if progress_callback:
                    progress_callback("Building vector index...")
                
                if self.vectorstore is None and self.embeddings:
                    self.vectorstore = FAISSVectorStore.from_documents(new_documents, self.embeddings)
                elif self.vectorstore and self.embeddings:
                    new_vectorstore = FAISSVectorStore.from_documents(new_documents, self.embeddings)
                    self.vectorstore.merge_from(new_vectorstore)
                
                self.documents.extend(new_documents)
            
            imported_files = import_data.get("indexed_files", {})
            for path, meta in imported_files.items():
                if not self._is_file_indexed(meta.get("filename", ""), meta.get("file_size", 0)):
                    self.indexed_files[path] = meta
            
            if import_data.get("graph_index"):
                if self.graph_index:
                    existing_entities = set(self.graph_index.get("entities", []))
                    new_entities = import_data["graph_index"].get("entities", [])
                    self.graph_index["entities"] = list(existing_entities.union(set(new_entities)))
                    self.graph_index["relationships"].extend(
                        import_data["graph_index"].get("relationships", [])
                    )
                    self.graph_index["document_count"] = len(self.documents)
                else:
                    self.graph_index = import_data["graph_index"]
                    self.graph_index["document_count"] = len(self.documents)
                
                self.graphrag_available = True
                self._graph_doc_count = len(self.documents)
            
            self._save_index()
            
            results["success"] = True
            results["documents_imported"] = len(new_documents)
            results["files_imported"] = len(imported_files)
            
            logger.info(f"✓ Imported {len(new_documents)} documents from JSON")
            
        except json.JSONDecodeError as e:
            results["error"] = f"Invalid JSON format: {str(e)}"
            logger.error(f"JSON import failed: {e}")
        except Exception as e:
            results["error"] = str(e)
            logger.error(f"Import failed: {e}")
        
        return results
    
    def needs_graph_update(self) -> bool:
        """Check if the graph index needs to be updated with new documents."""
        if not self.graph_index:
            return len(self.documents) > 0
        return len(self.documents) > self._graph_doc_count
