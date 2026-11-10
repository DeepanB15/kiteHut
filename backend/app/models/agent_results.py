"""
Agent Result Models.

Structured output models for each specialized agent.
All agents produce Pydantic-validated JSON.
"""

from typing import List

from pydantic import BaseModel, Field


# ============================================================
# AI Recon Agent Result
# ============================================================

class AIReconResult(BaseModel):
    """AI-powered reconnaissance analysis output."""

    project_summary: str = Field(
        description="One-paragraph summary of the project"
    )
    project_purpose: str = Field(
        description="What problem this repository solves"
    )
    application_type: str = Field(
        description="Type: web_api, web_frontend, full_stack, cli_tool, "
                    "library, machine_learning, data_pipeline, "
                    "microservice, mobile_application, unknown"
    )
    architecture_overview: str = Field(
        description="How the repository is organized"
    )
    major_components: List[str] = Field(
        default_factory=list,
        description="Major components or modules"
    )
    entry_points: List[str] = Field(
        default_factory=list,
        description="Where the application starts"
    )
    key_technologies: List[str] = Field(
        default_factory=list,
        description="Key technologies and frameworks used"
    )
    observations: List[str] = Field(
        default_factory=list,
        description="Notable observations about the repository"
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Assumptions made during analysis"
    )
    unknowns: List[str] = Field(
        default_factory=list,
        description="Things that could not be determined"
    )
    areas_for_investigation: List[str] = Field(
        default_factory=list,
        description="Areas that need deeper analysis by specialized agents"
    )


# ============================================================
# Architecture Agent Result
# ============================================================

class ArchitectureResult(BaseModel):
    """Architecture analysis output."""

    architecture_pattern: str = Field(
        description="Detected pattern: MVC, layered, monolith, "
                    "microservices, event_driven, clean_architecture, etc."
    )
    components: List[str] = Field(
        default_factory=list,
        description="Identified architectural components"
    )
    layers: List[str] = Field(
        default_factory=list,
        description="Application layers (presentation, business, data, etc.)"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Key dependency relationships between components"
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Architecture strengths"
    )
    potential_issues: List[str] = Field(
        default_factory=list,
        description="Potential architecture problems or risks"
    )
    investigation_areas: List[str] = Field(
        default_factory=list,
        description="Areas that need further investigation"
    )


# ============================================================
# Security Agent Result
# ============================================================

class SecurityResult(BaseModel):
    """Security analysis output."""

    security_observations: List[str] = Field(
        default_factory=list,
        description="General security observations"
    )
    potential_risks: List[str] = Field(
        default_factory=list,
        description="Potential security risks identified"
    )
    security_strengths: List[str] = Field(
        default_factory=list,
        description="Good security practices found"
    )
    areas_for_verification: List[str] = Field(
        default_factory=list,
        description="Areas that need manual verification"
    )


# ============================================================
# Code Quality Agent Result
# ============================================================

class QualityResult(BaseModel):
    """Code quality analysis output."""

    quality_summary: str = Field(
        description="Overall quality assessment"
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Code quality strengths"
    )
    potential_issues: List[str] = Field(
        default_factory=list,
        description="Potential quality issues"
    )
    maintainability_observations: List[str] = Field(
        default_factory=list,
        description="Observations about maintainability"
    )
    refactoring_candidates: List[str] = Field(
        default_factory=list,
        description="Code areas that may benefit from refactoring"
    )


# ============================================================
# Testing Agent Result
# ============================================================

class TestingResult(BaseModel):
    """Testing analysis output."""

    test_frameworks: List[str] = Field(
        default_factory=list,
        description="Detected test frameworks"
    )
    test_types: List[str] = Field(
        default_factory=list,
        description="Types of tests found: unit, integration, e2e, etc."
    )
    testing_maturity: str = Field(
        description="Maturity level: none, low, medium, high"
    )
    tested_components: List[str] = Field(
        default_factory=list,
        description="Components that appear to have tests"
    )
    potentially_untested_components: List[str] = Field(
        default_factory=list,
        description="Components that appear to lack tests"
    )
    observations: List[str] = Field(
        default_factory=list,
        description="Testing-related observations"
    )
