"""
Documents API routes for RAAA.
Handles file upload, indexing, and RAG index management.
"""
import os
import shutil
import tempfile
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel

from api.session import session_manager


router = APIRouter()


class IndexResult(BaseModel):
    """Document indexing result."""
    success: List[str]
    failed: List[dict]
    skipped: List[str]
    total_chunks: int


class IndexStats(BaseModel):
    """RAG index statistics."""
    indexed_files: int
    total_chunks: int
    has_graph: bool
    graph_storage: str
    neo4j_connected: bool
    neo4j_entity_count: int
    neo4j_relationship_count: int
    needs_graph_update: bool


@router.post("/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    auto_index: bool = Form(default=True),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Upload documents for RAG indexing.
    Optionally auto-index after upload.
    """
    session = session_manager.get_or_create_session(x_session_id)
    
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    temp_dir = tempfile.mkdtemp()
    uploaded_files = []
    
    try:
        # Save uploaded files to temp directory
        for file in files:
            temp_path = os.path.join(temp_dir, file.filename)
            with open(temp_path, 'wb') as f:
                content = await file.read()
                f.write(content)
            uploaded_files.append({
                "filename": file.filename,
                "path": temp_path,
                "size": len(content)
            })
        
        result = {
            "uploaded": [f["filename"] for f in uploaded_files],
            "count": len(uploaded_files),
            "session_id": session.session_id,
        }
        
        # Auto-index if requested
        if auto_index:
            index_result = await _index_files(session, temp_dir, uploaded_files)
            result["index_result"] = index_result
        else:
            # Store temp_dir path for later indexing
            result["temp_dir"] = temp_dir
            result["message"] = "Files uploaded. Call /index endpoint to index them."
        
        return result
        
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/index")
async def index_documents(
    file_paths: Optional[List[str]] = None,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Index documents that have been uploaded.
    If file_paths not provided, indexes all files in the session's temp directory.
    """
    session = session_manager.get_or_create_session(x_session_id)
    
    if not file_paths:
        raise HTTPException(
            status_code=400, 
            detail="No file paths provided. Use /upload with auto_index=true instead."
        )
    
    rag_indexer = session.orchestrator.get_rag_indexer()
    
    try:
        # Separate JSON files from regular documents
        json_files = [p for p in file_paths if p.endswith('.json')]
        doc_files = [p for p in file_paths if not p.endswith('.json')]
        
        results = {
            "success": [],
            "failed": [],
            "skipped": [],
            "total_chunks": 0,
            "json_imported": 0,
        }
        
        # Import JSON index files
        for json_path in json_files:
            if os.path.exists(json_path):
                import_result = rag_indexer.import_index_json(json_path)
                if import_result.get("success"):
                    results["json_imported"] += import_result.get("documents_imported", 0)
                    results["success"].append(os.path.basename(json_path))
                else:
                    results["failed"].append({
                        "file": os.path.basename(json_path),
                        "error": import_result.get("error", "Unknown error")
                    })
        
        # Index regular documents
        if doc_files:
            index_result = rag_indexer.index_documents(doc_files)
            results["success"].extend(index_result.get("success", []))
            results["failed"].extend(index_result.get("failed", []))
            results["skipped"].extend(index_result.get("skipped", []))
            results["total_chunks"] = index_result.get("total_chunks", 0)
        
        # Update session's indexed files
        for filename in results["success"]:
            session.indexed_files.add(filename)
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


async def _index_files(session, temp_dir: str, uploaded_files: List[dict]) -> dict:
    """Internal helper to index uploaded files."""
    rag_indexer = session.orchestrator.get_rag_indexer()
    
    json_files = []
    doc_files = []
    
    for f in uploaded_files:
        if f["filename"].endswith('.json'):
            json_files.append(f["path"])
        else:
            doc_files.append(f["path"])
    
    results = {
        "success": [],
        "failed": [],
        "skipped": [],
        "total_chunks": 0,
        "json_imported": 0,
    }
    
    try:
        # Import JSON files
        for json_path in json_files:
            import_result = rag_indexer.import_index_json(json_path)
            if import_result.get("success"):
                results["json_imported"] += import_result.get("documents_imported", 0)
                results["success"].append(os.path.basename(json_path))
            else:
                results["failed"].append({
                    "file": os.path.basename(json_path),
                    "error": import_result.get("error", "Unknown error")
                })
        
        # Index documents
        if doc_files:
            index_result = rag_indexer.index_documents(doc_files)
            results["success"].extend(index_result.get("success", []))
            results["failed"].extend(index_result.get("failed", []))
            results["skipped"].extend(index_result.get("skipped", []))
            results["total_chunks"] = index_result.get("total_chunks", 0)
        
        # Update session
        for filename in results["success"]:
            session.indexed_files.add(filename)
        
    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return results


@router.post("/graph/build")
async def build_knowledge_graph(
    force_rebuild: bool = False,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Build or update the GraphRAG knowledge graph."""
    session = session_manager.get_or_create_session(x_session_id)
    rag_indexer = session.orchestrator.get_rag_indexer()
    
    try:
        success = rag_indexer.build_graph_index(force_rebuild=force_rebuild)
        return {
            "success": success,
            "action": "rebuild" if force_rebuild else "update",
            "message": "Knowledge graph updated successfully" if success else "Graph building completed with warnings"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph building failed: {str(e)}")


@router.get("/export")
async def export_index(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Export the current RAG index to JSON."""
    session = session_manager.get_or_create_session(x_session_id)
    rag_indexer = session.orchestrator.get_rag_indexer()
    
    try:
        export_path = rag_indexer.export_index_json()
        
        with open(export_path, 'r', encoding='utf-8') as f:
            export_data = f.read()
        
        return {
            "success": True,
            "path": export_path,
            "filename": os.path.basename(export_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/export/download")
async def download_export(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Download the exported RAG index as a file."""
    from fastapi.responses import FileResponse
    
    session = session_manager.get_or_create_session(x_session_id)
    rag_indexer = session.orchestrator.get_rag_indexer()
    
    try:
        export_path = rag_indexer.export_index_json()
        return FileResponse(
            path=export_path,
            filename="rag_index_export.json",
            media_type="application/json"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.delete("/clear")
async def clear_index(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Clear the RAG index including Neo4j graph if connected."""
    session = session_manager.get_or_create_session(x_session_id)
    
    try:
        session.orchestrator.clear_rag_index()
        session.indexed_files = set()
        
        return {
            "success": True,
            "message": "Index cleared successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clear failed: {str(e)}")


@router.get("/files")
async def list_indexed_files(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """List all indexed files in the current session."""
    session = session_manager.get_or_create_session(x_session_id)
    
    return {
        "files": list(session.indexed_files),
        "count": len(session.indexed_files)
    }
