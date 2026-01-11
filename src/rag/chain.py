"""
Agentic RAG chain with query restatement, GraphRAG retrieval, and conditional web search.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_CONFIG, SYSTEM_PROMPTS
from utils import get_logger
from rag.indexer import RAGIndexer

logger = get_logger(__name__)


class AgenticRAGChain:
    """
    Agentic RAG chain with query restatement, GraphRAG retrieval, and conditional web search.
    """
    
    def __init__(self, indexer: RAGIndexer):
        self.indexer = indexer
        
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3
        )
        
        self.web_search_available = False
        self.web_search = None
        self._init_web_search()
        
        self.restate_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["query_restatement"]),
            ("human", "Original query: {query}\nConversation context: {context}")
        ])
        
        self.evaluate_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["rag_evaluation"]),
            ("human", "Query: {query}\nRAG Result: {rag_result}")
        ])
        
        self.answer_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["rag_answer"]),
            ("human", "{query}")
        ])
    
    def _init_web_search(self):
        """Initialize web search tool."""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            self.web_search = DDGS()
            self.web_search_available = True
            logger.info("DuckDuckGo search initialized")
        except ImportError:
            logger.warning("DuckDuckGo search not available")
        except Exception as e:
            logger.warning(f"Failed to initialize web search: {e}")
    
    def restate_query(self, query: str, context: str = "") -> str:
        """Restate query for better retrieval."""
        try:
            chain = self.restate_prompt | self.llm
            result = chain.invoke({"query": query, "context": context})
            restated = result.content.strip()
            if restated and len(restated) > 5:
                logger.info(f"Query restated: '{query}' -> '{restated}'")
                return restated
        except Exception as e:
            logger.warning(f"Query restatement failed: {e}")
        return query
    
    def web_search_query(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        """Perform web search."""
        if not self.web_search_available or not self.web_search:
            return []
        
        try:
            results = list(self.web_search.text(query, max_results=max_results))
            logger.info(f"Web search returned {len(results)} results")
            return [{"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")} for r in results]
        except Exception as e:
            logger.warning(f"Web search failed: {e}")
            return []
    
    def evaluate_rag_result(self, query: str, rag_result: str) -> Tuple[bool, str]:
        """Evaluate if RAG result needs web search supplementation."""
        try:
            chain = self.evaluate_prompt | self.llm
            result = chain.invoke({"query": query, "rag_result": rag_result})
            content = result.content.strip()
            
            if content.startswith("NEEDS_WEBSEARCH:"):
                search_query = content.replace("NEEDS_WEBSEARCH:", "").strip()
                return True, search_query
            return False, ""
        except Exception as e:
            logger.warning(f"RAG evaluation failed: {e}")
            return False, ""
    
    def invoke(
        self,
        query: str,
        history: str = "",
        use_restatement: bool = True,
        use_graph: bool = True,
        use_websearch: bool = True
    ) -> Dict[str, Any]:
        """
        Execute the agentic RAG chain.
        
        Args:
            query: User query
            history: Conversation history
            use_restatement: Whether to use query restatement
            use_graph: Whether to use GraphRAG
            use_websearch: Whether to allow web search fallback
            
        Returns:
            Dictionary with answer and metadata
        """
        result = {
            "answer": "",
            "sources": [],
            "graph_entities": [],
            "web_sources": [],
            "query_restated": False,
            "web_search_triggered": False,
            "status": "success"
        }
        
        if not self.indexer.vectorstore:
            result["answer"] = "⚠️ No documents have been indexed yet. Please upload documents first."
            result["status"] = "no_index"
            return result
        
        try:
            search_query = query
            if use_restatement:
                search_query = self.restate_query(query, history)
                result["query_restated"] = search_query != query
            
            docs = self.indexer.similarity_search(search_query, k=5)
            doc_context = "\n\n".join([
                f"[Source: {doc.metadata.get('filename', 'Unknown')}]\n{doc.page_content}"
                for doc in docs
            ])
            
            result["sources"] = [
                {
                    "filename": doc.metadata.get("filename", "Unknown"),
                    "chunk": doc.metadata.get("chunk_index", 0),
                    "preview": doc.page_content[:200] + "..."
                }
                for doc in docs
            ]
            
            graph_context = ""
            if use_graph and self.indexer.graphrag_available:
                graph_result = self.indexer.graph_search(search_query)
                graph_context = graph_result.get("context", "")
                result["graph_entities"] = graph_result.get("entities", [])
            
            web_context = ""
            if use_websearch and self.web_search_available:
                rag_preview = doc_context[:1000] if doc_context else "No documents found"
                needs_web, web_query = self.evaluate_rag_result(query, rag_preview)
                
                if needs_web:
                    web_results = self.web_search_query(web_query or query)
                    if web_results:
                        web_context = "\n\n".join([
                            f"[Web: {r['title']}]\n{r['body']}\nSource: {r['href']}"
                            for r in web_results
                        ])
                        result["web_sources"] = web_results
                        result["web_search_triggered"] = True
            
            chain = self.answer_prompt | self.llm
            answer = chain.invoke({
                "query": query,
                "doc_context": doc_context or "No relevant documents found.",
                "graph_context": graph_context or "No graph context available.",
                "web_context": web_context or "No web search performed.",
                "history": history or "No previous conversation."
            })
            
            result["answer"] = answer.content
            
        except Exception as e:
            logger.error(f"RAG chain error: {e}")
            result["answer"] = f"❌ Error processing query: {str(e)}"
            result["status"] = "error"
        
        return result


def create_rag_system(index_path: str = "rag_index") -> Tuple[RAGIndexer, AgenticRAGChain]:
    """
    Create and return the RAG system components.
    
    Returns:
        Tuple of (RAGIndexer, AgenticRAGChain)
    """
    indexer = RAGIndexer(index_path=index_path)
    chain = AgenticRAGChain(indexer)
    return indexer, chain
