"""
RAG (Retrieval-Augmented Generation) - 检索增强生成模块

提供文档解析、索引和检索能力，支持基于文档的智能问答。

核心组件：
    - DocumentParser: 文档解析器，支持 PDF、Word、Markdown 等格式
    - RAGIndexer: 索引器，使用 FAISS 向量存储和可选的 Neo4j 图存储
    - AgenticRAGChain: 智能 RAG 链，支持查询重写、混合检索和结果排序
    - Neo4jGraphStore: Neo4j 图存储，用于实体关系的图谱检索

使用示例：
    from rag import create_rag_system
    
    indexer, chain = create_rag_system()
    indexer.index_file("document.pdf")
    result = chain.invoke("查询问题")
"""
from .parser import DocumentParser
from .indexer import RAGIndexer
from .chain import AgenticRAGChain, create_rag_system
from .neo4j_store import Neo4jGraphStore, create_neo4j_store

__all__ = [
    "DocumentParser",
    "RAGIndexer", 
    "AgenticRAGChain",
    "create_rag_system",
    "Neo4jGraphStore",
    "create_neo4j_store",
]
