"""Requirements Analysis Agent Assistant (RAAA) - Streamlit Application."""
import os
import sys
import shutil
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).parent))
from src.config import USER_ROLES, DEFAULT_ROLE, SUPPORTED_FILE_TYPES, APP_TITLE
from src.agents.orchestrator import OrchestratorAgent, DEV_MODE
from src.modules.requirements_generator import RequirementsGenerator
from src.modules.roles import select_role_prompt

# LangSmith tracing URL
LANGSMITH_PROJECT_URL = "https://smith.langchain.com/o/raaa/projects/p/RAAA"


# =============================================================================
# Session State Management
# =============================================================================

SESSION_DEFAULTS = {
    "messages": [],
    "selected_role": DEFAULT_ROLE,
    "uploaded_files": [],
    "orchestrator": None,
    "requirements_generator": None,
    "generated_srs": None,
    "srs_markdown": None,
    "indexed_files": set(),
    "indexing_status": None,
    "last_chain_of_thought": [],
}


def initialize_session_state():
    """Initialize all session state variables with defaults."""
    for key, default in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            if key == "orchestrator":
                st.session_state[key] = OrchestratorAgent()
            elif key == "requirements_generator":
                st.session_state[key] = RequirementsGenerator()
            elif key == "indexed_files":
                st.session_state[key] = set()
            else:
                st.session_state[key] = default


# =============================================================================
# Document Indexing Functions
# =============================================================================

def index_documents(files):
    """Index uploaded documents with progress display."""
    rag_indexer = st.session_state.orchestrator.get_rag_indexer()
    temp_dir = tempfile.mkdtemp()
    file_paths = []
    
    try:
        with st.spinner(f"Processing {len(files)} document(s)..."):
            for file in files:
                temp_path = os.path.join(temp_dir, file.name)
                with open(temp_path, 'wb') as f:
                    f.write(file.getbuffer())
                file_paths.append(temp_path)
            
            results = rag_indexer.index_documents(file_paths)
        
        _handle_indexing_results(results)
        
    except Exception as e:
        st.error(f"❌ Indexing error: {str(e)}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _handle_indexing_results(results: dict):
    """Process and display indexing results."""
    for filename in results.get("success", []):
        st.session_state.indexed_files.add(filename)
    
    if results.get("success"):
        st.session_state.indexing_status = (
            f"✅ Indexed {len(results['success'])} file(s), "
            f"{results['total_chunks']} chunks"
        )
    
    for fail in results.get("failed", []):
        st.warning(f"⚠️ Failed: {fail['file']} - {fail['error']}")
    
    if results.get("skipped"):
        st.info(f"⏭️ Skipped {len(results['skipped'])} already indexed file(s)")


def build_knowledge_graph():
    """Build GraphRAG knowledge graph with progress display."""
    rag_indexer = st.session_state.orchestrator.get_rag_indexer()
    
    try:
        with st.spinner("Building knowledge graph..."):
            success = rag_indexer.build_graph_index()
        
        if success:
            st.success("✅ Knowledge graph built successfully!")
        else:
            st.warning("⚠️ Graph building completed with warnings")
    except Exception as e:
        st.error(f"❌ Graph building error: {str(e)}")


# =============================================================================
# SRS Generation Functions
# =============================================================================

def generate_srs(focus_input: str):
    """Generate SRS document from conversation context."""
    if not st.session_state.messages:
        st.warning("⚠️ Please have a conversation first to provide context.")
        return
    
    with st.spinner("Generating SRS document..."):
        try:
            role_prompt = select_role_prompt(st.session_state.selected_role)
            formatted_role = role_prompt.format(
                focus=focus_input or "General requirements",
                history="See conversation history below"
            )
            
            memory = st.session_state.orchestrator.get_memory()
            history = memory.get_summary()
            focus = focus_input if focus_input else "Based on conversation context"
            
            result = st.session_state.requirements_generator.invoke(
                role_prompt=formatted_role,
                history=history,
                focus=focus
            )
            
            st.session_state.generated_srs = result
            st.session_state.srs_markdown = RequirementsGenerator.to_markdown(result)
            
            entities = RequirementsGenerator.extract_entities_for_storage(result)
            for entity in entities:
                memory.store_entity(entity["text"], entity["metadata"])
            
            st.success(f"✅ SRS generated! Stored {len(entities)} requirements.")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error generating SRS: {str(e)}")


# =============================================================================
# Mermaid Diagram Rendering
# =============================================================================

def render_mermaid(mermaid_code: str):
    """Render a Mermaid diagram using HTML/JS component."""
    # Extract code from markdown code block if present
    code = mermaid_code
    if "```mermaid" in code:
        code = code.replace("```mermaid", "").replace("```", "").strip()
    
    html_content = f"""
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad:true, theme:'default'}});</script>
    <div class="mermaid">
    {code}
    </div>
    """
    components.html(html_content, height=400, scrolling=True)


def display_chain_of_thought(chain_of_thought: list):
    """Display chain of thought in dev mode."""
    if DEV_MODE and chain_of_thought:
        with st.expander("🧠 Chain of Thought (Dev Mode)", expanded=False):
            for thought in chain_of_thought:
                st.text(thought)
            st.markdown(f"[View in LangSmith]({LANGSMITH_PROJECT_URL})")


# =============================================================================
# Chat Processing Functions
# =============================================================================

def process_user_message(prompt: str):
    """Process user message and generate response based on intent."""
    has_files = len(st.session_state.uploaded_files) > 0
    intent = st.session_state.orchestrator.detect_intent(
        prompt, 
        st.session_state.selected_role,
        has_files
    )
    
    if intent == "general_chat":
        _handle_general_chat(prompt)
    elif intent == "deep_research":
        _handle_deep_research(prompt)
    else:
        _handle_standard_processing(prompt)


def _handle_general_chat(prompt: str):
    """Handle general chat with streaming response."""
    response_placeholder = st.empty()
    full_response = ""
    
    for chunk in st.session_state.orchestrator.stream_general_chat(prompt):
        full_response += chunk
        response_placeholder.markdown(full_response + "▌")
    
    response_placeholder.markdown(full_response)
    st.session_state.messages.append({"role": "assistant", "content": full_response})


def _handle_deep_research(prompt: str):
    """Handle deep research with PDF report generation."""
    with st.spinner("🔬 Conducting deep research... This may take a few minutes."):
        result = st.session_state.orchestrator.process(
            user_input=prompt,
            role=st.session_state.selected_role,
            uploaded_files=st.session_state.uploaded_files
        )
        
        st.markdown(result["response"])
        st.session_state.messages.append({"role": "assistant", "content": result["response"]})
        
        # Display chain of thought in dev mode
        display_chain_of_thought(result.get("chain_of_thought", []))
        st.session_state.last_chain_of_thought = result.get("chain_of_thought", [])
        
        pdf_path = result.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="📥 Download Research Report (PDF)",
                    data=pdf_file.read(),
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                    type="primary"
                )


def _handle_standard_processing(prompt: str):
    """Handle standard RAG/requirements processing."""
    with st.spinner("Processing..."):
        result = st.session_state.orchestrator.process(
            user_input=prompt,
            role=st.session_state.selected_role,
            uploaded_files=st.session_state.uploaded_files
        )
        
        st.markdown(result["response"])
        st.session_state.messages.append({"role": "assistant", "content": result["response"]})
        
        # Display chain of thought in dev mode
        display_chain_of_thought(result.get("chain_of_thought", []))
        st.session_state.last_chain_of_thought = result.get("chain_of_thought", [])
        
        # Render Mermaid diagram if present
        mermaid_chart = result.get("mermaid_chart", "")
        if mermaid_chart:
            st.subheader("📊 Generated Diagram")
            render_mermaid(mermaid_chart)


# =============================================================================
# Sidebar Components
# =============================================================================

def render_sidebar():
    """Render the sidebar with all configuration options."""
    with st.sidebar:
        st.header("⚙️ Configuration")
        _render_role_selection()
        st.divider()
        _render_document_upload()
        st.divider()
        _render_chat_controls()
        st.divider()
        _render_srs_generation()
        st.divider()
        _render_memory_stats()
        st.divider()
        _render_tips()


def _render_role_selection():
    """Render role selection dropdown."""
    st.subheader("Role Selection")
    st.session_state.selected_role = st.selectbox(
        "Select your role:",
        USER_ROLES,
        index=USER_ROLES.index(st.session_state.selected_role)
    )


def _render_document_upload():
    """Render document upload and indexing section."""
    st.subheader("📄 Document Upload & Indexing")
    
    uploaded_files = st.file_uploader(
        "Upload documents for RAG Q&A",
        type=SUPPORTED_FILE_TYPES,
        accept_multiple_files=True,
        help="Supported: PDF, Word, PPT, Excel, TXT, Images"
    )
    
    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files
        new_files = [f for f in uploaded_files if f.name not in st.session_state.indexed_files]
        
        if new_files:
            st.info(f"📁 {len(new_files)} new file(s) ready to index")
            if st.button("🔍 Index Documents", type="primary", use_container_width=True):
                index_documents(new_files)
        else:
            st.success(f"✅ {len(uploaded_files)} file(s) indexed")
        
        if st.session_state.indexing_status:
            st.success(st.session_state.indexing_status)
            st.session_state.indexing_status = None
        
        with st.expander("View uploaded files", expanded=False):
            for file in uploaded_files:
                status = "✅" if file.name in st.session_state.indexed_files else "⏳"
                st.text(f"{status} {file.name}")
    
    _render_index_stats()


def _render_index_stats():
    """Render RAG index statistics and controls."""
    rag_indexer = st.session_state.orchestrator.get_rag_indexer()
    index_stats = rag_indexer.get_index_stats()
    
    if index_stats.get("indexed_files", 0) > 0:
        st.caption("📊 **RAG Index Stats:**")
        st.caption(f"- Indexed files: {index_stats['indexed_files']}")
        st.caption(f"- Total chunks: {index_stats['total_chunks']}")
        st.caption(f"- Graph ready: {'Yes' if index_stats.get('has_graph') else 'No'}")
        
        col_graph, col_clear = st.columns(2)
        with col_graph:
            if not index_stats.get('has_graph'):
                if st.button("🔗 Build Graph", use_container_width=True):
                    build_knowledge_graph()
        with col_clear:
            if st.button("🗑️ Clear Index", use_container_width=True):
                st.session_state.orchestrator.clear_rag_index()
                st.session_state.indexed_files = set()
                st.success("Index cleared!")
                st.rerun()


def _render_chat_controls():
    """Render chat and memory control buttons."""
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()
    with col2:
        if st.button("🧹 Clear Memory"):
            st.session_state.orchestrator.clear_memory()
            st.success("Memory cleared!")
            st.rerun()


def _render_srs_generation():
    """Render SRS generation section."""
    st.subheader("📝 SRS Generation")
    
    focus_input = st.text_area(
        "Focus area (optional):",
        placeholder="e.g., User authentication, Payment processing...",
        height=80
    )
    
    if st.button("📄 Generate SRS", type="primary", use_container_width=True):
        generate_srs(focus_input)
    
    if st.session_state.srs_markdown:
        st.download_button(
            label="⬇️ Download SRS (Markdown)",
            data=st.session_state.srs_markdown,
            file_name="srs.md",
            mime="text/markdown",
            use_container_width=True
        )


def _render_memory_stats():
    """Render memory statistics."""
    memory = st.session_state.orchestrator.get_memory()
    entity_count = len(memory.entity_store)
    st.caption("📊 **Memory Stats:**")
    st.caption(f"- Stored entities: {entity_count}")


def _render_tips():
    """Render usage tips."""
    st.caption("💡 **Tips:**")
    st.caption("- Ask questions about uploaded documents")
    st.caption("- Request requirements generation")
    st.caption("- Use Deep Research for domain exploration")
    st.caption("- Ask for 'diagram' or 'chart' to visualize requirements")
    
    # Dev mode indicator
    if DEV_MODE:
        st.divider()
        st.caption("🔧 **Dev Mode Active**")
        st.caption(f"[LangSmith Traces]({LANGSMITH_PROJECT_URL})")


# =============================================================================
# Main Chat Interface
# =============================================================================

def render_chat_interface():
    """Render the main chat interface."""
    st.subheader(f"💬 Chat - {st.session_state.selected_role}")
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("Type your message here..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            try:
                process_user_message(prompt)
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})


# =============================================================================
# Main Application Entry Point
# =============================================================================

def main():
    """Main application entry point."""
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🤖",
        layout="wide"
    )
    
    st.title(APP_TITLE)
    initialize_session_state()
    render_sidebar()
    render_chat_interface()


if __name__ == "__main__":
    main()
