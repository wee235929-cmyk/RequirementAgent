"""
Deep Research API routes for RAAA.
Handles background research tasks with async execution.
"""
import os
import threading
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.session import (
    session_manager,
    get_deep_research_results,
    get_deep_research_lock,
)


router = APIRouter()


class ResearchRequest(BaseModel):
    """Deep research request."""
    query: str
    role: Optional[str] = None


class ResearchStartResponse(BaseModel):
    """Response when starting a research task."""
    task_id: str
    status: str
    message: str


class ResearchStatusResponse(BaseModel):
    """Research task status response."""
    task_id: str
    status: str  # "running", "completed", "error", "not_found"
    query: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    has_result: bool = False


def _run_deep_research_background(
    task_id: str,
    session_id: str,
    query: str,
    role: str
):
    """Run Deep Research in background thread."""
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    try:
        # Get session (may create new orchestrator if session expired)
        session = session_manager.get_session(session_id)
        if not session:
            with lock:
                results[task_id] = {
                    "status": "error",
                    "error": "Session expired",
                    "completed_at": datetime.now().isoformat()
                }
            return
        
        # Run the research
        result = session.orchestrator.process(
            user_input=query,
            role=role,
            uploaded_files=[]
        )
        
        with lock:
            results[task_id] = {
                "status": "completed",
                "result": result,
                "completed_at": datetime.now().isoformat()
            }
            
        # Update session state
        session.deep_research_result = result
        session.deep_research_status = "completed"
        
    except Exception as e:
        with lock:
            results[task_id] = {
                "status": "error",
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            }


@router.post("/start", response_model=ResearchStartResponse)
async def start_research(
    request: ResearchRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Start a Deep Research task in the background.
    Returns immediately with a task_id for status polling.
    """
    session = session_manager.get_or_create_session(x_session_id)
    
    if request.role:
        session.selected_role = request.role
    
    # Generate task ID
    task_id = f"dr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(request.query) % 10000}"
    
    # Initialize task status
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    with lock:
        results[task_id] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "query": request.query
        }
    
    # Update session state
    session.deep_research_task = task_id
    session.deep_research_status = "running"
    session.deep_research_query = request.query
    
    # Add user message to history
    session.messages.append({"role": "user", "content": request.query})
    
    # Start background thread
    thread = threading.Thread(
        target=_run_deep_research_background,
        args=(task_id, session.session_id, request.query, session.selected_role),
        daemon=True
    )
    thread.start()
    
    return ResearchStartResponse(
        task_id=task_id,
        status="running",
        message="Deep Research started. Poll /status/{task_id} for updates."
    )


@router.get("/status/{task_id}", response_model=ResearchStatusResponse)
async def get_research_status(
    task_id: str,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get the status of a Deep Research task."""
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    with lock:
        task_info = results.get(task_id)
    
    if not task_info:
        return ResearchStatusResponse(
            task_id=task_id,
            status="not_found"
        )
    
    return ResearchStatusResponse(
        task_id=task_id,
        status=task_info.get("status", "unknown"),
        query=task_info.get("query"),
        started_at=task_info.get("started_at"),
        completed_at=task_info.get("completed_at"),
        error=task_info.get("error"),
        has_result="result" in task_info
    )


@router.get("/result/{task_id}")
async def get_research_result(
    task_id: str,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get the result of a completed Deep Research task."""
    session = session_manager.get_or_create_session(x_session_id)
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    with lock:
        task_info = results.get(task_id)
    
    if not task_info:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task_info.get("status") != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Task not completed. Status: {task_info.get('status')}"
        )
    
    result = task_info.get("result", {})
    
    # Add response to session messages
    response_content = result.get("response", "Research completed.")
    session.messages.append({
        "role": "assistant",
        "content": f"🔬 **Deep Research Completed!**\n\n{response_content}"
    })
    
    return {
        "task_id": task_id,
        "response": result.get("response"),
        "intent": result.get("intent"),
        "chain_of_thought": result.get("chain_of_thought", []),
        "pdf_path": result.get("pdf_path"),
        "docx_path": result.get("docx_path"),
    }


@router.get("/download/pdf/{task_id}")
async def download_research_pdf(
    task_id: str,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Download the PDF report for a completed research task."""
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    with lock:
        task_info = results.get(task_id)
    
    if not task_info or task_info.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Completed task not found")
    
    result = task_info.get("result", {})
    pdf_path = result.get("pdf_path")
    
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not available")
    
    return FileResponse(
        path=pdf_path,
        filename=os.path.basename(pdf_path),
        media_type="application/pdf"
    )


@router.get("/download/docx/{task_id}")
async def download_research_docx(
    task_id: str,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Download the Word report for a completed research task."""
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    with lock:
        task_info = results.get(task_id)
    
    if not task_info or task_info.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Completed task not found")
    
    result = task_info.get("result", {})
    docx_path = result.get("docx_path")
    
    if not docx_path or not os.path.exists(docx_path):
        raise HTTPException(status_code=404, detail="Word report not available")
    
    return FileResponse(
        path=docx_path,
        filename=os.path.basename(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@router.delete("/clear/{task_id}")
async def clear_research_task(
    task_id: str,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Clear a completed research task."""
    session = session_manager.get_or_create_session(x_session_id)
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    with lock:
        if task_id in results:
            del results[task_id]
    
    # Clear session state if this was the active task
    if session.deep_research_task == task_id:
        session.deep_research_task = None
        session.deep_research_status = None
        session.deep_research_query = None
        session.deep_research_result = None
    
    return {"success": True, "message": "Task cleared."}


@router.get("/current")
async def get_current_research(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get the current research task status for this session."""
    session = session_manager.get_or_create_session(x_session_id)
    
    if not session.deep_research_task:
        return {
            "has_task": False,
            "message": "No active research task."
        }
    
    # Get task status
    results = get_deep_research_results()
    lock = get_deep_research_lock()
    
    with lock:
        task_info = results.get(session.deep_research_task, {})
    
    return {
        "has_task": True,
        "task_id": session.deep_research_task,
        "status": task_info.get("status", session.deep_research_status),
        "query": session.deep_research_query,
    }
