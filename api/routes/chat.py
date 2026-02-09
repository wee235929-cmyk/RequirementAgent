"""
Chat API routes for RAAA.
Handles chat messages, streaming responses, and intent detection.
"""
import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.session import session_manager


router = APIRouter()


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    role: Optional[str] = None  # User role (e.g., "Requirements Analyst")


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    intent: str
    chain_of_thought: List[str] = []
    mermaid_chart: Optional[str] = None
    pdf_path: Optional[str] = None
    docx_path: Optional[str] = None


class IntentResponse(BaseModel):
    """Intent detection response."""
    intent: str
    is_mixed: bool


@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Send a chat message and get a response.
    Non-streaming endpoint for standard processing.
    """
    session = session_manager.get_or_create_session(x_session_id)
    
    # Update role if provided
    if request.role:
        session.selected_role = request.role
    
    # Add user message to history
    session.messages.append({"role": "user", "content": request.message})
    
    try:
        # Check if files are indexed
        has_files = len(session.indexed_files) > 0
        
        # Process message through orchestrator
        result = session.orchestrator.process(
            user_input=request.message,
            role=session.selected_role,
            uploaded_files=[]  # Files are already indexed
        )
        
        response_content = result.get("response", "")
        
        # Add assistant response to history
        session.messages.append({"role": "assistant", "content": response_content})
        
        return ChatResponse(
            response=response_content,
            intent=result.get("intent", "unknown"),
            chain_of_thought=result.get("chain_of_thought", []),
            mermaid_chart=result.get("mermaid_chart"),
            pdf_path=result.get("pdf_path"),
            docx_path=result.get("docx_path"),
        )
        
    except Exception as e:
        error_msg = f"Error processing message: {str(e)}"
        session.messages.append({"role": "assistant", "content": error_msg})
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/stream")
async def stream_message(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Send a chat message and get a streaming response.
    Uses Server-Sent Events (SSE) for real-time streaming.
    """
    session = session_manager.get_or_create_session(x_session_id)
    
    if request.role:
        session.selected_role = request.role
    
    session.messages.append({"role": "user", "content": request.message})
    
    async def generate():
        """Generate SSE stream."""
        full_response = ""
        try:
            # Detect intent first
            has_files = len(session.indexed_files) > 0
            intent = session.orchestrator.detect_intent(
                request.message,
                session.selected_role,
                has_files
            )
            
            # Send intent event
            yield f"event: intent\ndata: {intent}\n\n"
            
            # For general chat, use streaming
            if intent == "general_chat":
                for chunk in session.orchestrator.stream_general_chat(request.message):
                    full_response += chunk
                    yield f"data: {chunk}\n\n"
                    await asyncio.sleep(0)  # Allow other tasks to run
            else:
                # For other intents, process normally and send as single chunk
                result = session.orchestrator.process(
                    user_input=request.message,
                    role=session.selected_role,
                    uploaded_files=[]
                )
                full_response = result.get("response", "")
                yield f"data: {full_response}\n\n"
                
                # Send additional data if available
                if result.get("mermaid_chart"):
                    yield f"event: mermaid\ndata: {result['mermaid_chart']}\n\n"
                if result.get("pdf_path"):
                    yield f"event: pdf\ndata: {result['pdf_path']}\n\n"
                if result.get("docx_path"):
                    yield f"event: docx\ndata: {result['docx_path']}\n\n"
            
            # Signal completion
            yield "event: done\ndata: complete\n\n"
            
            # Save to session
            session.messages.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session.session_id,
        }
    )


@router.post("/detect-intent", response_model=IntentResponse)
async def detect_intent(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Detect the intent of a message without processing it."""
    session = session_manager.get_or_create_session(x_session_id)
    
    has_files = len(session.indexed_files) > 0
    intent = session.orchestrator.detect_intent(
        request.message,
        session.selected_role or "Requirements Analyst",
        has_files
    )
    
    is_mixed = session.orchestrator.is_mixed_intent(intent)
    
    return IntentResponse(intent=intent, is_mixed=is_mixed)


@router.get("/history")
async def get_chat_history(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Get chat history for the current session."""
    session = session_manager.get_or_create_session(x_session_id)
    return {
        "session_id": session.session_id,
        "messages": session.messages,
        "selected_role": session.selected_role,
    }


@router.delete("/history")
async def clear_chat_history(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Clear chat history for the current session."""
    session = session_manager.get_or_create_session(x_session_id)
    session.messages = []
    return {"status": "cleared", "session_id": session.session_id}


@router.post("/role")
async def set_role(
    role: str,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Set the user role for the current session."""
    session = session_manager.get_or_create_session(x_session_id)
    session.selected_role = role
    return {"status": "updated", "role": role}
