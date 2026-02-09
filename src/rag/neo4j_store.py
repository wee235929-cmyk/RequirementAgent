"""
Neo4j Graph Store for Knowledge Graph storage and querying.
Provides an alternative to JSON-based graph storage with full graph database capabilities.
"""
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from contextlib import contextmanager

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    GraphDatabase = None

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NEO4J_CONFIG
from utils import get_logger

logger = get_logger(__name__)


class Neo4jGraphStore:
    """
    Neo4j-based graph store for knowledge graph storage and retrieval.
    
    Features:
    - Store entities as nodes with labels and properties
    - Store relationships as edges with types
    - Support for incremental updates
    - Efficient graph queries using Cypher
    - Fallback to JSON storage if Neo4j is unavailable
    """
    
    def __init__(
        self,
        uri: str = None,
        username: str = None,
        password: str = None,
        database: str = "neo4j"
    ):
        """
        Initialize Neo4j connection.
        
        Args:
            uri: Neo4j connection URI (default from config)
            username: Neo4j username (default from config)
            password: Neo4j password (default from config)
            database: Database name (default: neo4j)
        """
        self.uri = uri or NEO4J_CONFIG["uri"]
        self.username = username or NEO4J_CONFIG["username"]
        self.password = password or NEO4J_CONFIG["password"]
        self.database = database
        
        self.driver = None
        self.connected = False
        
        if NEO4J_AVAILABLE:
            self._connect()
        else:
            logger.warning("Neo4j driver not installed. Run: pip install neo4j")
    
    def _connect(self) -> bool:
        """Establish connection to Neo4j database."""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password)
            )
            # Verify connection
            self.driver.verify_connectivity()
            self.connected = True
            logger.info(f"Connected to Neo4j at {self.uri}")
            
            # Initialize schema (indexes for better performance)
            self._init_schema()
            return True
            
        except AuthError as e:
            logger.error(f"Neo4j authentication failed: {e}")
            self.connected = False
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            self.connected = False
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self.connected = False
        
        return False
    
    def _init_schema(self):
        """Initialize Neo4j schema with indexes for better query performance."""
        try:
            with self.driver.session(database=self.database) as session:
                # Create index on Entity name for faster lookups
                session.run("""
                    CREATE INDEX entity_name_index IF NOT EXISTS
                    FOR (e:Entity) ON (e.name)
                """)
                # Create index on Entity type
                session.run("""
                    CREATE INDEX entity_type_index IF NOT EXISTS
                    FOR (e:Entity) ON (e.type)
                """)
                # Create full-text index for entity search
                session.run("""
                    CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
                    FOR (e:Entity) ON EACH [e.name, e.description]
                """)
                logger.info("Neo4j schema initialized with indexes")
        except Exception as e:
            # Indexes might already exist, which is fine
            logger.debug(f"Schema initialization note: {e}")
    
    @contextmanager
    def _session(self):
        """Context manager for Neo4j sessions."""
        if not self.connected or not self.driver:
            raise RuntimeError("Not connected to Neo4j")
        session = self.driver.session(database=self.database)
        try:
            yield session
        finally:
            session.close()
    
    def close(self):
        """Close the Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.connected = False
            logger.info("Neo4j connection closed")
    
    def clear_graph(self):
        """Clear all nodes and relationships from the graph."""
        if not self.connected:
            logger.warning("Cannot clear graph: not connected to Neo4j")
            return False
        
        try:
            with self._session() as session:
                # Delete all nodes and relationships
                session.run("MATCH (n) DETACH DELETE n")
                logger.info("Neo4j graph cleared")
                return True
        except Exception as e:
            logger.error(f"Failed to clear graph: {e}")
            return False
    
    def add_entities(self, entities: List[str], source_doc: str = None) -> int:
        """
        Add entities to the graph as nodes.
        
        Args:
            entities: List of entity names/strings
            source_doc: Optional source document identifier
            
        Returns:
            Number of entities added
        """
        if not self.connected:
            logger.warning("Cannot add entities: not connected to Neo4j")
            return 0
        
        added_count = 0
        try:
            with self._session() as session:
                for entity in entities:
                    entity = entity.strip()
                    if not entity:
                        continue
                    
                    # Determine entity type based on patterns
                    entity_type = self._detect_entity_type(entity)
                    
                    # MERGE to avoid duplicates
                    result = session.run("""
                        MERGE (e:Entity {name: $name})
                        ON CREATE SET 
                            e.type = $type,
                            e.created_at = datetime(),
                            e.source = $source
                        ON MATCH SET
                            e.updated_at = datetime()
                        RETURN e
                    """, name=entity, type=entity_type, source=source_doc or "unknown")
                    
                    if result.single():
                        added_count += 1
                
                logger.info(f"Added/updated {added_count} entities in Neo4j")
                
        except Exception as e:
            logger.error(f"Failed to add entities: {e}")
        
        return added_count
    
    def add_relationships(self, relationships: List[List[str]], source_doc: str = None) -> int:
        """
        Add relationships to the graph.
        
        Args:
            relationships: List of [source, relation_type, target] triples
            source_doc: Optional source document identifier
            
        Returns:
            Number of relationships added
        """
        if not self.connected:
            logger.warning("Cannot add relationships: not connected to Neo4j")
            return 0
        
        added_count = 0
        try:
            with self._session() as session:
                for rel in relationships:
                    if len(rel) < 3:
                        continue
                    
                    source, rel_type, target = rel[0].strip(), rel[1].strip(), rel[2].strip()
                    if not source or not target:
                        continue
                    
                    # Sanitize relationship type for Cypher (remove spaces, special chars)
                    rel_type_safe = re.sub(r'[^a-zA-Z0-9_]', '_', rel_type.upper())
                    if not rel_type_safe:
                        rel_type_safe = "RELATES_TO"
                    
                    # Create nodes if they don't exist, then create relationship
                    result = session.run(f"""
                        MERGE (s:Entity {{name: $source}})
                        ON CREATE SET s.type = $source_type, s.created_at = datetime()
                        MERGE (t:Entity {{name: $target}})
                        ON CREATE SET t.type = $target_type, t.created_at = datetime()
                        MERGE (s)-[r:{rel_type_safe}]->(t)
                        ON CREATE SET 
                            r.type = $rel_type,
                            r.created_at = datetime(),
                            r.source = $doc_source
                        RETURN r
                    """, 
                        source=source, 
                        target=target, 
                        rel_type=rel_type,
                        source_type=self._detect_entity_type(source),
                        target_type=self._detect_entity_type(target),
                        doc_source=source_doc or "unknown"
                    )
                    
                    if result.single():
                        added_count += 1
                
                logger.info(f"Added/updated {added_count} relationships in Neo4j")
                
        except Exception as e:
            logger.error(f"Failed to add relationships: {e}")
        
        return added_count
    
    def _detect_entity_type(self, entity: str) -> str:
        """Detect the type of entity based on patterns."""
        entity_upper = entity.upper()
        
        # Requirement IDs (e.g., REQ-001, FR-001, NFR-001)
        if re.match(r'^[A-Z]{2,}-\d+', entity_upper):
            return "REQUIREMENT"
        
        # Table references
        if "TABLE" in entity_upper or "表" in entity:
            return "TABLE"
        
        # Technical terms
        tech_keywords = ["API", "DATABASE", "SERVER", "CLIENT", "MODULE", "SYSTEM", "SERVICE"]
        if any(kw in entity_upper for kw in tech_keywords):
            return "TECHNOLOGY"
        
        # Default
        return "CONCEPT"
    
    def search_entities(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Search for entities matching the query.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of matching entities with their properties
        """
        if not self.connected:
            return []
        
        results = []
        try:
            with self._session() as session:
                query_lower = query.lower()
                query_words = set(query_lower.split())
                
                # Extract IDs from query (e.g., REQ-001, LGT-004)
                id_pattern = re.compile(r'[A-Z]{2,}-\d+', re.IGNORECASE)
                query_ids = [qid.upper() for qid in id_pattern.findall(query)]
                
                # First, try exact ID match
                if query_ids:
                    for qid in query_ids:
                        result = session.run("""
                            MATCH (e:Entity)
                            WHERE toUpper(e.name) CONTAINS $id
                            RETURN e.name as name, e.type as type
                            LIMIT $limit
                        """, id=qid, limit=limit)
                        
                        for record in result:
                            results.append({
                                "name": record["name"],
                                "type": record["type"]
                            })
                
                # Then, try full-text search
                if len(results) < limit:
                    try:
                        # Use full-text index if available
                        search_term = query + "~"
                        result = session.run("""
                            CALL db.index.fulltext.queryNodes('entity_fulltext', $search_term)
                            YIELD node, score
                            RETURN node.name as name, node.type as type, score
                            ORDER BY score DESC
                            LIMIT $limit
                        """, search_term=search_term, limit=limit - len(results))
                        
                        for record in result:
                            if record["name"] not in [r["name"] for r in results]:
                                results.append({
                                    "name": record["name"],
                                    "type": record["type"],
                                    "score": record["score"]
                                })
                    except Exception:
                        # Fallback to CONTAINS search if full-text index not available
                        result = session.run("""
                            MATCH (e:Entity)
                            WHERE toLower(e.name) CONTAINS $search_term
                            RETURN e.name as name, e.type as type
                            LIMIT $limit
                        """, search_term=query_lower, limit=limit - len(results))
                        
                        for record in result:
                            if record["name"] not in [r["name"] for r in results]:
                                results.append({
                                    "name": record["name"],
                                    "type": record["type"]
                                })
                
        except Exception as e:
            logger.error(f"Entity search failed: {e}")
        
        return results[:limit]
    
    def get_related_entities(self, entity_name: str, depth: int = 1, limit: int = 20) -> Dict[str, Any]:
        """
        Get entities related to a given entity.
        
        Args:
            entity_name: Name of the entity to find relations for
            depth: How many hops to traverse (default 1)
            limit: Maximum number of related entities
            
        Returns:
            Dictionary with related entities and relationships
        """
        if not self.connected:
            return {"entities": [], "relationships": []}
        
        result_data = {"entities": [], "relationships": []}
        
        try:
            with self._session() as session:
                # Find the entity and its neighbors
                result = session.run(f"""
                    MATCH (e:Entity {{name: $name}})-[r*1..{depth}]-(related:Entity)
                    RETURN DISTINCT related.name as name, related.type as type
                    LIMIT $limit
                """, name=entity_name, limit=limit)
                
                for record in result:
                    result_data["entities"].append({
                        "name": record["name"],
                        "type": record["type"]
                    })
                
                # Get relationships
                result = session.run("""
                    MATCH (e:Entity {name: $name})-[r]->(t:Entity)
                    RETURN e.name as source, type(r) as rel_type, t.name as target
                    UNION
                    MATCH (s:Entity)-[r]->(e:Entity {name: $name})
                    RETURN s.name as source, type(r) as rel_type, e.name as target
                    LIMIT $limit
                """, name=entity_name, limit=limit)
                
                for record in result:
                    result_data["relationships"].append([
                        record["source"],
                        record["rel_type"],
                        record["target"]
                    ])
                
        except Exception as e:
            logger.error(f"Failed to get related entities: {e}")
        
        return result_data
    
    def graph_search(self, query: str) -> Dict[str, Any]:
        """
        Search the knowledge graph for relevant entities and relationships.
        Compatible with the RAGIndexer.graph_search interface.
        
        Args:
            query: Search query
            
        Returns:
            Dictionary with entities, relationships, context, and found flag
        """
        if not self.connected:
            return {"entities": [], "relationships": [], "context": "", "found": False}
        
        # Search for matching entities
        matching_entities = self.search_entities(query, limit=15)
        
        if not matching_entities:
            return {"entities": [], "relationships": [], "context": "", "found": False}
        
        entity_names = [e["name"] for e in matching_entities]
        
        # Get relationships for found entities
        all_relationships = []
        try:
            with self._session() as session:
                for entity_name in entity_names[:5]:  # Limit to top 5 entities
                    result = session.run("""
                        MATCH (e:Entity {name: $name})-[r]->(t:Entity)
                        RETURN e.name as source, type(r) as rel_type, t.name as target
                        LIMIT 10
                    """, name=entity_name)
                    
                    for record in result:
                        all_relationships.append([
                            record["source"],
                            record["rel_type"],
                            record["target"]
                        ])
        except Exception as e:
            logger.error(f"Failed to get relationships: {e}")
        
        # Build context string
        context_parts = []
        if entity_names:
            context_parts.append(f"Related entities: {', '.join(entity_names[:15])}")
        if all_relationships:
            rel_strs = [f"{r[0]} {r[1]} {r[2]}" for r in all_relationships[:10]]
            context_parts.append(f"Relationships: {'; '.join(rel_strs)}")
        
        return {
            "entities": entity_names[:15],
            "relationships": all_relationships[:15],
            "context": "\n".join(context_parts),
            "found": len(entity_names) > 0
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the graph."""
        if not self.connected:
            return {"connected": False, "entity_count": 0, "relationship_count": 0}
        
        stats = {"connected": True, "entity_count": 0, "relationship_count": 0}
        
        try:
            with self._session() as session:
                # Count entities
                result = session.run("MATCH (e:Entity) RETURN count(e) as count")
                record = result.single()
                if record:
                    stats["entity_count"] = record["count"]
                
                # Count relationships
                result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                record = result.single()
                if record:
                    stats["relationship_count"] = record["count"]
                
                # Get entity types distribution
                result = session.run("""
                    MATCH (e:Entity)
                    RETURN e.type as type, count(*) as count
                    ORDER BY count DESC
                """)
                stats["entity_types"] = {record["type"]: record["count"] for record in result}
                
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
        
        return stats
    
    def export_to_dict(self) -> Dict[str, Any]:
        """
        Export the entire graph to a dictionary format.
        Compatible with the JSON-based graph_index format.
        
        Returns:
            Dictionary with entities and relationships
        """
        if not self.connected:
            return {"entities": [], "relationships": [], "document_count": 0}
        
        export_data = {"entities": [], "relationships": [], "document_count": 0}
        
        try:
            with self._session() as session:
                # Get all entities
                result = session.run("MATCH (e:Entity) RETURN e.name as name")
                export_data["entities"] = [record["name"] for record in result]
                
                # Get all relationships
                result = session.run("""
                    MATCH (s:Entity)-[r]->(t:Entity)
                    RETURN s.name as source, type(r) as rel_type, t.name as target
                """)
                export_data["relationships"] = [
                    [record["source"], record["rel_type"], record["target"]]
                    for record in result
                ]
                
                export_data["document_count"] = len(export_data["entities"])
                
        except Exception as e:
            logger.error(f"Failed to export graph: {e}")
        
        return export_data
    
    def import_from_dict(self, data: Dict[str, Any]) -> bool:
        """
        Import graph data from a dictionary (e.g., from JSON file).
        
        Args:
            data: Dictionary with 'entities' and 'relationships' keys
            
        Returns:
            True if successful
        """
        if not self.connected:
            logger.warning("Cannot import: not connected to Neo4j")
            return False
        
        try:
            entities = data.get("entities", [])
            relationships = data.get("relationships", [])
            
            if entities:
                self.add_entities(entities, source_doc="import")
            
            if relationships:
                self.add_relationships(relationships, source_doc="import")
            
            logger.info(f"Imported {len(entities)} entities and {len(relationships)} relationships")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import graph: {e}")
            return False


def create_neo4j_store() -> Optional[Neo4jGraphStore]:
    """
    Factory function to create a Neo4j graph store if enabled and available.
    
    Returns:
        Neo4jGraphStore instance if successful, None otherwise
    """
    if not NEO4J_CONFIG.get("enabled"):
        logger.info("Neo4j is not enabled in configuration")
        return None
    
    if not NEO4J_AVAILABLE:
        logger.warning("Neo4j driver not installed")
        return None
    
    store = Neo4jGraphStore()
    if store.connected:
        return store
    
    return None
