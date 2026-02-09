import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_CONFIG

class RequirementsOutput(BaseModel):
    """Schema for structured requirements output."""
    functional_requirements: list[str] = Field(description="List of functional requirements")
    non_functional_requirements: list[str] = Field(description="List of non-functional requirements")
    business_rules: list[str] = Field(description="List of business rules")
    use_cases: list[str] = Field(default=[], description="List of use cases")
    assumptions: list[str] = Field(default=[], description="List of assumptions")

class QualityScores(BaseModel):
    """Schema for quality assessment scores."""
    ambiguity: int = Field(description="Score for ambiguity (1-10, higher is better)")
    completeness: int = Field(description="Score for completeness (1-10)")
    consistency: int = Field(description="Score for consistency (1-10)")
    clarity: int = Field(description="Score for clarity (1-10)")

class ValidationOutput(BaseModel):
    """Schema for validation output."""
    scores: QualityScores = Field(description="Quality scores")
    suggestions: list[str] = Field(description="Improvement suggestions")
    overall_score: float = Field(description="Overall quality score")

class RequirementsGenerator:
    """
    LangChain-based requirements generator with validation chain.
    Compatible with LangChain 1.x using LCEL (LangChain Expression Language).
    """
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=LLM_CONFIG["temperature"]
        )
        
        self.validation_llm = ChatOpenAI(
            model=LLM_CONFIG["model"],
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
            temperature=0.3
        )
        
        self.requirements_parser = JsonOutputParser(pydantic_object=RequirementsOutput)
        self.validation_parser = JsonOutputParser(pydantic_object=ValidationOutput)
        
        self.generation_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert software requirements engineer. Generate comprehensive software requirements based on the following role context, conversation history, and focus area.

Ensure requirements are SMART (Specific, Measurable, Achievable, Relevant, Time-bound).
Check for ambiguity or inconsistencies and annotate them with [AMBIGUOUS] or [NEEDS CLARIFICATION] tags.

Role Context:
{role_prompt}

Conversation History:
{history}

Focus Area:
{focus}

{format_instructions}

Generate detailed, professional requirements that conform to ISO 29148 and IEEE-830 standards."""),
            ("human", "Generate the software requirements document based on the above context.")
        ])
        
        self.validation_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a quality control expert for software requirements. Rate the following requirements on a scale of 1-10 for each criterion:

1. Ambiguity (10 = no ambiguity, 1 = highly ambiguous)
2. Completeness (10 = fully complete, 1 = missing critical elements)
3. Consistency (10 = fully consistent, 1 = many contradictions)
4. Clarity (10 = crystal clear, 1 = very unclear)

If any score is below 7, provide specific improvement suggestions.
Calculate the overall_score as the average of all scores.

Requirements to evaluate:
{requirements}

{format_instructions}"""),
            ("human", "Evaluate the requirements and provide scores and suggestions.")
        ])
        
        self.refinement_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert software requirements engineer. Refine and improve the following requirements based on the quality assessment feedback.

Original Requirements:
{original_requirements}

Quality Assessment:
- Scores: {scores}
- Suggestions: {suggestions}

Improve the requirements by addressing the suggestions while maintaining the original intent.
Ensure all improvements make the requirements more SMART compliant.

{format_instructions}"""),
            ("human", "Refine the requirements based on the feedback.")
        ])
        
        self.generation_chain = (
            self.generation_prompt.partial(
                format_instructions=self.requirements_parser.get_format_instructions()
            ) 
            | self.llm 
            | self.requirements_parser
        )
        
        self.validation_chain = (
            self.validation_prompt.partial(
                format_instructions=self.validation_parser.get_format_instructions()
            )
            | self.validation_llm
            | self.validation_parser
        )
        
        self.refinement_chain = (
            self.refinement_prompt.partial(
                format_instructions=self.requirements_parser.get_format_instructions()
            )
            | self.llm
            | self.requirements_parser
        )
    
    def invoke(
        self,
        role_prompt: str,
        history: str,
        focus: str,
        max_refinement_iterations: int = 2,
        quality_threshold: float = 7.0
    ) -> Dict[str, Any]:
        """
        Generate requirements with validation and optional refinement.
        
        Args:
            role_prompt: The role-specific prompt context
            history: Conversation history from memory
            focus: The focus area for requirements
            max_refinement_iterations: Maximum refinement attempts
            quality_threshold: Minimum acceptable quality score
            
        Returns:
            Dictionary containing requirements, validation scores, and metadata
        """
        try:
            requirements = self.generation_chain.invoke({
                "role_prompt": role_prompt,
                "history": history,
                "focus": focus
            })
            
            validation = self.validation_chain.invoke({
                "requirements": json.dumps(requirements, indent=2)
            })
            
            iteration = 0
            while (validation.get("overall_score", 10) < quality_threshold 
                   and iteration < max_refinement_iterations):
                
                requirements = self.refinement_chain.invoke({
                    "original_requirements": json.dumps(requirements, indent=2),
                    "scores": json.dumps(validation.get("scores", {})),
                    "suggestions": json.dumps(validation.get("suggestions", []))
                })
                
                validation = self.validation_chain.invoke({
                    "requirements": json.dumps(requirements, indent=2)
                })
                
                iteration += 1
            
            return {
                "requirements": requirements,
                "validation": validation,
                "refinement_iterations": iteration,
                "status": "success"
            }
            
        except Exception as e:
            return {
                "requirements": self._get_fallback_requirements(),
                "validation": {"scores": {}, "suggestions": [str(e)], "overall_score": 0},
                "refinement_iterations": 0,
                "status": "error",
                "error": str(e)
            }
    
    async def ainvoke(
        self,
        role_prompt: str,
        history: str,
        focus: str,
        max_refinement_iterations: int = 2,
        quality_threshold: float = 7.0
    ) -> Dict[str, Any]:
        """
        Async version of invoke for non-blocking calls.
        """
        try:
            requirements = await self.generation_chain.ainvoke({
                "role_prompt": role_prompt,
                "history": history,
                "focus": focus
            })
            
            validation = await self.validation_chain.ainvoke({
                "requirements": json.dumps(requirements, indent=2)
            })
            
            iteration = 0
            while (validation.get("overall_score", 10) < quality_threshold 
                   and iteration < max_refinement_iterations):
                
                requirements = await self.refinement_chain.ainvoke({
                    "original_requirements": json.dumps(requirements, indent=2),
                    "scores": json.dumps(validation.get("scores", {})),
                    "suggestions": json.dumps(validation.get("suggestions", []))
                })
                
                validation = await self.validation_chain.ainvoke({
                    "requirements": json.dumps(requirements, indent=2)
                })
                
                iteration += 1
            
            return {
                "requirements": requirements,
                "validation": validation,
                "refinement_iterations": iteration,
                "status": "success"
            }
            
        except Exception as e:
            return {
                "requirements": self._get_fallback_requirements(),
                "validation": {"scores": {}, "suggestions": [str(e)], "overall_score": 0},
                "refinement_iterations": 0,
                "status": "error",
                "error": str(e)
            }
    
    def _get_fallback_requirements(self) -> Dict[str, Any]:
        """Return empty requirements structure as fallback."""
        return {
            "functional_requirements": [],
            "non_functional_requirements": [],
            "business_rules": [],
            "use_cases": [],
            "assumptions": []
        }
    
    @staticmethod
    def to_markdown(result: Dict[str, Any]) -> str:
        """
        Convert requirements result to Markdown format.
        
        Args:
            result: The result from invoke() method
            
        Returns:
            Markdown formatted string
        """
        requirements = result.get("requirements", {})
        validation = result.get("validation", {})
        
        md_lines = [
            "# Software Requirements Specification (SRS)",
            "",
            "## Document Information",
            f"- **Generation Status**: {result.get('status', 'unknown')}",
            f"- **Refinement Iterations**: {result.get('refinement_iterations', 0)}",
            ""
        ]
        
        if validation.get("scores"):
            scores = validation["scores"]
            md_lines.extend([
                "## Quality Assessment",
                f"- **Ambiguity Score**: {scores.get('ambiguity', 'N/A')}/10",
                f"- **Completeness Score**: {scores.get('completeness', 'N/A')}/10",
                f"- **Consistency Score**: {scores.get('consistency', 'N/A')}/10",
                f"- **Clarity Score**: {scores.get('clarity', 'N/A')}/10",
                f"- **Overall Score**: {validation.get('overall_score', 'N/A')}/10",
                ""
            ])
        
        fr_list = requirements.get("functional_requirements", [])
        if fr_list:
            md_lines.extend([
                "## 1. Functional Requirements",
                ""
            ])
            for i, req in enumerate(fr_list, 1):
                md_lines.append(f"### FR-{i:03d}")
                md_lines.append(f"{req}")
                md_lines.append("")
        
        nfr_list = requirements.get("non_functional_requirements", [])
        if nfr_list:
            md_lines.extend([
                "## 2. Non-Functional Requirements",
                ""
            ])
            for i, req in enumerate(nfr_list, 1):
                md_lines.append(f"### NFR-{i:03d}")
                md_lines.append(f"{req}")
                md_lines.append("")
        
        br_list = requirements.get("business_rules", [])
        if br_list:
            md_lines.extend([
                "## 3. Business Rules",
                ""
            ])
            for i, rule in enumerate(br_list, 1):
                md_lines.append(f"### BR-{i:03d}")
                md_lines.append(f"{rule}")
                md_lines.append("")
        
        uc_list = requirements.get("use_cases", [])
        if uc_list:
            md_lines.extend([
                "## 4. Use Cases",
                ""
            ])
            for i, uc in enumerate(uc_list, 1):
                md_lines.append(f"### UC-{i:03d}")
                md_lines.append(f"{uc}")
                md_lines.append("")
        
        assumptions = requirements.get("assumptions", [])
        if assumptions:
            md_lines.extend([
                "## 5. Assumptions",
                ""
            ])
            for assumption in assumptions:
                md_lines.append(f"- {assumption}")
            md_lines.append("")
        
        suggestions = validation.get("suggestions", [])
        if suggestions:
            md_lines.extend([
                "## Quality Improvement Suggestions",
                ""
            ])
            for suggestion in suggestions:
                md_lines.append(f"- {suggestion}")
            md_lines.append("")
        
        md_lines.extend([
            "---",
            "*Generated by Requirements Analysis Agent Assistant (RAAA)*"
        ])
        
        return "\n".join(md_lines)
    
    @staticmethod
    def extract_entities_for_storage(result: Dict[str, Any]) -> list[Dict[str, Any]]:
        """
        Extract key entities from requirements for FAISS storage.
        
        Args:
            result: The result from invoke() method
            
        Returns:
            List of entities with text and metadata
        """
        entities = []
        requirements = result.get("requirements", {})
        
        for i, req in enumerate(requirements.get("functional_requirements", []), 1):
            entities.append({
                "text": f"FR-{i:03d}: {req}",
                "metadata": {"type": "functional_requirement", "id": f"FR-{i:03d}"}
            })
        
        for i, req in enumerate(requirements.get("non_functional_requirements", []), 1):
            entities.append({
                "text": f"NFR-{i:03d}: {req}",
                "metadata": {"type": "non_functional_requirement", "id": f"NFR-{i:03d}"}
            })
        
        for i, rule in enumerate(requirements.get("business_rules", []), 1):
            entities.append({
                "text": f"BR-{i:03d}: {rule}",
                "metadata": {"type": "business_rule", "id": f"BR-{i:03d}"}
            })
        
        return entities
