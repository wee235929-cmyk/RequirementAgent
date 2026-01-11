# Requirements Analysis Agent Assistant (RAAA)

A multi-agent AI system for requirements engineering, built with LangChain, LangGraph, and Streamlit.

## Overview

RAAA is an intelligent assistant that helps software teams with requirements analysis, generation, and validation. It combines multiple AI agents with RAG (Retrieval-Augmented Generation) capabilities to provide context-aware requirements engineering support.

## Features

- **Multi-Role Support**: Switch between Requirements Analyst, Software Architect, Software Developer, and Test Engineer perspectives
- **RAG-Powered Q&A**: Upload documents (PDF, Word, Excel, PPT, TXT, Images) and ask questions with context-aware responses
- **GraphRAG Integration**: Build knowledge graphs from documents for enhanced entity and relationship extraction
- **Requirements Generation**: Generate structured SRS documents with validation scoring
- **Deep Research**: Conduct comprehensive research on topics with automated PDF report generation
- **Conversation Memory**: Maintains context across interactions with FAISS-based entity storage

## Project Structure

```
RequirementAgent/
├── app.py                      # Streamlit application entry point
├── requirements.txt            # Python dependencies
├── test_integration.py         # Integration test suite
├── doc/
│   └── README.md               # This file
└── src/
    ├── config.py               # Centralized configuration
    ├── agents/
    │   └── orchestrator.py     # Main orchestration agent
    ├── modules/
    │   ├── memory.py           # Conversation memory with FAISS
    │   ├── requirements_generator.py  # SRS generation
    │   ├── roles.py            # Role-based prompts
    │   └── research/           # Deep research module
    │       ├── agents.py       # Planner, Searcher, Writer agents
    │       ├── pdf_generator.py # PDF report generation
    │       └── workflow.py     # LangGraph workflow
    ├── rag/                    # RAG module
    │   ├── parser.py           # Document parsing (Docling + fallbacks)
    │   ├── indexer.py          # FAISS vector store + GraphRAG
    │   └── chain.py            # Agentic RAG chain
    └── utils/                  # Shared utilities
        ├── logging_config.py   # Centralized logging
        └── exceptions.py       # Custom exception classes
```

## Installation

### Prerequisites

- Python 3.10+
- DeepSeek API key (or compatible OpenAI-style API)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/RequirementAgent.git
cd RequirementAgent
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your API credentials:
```env
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## Usage

### Running the Application

```bash
streamlit run app.py
```

The application will open in your browser at `http://localhost:8501`.

### Running Tests

```bash
python test_integration.py
```

## Key Components

### Orchestrator Agent

The central agent that:
- Detects user intent (general chat, RAG Q&A, requirements generation, deep research)
- Routes requests to appropriate handlers
- Maintains conversation memory and context

### RAG System

- **DocumentParser**: Parses various document formats using Docling with fallback loaders
- **RAGIndexer**: Manages FAISS vector store and GraphRAG knowledge graph
- **AgenticRAGChain**: Performs query restatement, retrieval, and conditional web search

### Research Workflow

A LangGraph-based workflow with:
- **PlannerAgent**: Breaks down research topics into subtasks
- **SearcherAgent**: Executes web searches using DuckDuckGo
- **WriterAgent**: Synthesizes findings into comprehensive reports
- **PDFReportGenerator**: Generates downloadable PDF reports

### Requirements Generator

Generates structured SRS documents with:
- Functional and non-functional requirements
- Business rules and constraints
- Quality validation scores (ambiguity, completeness, consistency, clarity)

## Configuration

All configuration is centralized in `src/config.py`:

| Setting | Description |
|---------|-------------|
| `LLM_CONFIG` | LLM model, API key, base URL, temperature |
| `EMBEDDING_CONFIG` | Sentence transformer model settings |
| `RAG_CONFIG` | Chunk size, overlap, similarity threshold |
| `USER_ROLES` | Available user roles |
| `SYSTEM_PROMPTS` | Prompt templates for various tasks |

## Dependencies

Key libraries used:
- **LangChain & LangGraph**: Agent orchestration and workflows
- **Streamlit**: Web interface
- **FAISS**: Vector similarity search
- **Docling**: Document parsing
- **Sentence Transformers**: Text embeddings
- **ReportLab**: PDF generation

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `python test_integration.py`
5. Submit a pull request
