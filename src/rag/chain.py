"""
Agentic RAG Chain - 智能检索增强生成链

实现智能的文档问答功能，支持：
    - 查询重写：优化用户查询以提高检索效果
    - 混合检索：同时使用向量检索、图检索和关键词检索
    - 结果排序：智能排序和合并多种检索结果
    - 网络回退：本地结果不足时自动搜索网络

检索策略：
    1. Query Rewriting: 代理重写查询以获得更好的检索结果
    2. Hybrid Search: 同时运行图、向量和关键词搜索
    3. Result Ranking: 代理对所有策略的结果进行排序和合并
    4. Fallback: 如果本地结果不足，则进行网络搜索
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import LLM_CONFIG, SYSTEM_PROMPTS
from utils import get_logger
from rag.indexer import RAGIndexer
from integrations.langfuse import get_langfuse_handler, is_langfuse_enabled

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
        
        # LangFuse tracing
        self._langfuse_enabled = is_langfuse_enabled()
        if self._langfuse_enabled:
            logger.info("LangFuse tracing enabled for AgenticRAGChain")
        
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
        
        self.graph_decision_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a search strategy expert. Analyze the user's query and decide if a knowledge graph search would be beneficial.

Graph search is useful when:
1. The query asks about relationships between entities (e.g., "how does X relate to Y")
2. The query references specific IDs or codes (e.g., REQ-001, LGT-004, INT-003)
3. The query asks about dependencies, connections, or associations
4. The query needs to trace requirements, features, or components

Graph search is NOT needed when:
1. The query is a simple factual question
2. The query asks for definitions or explanations
3. The query is about general concepts without specific entity references
4. Vector/keyword search results are likely sufficient

Respond with ONLY one of:
- "USE_GRAPH: <reason>" if graph search would help
- "SKIP_GRAPH: <reason>" if graph search is not needed"""),
            ("human", "Query: {query}\nRewritten query: {rewritten_query}\nAvailable graph entities: {available_entities}")
        ])
        
        self.answer_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["rag_answer"]),
            ("human", "{query}")
        ])
    
    def _get_langfuse_callbacks(self, operation: str = None) -> list:
        """Get LangFuse callbacks if enabled."""
        if not self._langfuse_enabled:
            return []
        
        handler = get_langfuse_handler(
            tags=["raaa", "rag", f"op:{operation}"] if operation else ["raaa", "rag"],
        )
        return [handler] if handler else []
    
    def _invoke_with_langfuse(self, chain, inputs: dict, operation: str = None):
        """Invoke a chain with LangFuse callbacks if enabled."""
        callbacks = self._get_langfuse_callbacks(operation)
        if callbacks:
            return chain.invoke(inputs, config={"callbacks": callbacks})
        return chain.invoke(inputs)
    
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
            result = self._invoke_with_langfuse(
                chain,
                {"query": query, "context": context or "No context"},
                operation="query_rewrite"
            )
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
            result = self._invoke_with_langfuse(
                chain,
                {"query": query, "documents": "\n\n".join(doc_summaries)},
                operation="doc_ranking"
            )
            
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
            result = self._invoke_with_langfuse(
                chain,
                {"query": query, "rag_result": rag_result},
                operation="rag_evaluation"
            )
            content = result.content.strip()
            
            if content.startswith("NEEDS_WEBSEARCH:"):
                search_query = content.replace("NEEDS_WEBSEARCH:", "").strip()
                return True, search_query
            return False, ""
        except Exception as e:
            logger.warning(f"RAG evaluation failed: {e}")
            return False, ""
    
    def should_use_graph_search(self, query: str, rewritten_query: str) -> Tuple[bool, str]:
        """
        Use Agent to decide if graph search is beneficial for this query.
        
        Returns:
            Tuple of (should_use_graph, reason)
        """
        if not self.indexer.graphrag_available:
            return False, "Graph not available"
        
        try:
            # Get a sample of available entities to help the agent decide
            graph_stats = self.indexer.get_index_stats()
            available_entities = "Graph available"
            if graph_stats.get('neo4j_connected'):
                available_entities = f"Neo4j connected with {graph_stats.get('neo4j_entity_count', 0)} entities"
            
            chain = self.graph_decision_prompt | self.llm
            result = self._invoke_with_langfuse(
                chain,
                {"query": query, "rewritten_query": rewritten_query, "available_entities": available_entities},
                operation="graph_decision"
            )
            content = result.content.strip()
            
            if content.startswith("USE_GRAPH:"):
                reason = content.replace("USE_GRAPH:", "").strip()
                logger.info(f"Agent decided to use graph search: {reason}")
                return True, reason
            else:
                reason = content.replace("SKIP_GRAPH:", "").strip() if content.startswith("SKIP_GRAPH:") else content
                logger.info(f"Agent decided to skip graph search: {reason}")
                return False, reason
                
        except Exception as e:
            logger.warning(f"Graph decision failed: {e}, defaulting to skip")
            return False, f"Decision failed: {e}"
    
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
            
            # PRIORITY 1: Vector search (always run first)
            vector_docs = self.indexer.similarity_search(search_query, k=8)
            for doc in vector_docs:
                content_hash = hash(doc.page_content[:200])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    all_docs.append(doc)
            if vector_docs:
                methods_used.append("vector")
            
            # PRIORITY 2: Keyword search (always run)
            keyword_docs = self.indexer.keyword_search(search_query, k=8)
            for doc in keyword_docs:
                content_hash = hash(doc.page_content[:200])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    all_docs.append(doc)
            if keyword_docs:
                methods_used.append("keyword")
            
            # PRIORITY 3: Graph search (conditional - Agent decides if needed)
            if use_graph and self.indexer.graphrag_available:
                should_use_graph, graph_reason = self.should_use_graph_search(query, search_query)
                result["graph_decision_reason"] = graph_reason
                
                if should_use_graph:
                    graph_result = self.indexer.graph_search(search_query)
                    graph_context = graph_result.get("context", "")
                    graph_entities = graph_result.get("entities", [])
                    if graph_result.get("found"):
                        methods_used.append("graph")
            
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
            answer = self._invoke_with_langfuse(
                chain,
                {
                    "query": query,
                    "doc_context": doc_context or "No relevant documents found.",
                    "graph_context": graph_context or "No graph context available.",
                    "web_context": web_context or "No web search performed.",
                    "history": history or "No previous conversation."
                },
                operation="rag_answer"
            )
            
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
