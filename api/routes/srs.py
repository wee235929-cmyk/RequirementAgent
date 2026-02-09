"""
SRS Generation API routes for RAAA.
Handles Software Requirements Specification generation and download.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from api.session import session_manager
from src.requirements.roles import select_role_prompt
from src.requirements.generator import RequirementsGenerator


router = APIRouter()


class SRSRequest(BaseModel):
    """SRS generation request."""
    focus: Optional[str] = None  # Focus area for requirements


class SRSResponse(BaseModel):
    """SRS generation response."""
    success: bool
    markdown: Optional[str] = None
    entities_stored: int = 0
    message: str


@router.post("/generate", response_model=SRSResponse)
async def generate_srs(
    request: SRSRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Generate an SRS document from conversation context.
    Requires prior conversation history.
    """
    session = session_manager.get_or_create_session(x_session_id)
    
    if not session.messages:
        return SRSResponse(
            success=False,
            message="Please have a conversation first to provide context."
        )
    
    try:
        # Get role prompt
        role_prompt = select_role_prompt(session.selected_role)
        formatted_role = role_prompt.format(
            focus=request.focus or "General requirements",
            history="See conversation history below"
        )
        
        # Get memory and history
        memory = session.orchestrator.get_memory()
        history = memory.get_summary()
        focus = request.focus if request.focus else "Based on conversation context"
        
        # Generate SRS
        result = session.requirements_generator.invoke(
            role_prompt=formatted_role,
            history=history,
            focus=focus
        )
        
        # Convert to markdown
        srs_markdown = RequirementsGenerator.to_markdown(result)
        
        # Store in session
        session.generated_srs = result
        session.srs_markdown = srs_markdown
        
        # Extract and store entities
        entities = RequirementsGenerator.extract_entities_for_storage(result)
        for entity in entities:
            memory.store_entity(entity["text"], entity["metadata"])
        
        return SRSResponse(
            success=True,
            markdown=srs_markdown,
            entities_stored=len(entities),
            message=f"SRS generated successfully! Stored {len(entities)} requirements."
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SRS generation failed: {str(e)}")


@router.get("/download")
async def download_srs(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Download the generated SRS as markdown."""
    session = session_manager.get_or_create_session(x_session_id)
    
    if not session.srs_markdown:
        raise HTTPException(status_code=404, detail="No SRS generated yet. Call /generate first.")
    
    return PlainTextResponse(
        content=session.srs_markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": "attachment; filename=srs.md"
        }
    )


@router.get("/current")
async def get_current_srs(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get the current generated SRS if available."""
    session = session_manager.get_or_create_session(x_session_id)
    
    if not session.generated_srs:
        return {
            "available": False,
            "message": "No SRS generated yet."
        }
    
    return {
        "available": True,
        "markdown": session.srs_markdown,
        "data": session.generated_srs
    }


@router.delete("/clear")
async def clear_srs(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Clear the generated SRS."""
    session = session_manager.get_or_create_session(x_session_id)
    
    session.generated_srs = None
    session.srs_markdown = None
    
    return {"success": True, "message": "SRS cleared."}
