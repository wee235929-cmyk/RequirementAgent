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
    Agentic RAG chain with query rewriting, true hybrid retrieval, and conditional web search.
    
    Retrieval Strategy:
    1. Query Rewriting: Agent rewrites query for better retrieval
    2. Hybrid Search: Runs graph, vector, and keyword search simultaneously
    3. Result Ranking: Agent ranks and merges results from all strategies
    4. Fallback: Web search if local results are insufficient
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
        
        self.rewrite_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a query rewriting expert for document retrieval.
Rewrite the user's query to improve retrieval results. Consider:
1. Extract key terms, IDs (like INT-004, REQ-001), and concepts
2. Expand abbreviations if helpful
3. Add synonyms for important terms
4. Keep the query focused and specific

Output format: Return ONLY the rewritten query, nothing else.
If the query is already optimal, return it unchanged."""),
            ("human", "Original query: {query}\nContext: {context}")
        ])
        
        self.rank_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a relevance ranking expert. Given a query and retrieved documents, 
rank them by relevance (1=most relevant). Consider:
1. Direct answer to the query
2. Contains specific IDs or terms mentioned in query
3. Provides context or related information

Output format: Return comma-separated indices of documents in order of relevance.
Example: "2,0,3,1" means doc 2 is most relevant, then doc 0, etc."""),
            ("human", "Query: {query}\n\nDocuments:\n{documents}")
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
    
    def rewrite_query(self, query: str, context: str = "") -> str:
        """
        Rewrite query for better retrieval using LLM.
        Extracts key terms, IDs, and concepts to improve search results.
        """
        try:
            chain = self.rewrite_prompt | self.llm
            result = chain.invoke({"query": query, "context": context or "No context"})
            rewritten = result.content.strip()
            if rewritten and len(rewritten) > 3:
                logger.info(f"Query rewritten: '{query}' -> '{rewritten}'")
                return rewritten
        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}")
        return query
    
    def rank_documents(self, query: str, docs: List) -> List:
        """
        Use LLM to rank documents by relevance to the query.
        Returns documents in ranked order.
        """
        if not docs or len(docs) <= 1:
            return docs
        
        try:
            doc_summaries = []
            for i, doc in enumerate(docs[:10]):
                preview = doc.page_content[:300].replace('\n', ' ')
                doc_summaries.append(f"[{i}] {preview}")
            
            chain = self.rank_prompt | self.llm
            result = chain.invoke({
                "query": query,
                "documents": "\n\n".join(doc_summaries)
            })
            
            ranking_str = result.content.strip()
            indices = []
            for part in ranking_str.replace(" ", "").split(","):
                try:
                    idx = int(part)
                    if 0 <= idx < len(docs) and idx not in indices:
                        indices.append(idx)
                except ValueError:
                    continue
            
            for i in range(len(docs)):
                if i not in indices:
                    indices.append(i)
            
            ranked_docs = [docs[i] for i in indices if i < len(docs)]
            logger.info(f"Documents ranked: {indices[:5]}...")
            return ranked_docs
            
        except Exception as e:
            logger.warning(f"Document ranking failed: {e}")
            return docs
    
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
        use_rewriting: bool = True,
        use_graph: bool = True,
        use_websearch: bool = True
    ) -> Dict[str, Any]:
        """
        Execute the agentic RAG chain with true hybrid retrieval.
        
        Strategy:
        1. Rewrite query for better retrieval
        2. Run ALL search strategies simultaneously (graph, vector, keyword)
        3. Merge and deduplicate results
        4. Rank results by relevance using LLM
        5. If results insufficient, try web search
        
        Args:
            query: User query
            history: Conversation history
            use_rewriting: Whether to use query rewriting
            use_graph: Whether to use GraphRAG
            use_websearch: Whether to allow web search fallback
            
        Returns:
            Dictionary with answer and metadata
        """
        result = {
            "answer": "",
            "sources": [],
            "graph_entities": [],
            "graph_context": "",
            "web_sources": [],
            "query_rewritten": False,
            "rewritten_query": "",
            "web_search_triggered": False,
            "search_methods": [],
            "status": "success"
        }
        
        if not self.indexer.vectorstore:
            result["answer"] = "⚠️ No documents have been indexed yet. Please upload documents first."
            result["status"] = "no_index"
            return result
        
        try:
            search_query = query
            if use_rewriting:
                search_query = self.rewrite_query(query, history)
                result["query_rewritten"] = search_query != query
                result["rewritten_query"] = search_query
            
            all_docs = []
            seen_content = set()
            graph_context = ""
            graph_entities = []
            methods_used = []
            
            if use_graph and self.indexer.graphrag_available:
                graph_result = self.indexer.graph_search(search_query)
                graph_context = graph_result.get("context", "")
                graph_entities = graph_result.get("entities", [])
                if graph_result.get("found"):
                    methods_used.append("graph")
            
            vector_docs = self.indexer.similarity_search(search_query, k=8)
            for doc in vector_docs:
                content_hash = hash(doc.page_content[:200])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    all_docs.append(doc)
            if vector_docs:
                methods_used.append("vector")
            
            keyword_docs = self.indexer.keyword_search(search_query, k=8)
            for doc in keyword_docs:
                content_hash = hash(doc.page_content[:200])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    all_docs.append(doc)
            if keyword_docs:
                methods_used.append("keyword")
            
            if search_query != query:
                orig_vector = self.indexer.similarity_search(query, k=5)
                for doc in orig_vector:
                    content_hash = hash(doc.page_content[:200])
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        all_docs.append(doc)
                
                orig_keyword = self.indexer.keyword_search(query, k=5)
                for doc in orig_keyword:
                    content_hash = hash(doc.page_content[:200])
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        all_docs.append(doc)
            
            logger.info(f"Hybrid search collected {len(all_docs)} unique docs via {methods_used}")
            
            if len(all_docs) > 3:
                all_docs = self.rank_documents(query, all_docs)
            
            docs = all_docs[:10]
            
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
            result["search_methods"] = methods_used
            result["graph_context"] = graph_context
            result["graph_entities"] = graph_entities
            
            web_context = ""
            if use_websearch and self.web_search_available and not docs:
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
            logger.info(f"RAG completed: {len(docs)} docs, methods={methods_used}")
            
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
