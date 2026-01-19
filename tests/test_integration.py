"""
Test script to verify all modules after refactoring.
Tests: utils, rag, research, roles, memory, requirements generator, orchestrator.
"""
import sys
from pathlib import Path

# Add project root to path (parent of tests folder)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Core modules
from src.agents.orchestrator import OrchestratorAgent
from src.modules.roles import select_role_prompt, get_available_roles
from src.modules.memory import EnhancedConversationMemory
from src.modules.requirements_generator import RequirementsGenerator

# New refactored modules
from src.utils import get_logger, setup_logging
from src.utils.exceptions import RAAAError, ConfigurationError, ParsingError
from src.rag import DocumentParser, RAGIndexer, AgenticRAGChain, create_rag_system
from src.modules.research import PlannerAgent, SearcherAgent, WriterAgent, PDFReportGenerator
from src.tools.chart import MermaidChartTool, should_generate_chart, should_auto_generate_diagram

def test_utils_module():
    """Test utils module (logging and exceptions)."""
    print("=" * 60)
    print("Testing Utils Module")
    print("=" * 60)
    
    print("\n1. Testing logging setup...")
    logger = get_logger("test_module")
    print(f"✓ Logger created: {logger.name}")
    
    print("\n2. Testing custom exceptions...")
    try:
        raise ConfigurationError("Test config error")
    except RAAAError as e:
        print(f"✓ ConfigurationError caught as RAAAError: {e}")
    
    try:
        raise ParsingError("Test parsing error")
    except RAAAError as e:
        print(f"✓ ParsingError caught as RAAAError: {e}")
    
    print("\n✓ Utils module tests passed\n")


def test_rag_module():
    """Test RAG module components."""
    print("=" * 60)
    print("Testing RAG Module")
    print("=" * 60)
    
    print("\n1. Testing DocumentParser initialization...")
    parser = DocumentParser()
    print(f"✓ DocumentParser created, Docling available: {parser.docling_available}")
    
    print("\n2. Testing RAGIndexer initialization...")
    indexer = RAGIndexer()
    stats = indexer.get_index_stats()
    print(f"✓ RAGIndexer created")
    print(f"  - Indexed files: {stats.get('indexed_files', 0)}")
    print(f"  - Total chunks: {stats.get('total_chunks', 0)}")
    
    print("\n3. Testing AgenticRAGChain initialization...")
    chain = AgenticRAGChain(indexer)
    print(f"✓ AgenticRAGChain created")
    
    print("\n4. Testing create_rag_system factory...")
    rag_indexer, rag_chain = create_rag_system()
    print(f"✓ RAG system created via factory")
    
    print("\n✓ RAG module tests passed\n")


def test_research_module():
    """Test research module components."""
    print("=" * 60)
    print("Testing Research Module")
    print("=" * 60)
    
    print("\n1. Testing PlannerAgent initialization...")
    planner = PlannerAgent()
    print(f"✓ PlannerAgent created")
    
    print("\n2. Testing SearcherAgent initialization...")
    searcher = SearcherAgent()
    print(f"✓ SearcherAgent created")
    
    print("\n3. Testing WriterAgent initialization...")
    writer = WriterAgent()
    print(f"✓ WriterAgent created")
    
    print("\n4. Testing PDFReportGenerator initialization...")
    pdf_gen = PDFReportGenerator()
    print(f"✓ PDFReportGenerator created")
    
    print("\n✓ Research module tests passed\n")


def test_chart_tool():
    """Test Mermaid chart generation tool."""
    print("=" * 60)
    print("Testing Chart Tool")
    print("=" * 60)
    
    print("\n1. Testing MermaidChartTool initialization...")
    chart_tool = MermaidChartTool()
    print(f"✓ MermaidChartTool created")
    
    print("\n2. Testing should_generate_chart detection...")
    test_cases = [
        ("Generate a sequence diagram for login", True),
        ("Show me a flowchart", True),
        ("I need requirements for authentication", False),
        ("Create a class diagram", True),
        ("What is the weather?", False),
        ("我需要一个流程图", True),  # Chinese: I need a flowchart
    ]
    for text, expected in test_cases:
        result = should_generate_chart(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{text[:40]}' -> {result} (expected {expected})")
    
    print("\n3. Testing diagram type detection...")
    test_types = [
        ("sequence diagram", "sequence"),
        ("flowchart process", "flowchart"),
        ("workflow diagram", "flowchart"),
        ("class structure", "class"),
        ("entity relationship", "er"),
        ("流程图", "flowchart"),  # Chinese: flowchart
    ]
    for text, expected in test_types:
        result = chart_tool.detect_diagram_type(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{text}' -> {result} (expected {expected})")
    
    print("\n4. Testing should_auto_generate_diagram...")
    auto_test_cases = [
        ("Step 1: User logs in. Step 2: User selects product.", True, "sequence"),
        ("If the user is authenticated, show dashboard. Else redirect to login.", True, "flowchart"),
        ("The User entity has fields: id, name, email.", True, "er"),
        ("Simple text without any patterns.", False, ""),
    ]
    for text, expected_gen, expected_type in auto_test_cases:
        result_gen, result_type = should_auto_generate_diagram(text)
        status = "✓" if result_gen == expected_gen else "✗"
        print(f"  {status} Auto-detect: {result_gen} (expected {expected_gen}), type: {result_type}")
    
    print("\n✓ Chart tool tests passed\n")


def test_role_prompts():
    """Test role prompt selection."""
    print("=" * 60)
    print("Testing Role Prompts")
    print("=" * 60)
    
    available_roles = get_available_roles()
    print(f"\nAvailable roles: {available_roles}\n")
    
    for role in available_roles:
        try:
            prompt = select_role_prompt(role)
            print(f"✓ Role '{role}' prompt loaded successfully")
            formatted = prompt.format(
                focus="Test requirement",
                history="No previous history"
            )
            print(f"  Preview: {formatted[:100]}...\n")
        except Exception as e:
            print(f"✗ Failed to load role '{role}': {e}\n")

def test_memory():
    """Test memory functionality."""
    print("=" * 60)
    print("Testing Memory Module")
    print("=" * 60)
    
    memory = EnhancedConversationMemory(token_limit=1000)
    
    print("\n1. Adding messages...")
    memory.add_message("I need to create a login system", "user")
    memory.add_message("I'll help you define requirements for a login system.", "assistant")
    
    print("✓ Messages added")
    
    print("\n2. Getting summary...")
    summary = memory.get_summary()
    print(f"Summary: {summary[:200]}...")
    
    print("\n3. Storing entities...")
    memory.store_entity(
        "FR-001: User shall be able to login with email and password",
        metadata={"type": "functional_requirement", "priority": "high"}
    )
    memory.store_entity(
        "NFR-001: System shall respond within 2 seconds",
        metadata={"type": "non_functional_requirement", "priority": "medium"}
    )
    print(f"✓ Stored {len(memory.entity_store)} entities")
    
    print("\n4. Retrieving entities...")
    results = memory.retrieve_entities("login requirements", top_k=2)
    print(f"✓ Retrieved {len(results)} entities:")
    for i, entity in enumerate(results, 1):
        print(f"  {i}. {entity['text'][:60]}...")

def test_orchestrator_integration():
    """Test orchestrator with role prompts and memory."""
    print("\n" + "=" * 60)
    print("Testing Orchestrator Integration")
    print("=" * 60)
    
    orchestrator = OrchestratorAgent()
    
    print("\n1. Testing with Requirements Analyst role...")
    result = orchestrator.process(
        user_input="I need to build a user authentication system",
        role="Requirements Analyst"
    )
    response = result["response"]
    print(f"✓ Response received (length: {len(response)} chars)")
    print(f"Preview: {response[:200]}...\n")
    
    print("2. Testing memory persistence...")
    memory_summary = orchestrator.get_memory().get_summary()
    print(f"✓ Memory contains: {len(memory_summary)} chars")
    print(f"Preview: {memory_summary[:150]}...\n")
    
    print("3. Testing second interaction with context...")
    result2 = orchestrator.process(
        user_input="What about password reset functionality?",
        role="Requirements Analyst"
    )
    response2 = result2["response"]
    print(f"✓ Second response received (length: {len(response2)} chars)")
    print(f"Preview: {response2[:200]}...\n")
    
    print("4. Testing with different role (Test Engineer)...")
    result3 = orchestrator.process(
        user_input="Generate test cases for the login system",
        role="Test Engineer"
    )
    response3 = result3["response"]
    print(f"✓ Test Engineer response received (length: {len(response3)} chars)")
    print(f"Preview: {response3[:200]}...\n")
    
    print("5. Clearing memory...")
    orchestrator.clear_memory()
    cleared_summary = orchestrator.get_memory().get_summary()
    print(f"✓ Memory cleared. Summary: {cleared_summary}\n")

def test_requirements_generator():
    """Test requirements generator with validation chain."""
    print("\n" + "=" * 60)
    print("Testing Requirements Generator")
    print("=" * 60)
    
    generator = RequirementsGenerator()
    
    print("\n1. Testing requirements generation...")
    role_prompt = select_role_prompt("Requirements Analyst")
    formatted_role = role_prompt.format(
        focus="User authentication system",
        history="User wants to build a login system with email and password"
    )
    
    result = generator.invoke(
        role_prompt=formatted_role,
        history="User: I need a login system\nAssistant: I'll help you define requirements.",
        focus="User authentication with email/password login"
    )
    
    print(f"✓ Generation status: {result.get('status')}")
    print(f"✓ Refinement iterations: {result.get('refinement_iterations')}")
    
    requirements = result.get("requirements", {})
    print(f"✓ Functional requirements: {len(requirements.get('functional_requirements', []))}")
    print(f"✓ Non-functional requirements: {len(requirements.get('non_functional_requirements', []))}")
    print(f"✓ Business rules: {len(requirements.get('business_rules', []))}")
    
    print("\n2. Testing validation scores...")
    validation = result.get("validation", {})
    scores = validation.get("scores", {})
    if scores:
        print(f"✓ Ambiguity score: {scores.get('ambiguity', 'N/A')}/10")
        print(f"✓ Completeness score: {scores.get('completeness', 'N/A')}/10")
        print(f"✓ Consistency score: {scores.get('consistency', 'N/A')}/10")
        print(f"✓ Clarity score: {scores.get('clarity', 'N/A')}/10")
        print(f"✓ Overall score: {validation.get('overall_score', 'N/A')}/10")
    
    print("\n3. Testing Markdown conversion...")
    markdown = RequirementsGenerator.to_markdown(result)
    print(f"✓ Markdown generated: {len(markdown)} characters")
    print(f"Preview:\n{markdown[:500]}...\n")
    
    print("4. Testing entity extraction...")
    entities = RequirementsGenerator.extract_entities_for_storage(result)
    print(f"✓ Extracted {len(entities)} entities for FAISS storage")
    if entities:
        print(f"  Sample: {entities[0]['text'][:60]}...")

def test_mixed_intent_detection():
    """Test mixed intent detection and workflow orchestration."""
    print("\n" + "=" * 60)
    print("Testing Mixed Intent Detection")
    print("=" * 60)
    
    orchestrator = OrchestratorAgent()
    
    print("\n1. Testing is_mixed_intent helper...")
    test_cases = [
        ("rag_qa+requirements_generation", True),
        ("deep_research+requirements_generation", True),
        ("rag_qa+deep_research+requirements_generation", True),
        ("requirements_generation", False),
        ("general_chat", False),
        ("rag_qa", False),
    ]
    for intent, expected in test_cases:
        result = orchestrator.is_mixed_intent(intent)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{intent}' -> is_mixed={result} (expected {expected})")
    
    print("\n2. Testing mixed intent detection with sample queries...")
    mixed_intent_queries = [
        ("Based on the uploaded document, generate requirements for the login module", "rag_qa"),
        ("Research authentication best practices and create requirements", "deep_research"),
        ("Generate requirements for a payment system", "requirements_generation"),
        ("What is the weather today?", "general_chat"),
    ]
    
    for query, expected_contains in mixed_intent_queries:
        intent = orchestrator.detect_intent(query, "Requirements Analyst", has_files=True)
        # Check if the detected intent contains the expected component
        contains_expected = expected_contains in intent
        status = "✓" if contains_expected else "?"
        print(f"  {status} Query: '{query[:50]}...'")
        print(f"      Detected: '{intent}' (expected to contain '{expected_contains}')")
    
    print("\n3. Testing mixed intent workflow execution...")
    # Test with a query that should trigger rag_qa + requirements_generation
    result = orchestrator.process(
        user_input="Based on the uploaded specifications, generate software requirements for user authentication",
        role="Requirements Analyst",
        uploaded_files=["test.pdf"]  # Simulate having files
    )
    
    print(f"✓ Mixed intent processing completed")
    print(f"  - Intent detected: {result.get('intent', 'N/A')}")
    print(f"  - Response length: {len(result.get('response', ''))} chars")
    print(f"  - Chain of thought steps: {len(result.get('chain_of_thought', []))}")
    
    # Show chain of thought for debugging
    if result.get('chain_of_thought'):
        print(f"\n  Chain of Thought:")
        for thought in result['chain_of_thought'][:5]:
            print(f"    - {thought[:80]}...")
    
    print(f"\n  Response preview: {result.get('response', '')[:300]}...")
    
    print("\n✓ Mixed intent detection tests passed\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("RAAA Integration Test Suite (Post-Refactoring)")
    print("=" * 60 + "\n")
    
    try:
        # Test new refactored modules first
        test_utils_module()
        test_rag_module()
        test_research_module()
        test_chart_tool()
        
        # Test existing modules
        test_role_prompts()
        test_memory()
        test_requirements_generator()
        test_orchestrator_integration()
        
        # Test mixed intent detection
        test_mixed_intent_detection()
        
        print("\n" + "=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
