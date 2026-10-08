"""End-to-End Portfolio Generation and Reliability Gate Integration Test.

Tests the complete lifecycle:
  User Requirement (Developer Portfolio)
    -> Planning
    -> Requirements
    -> Architecture
    -> Frontend & Tests
    -> Real Validation & QA
    -> Error Detection & Repair
    -> Review & Improvement
    -> Final QA on Final Workspace
    -> Strict Release Gate
    -> Clean ZIP Packaging
    -> Independent ZIP Extraction & Validation
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.agents.context import AgentContext
from app.agents.registry import AgentRegistry
from app.core.enums import AgentRole, AgentStatus, LogLevel
from app.packaging.workspace import ProjectWorkspace
from app.packaging.zip_builder import ZipPackager, extract_and_verify_zip
from app.validation.executor import CommandResult, ValidationRun, WorkspaceValidator
from app.workflow.engine import StepOutcome, WorkflowEngine
from app.workflow.memory import (
    ArchitectureDesign,
    DatabaseDesign,
    RequirementAnalysis,
    ReviewFindings,
    SharedProjectMemory,
    TechStack,
    ValidationResult,
)
from tests.conftest import StubLLM


def make_context(memory: SharedProjectMemory, llm: Any, adapters: Any) -> AgentContext:
    async def progress(role: AgentRole, percent: int, message: str) -> None:
        pass

    async def log(role: AgentRole, level: LogLevel, message: str, payload: dict | None = None) -> None:
        pass

    return AgentContext(
        memory=memory, llm=llm, registry=adapters, report_progress=progress, report_log=log
    )


class TestPortfolioE2EWorkflow:
    """E2E verification of portfolio project generation through all quality gates."""

    @pytest.mark.asyncio
    async def test_portfolio_generation_through_final_qa_and_zip_validation(
        self, adapters, tmp_path
    ) -> None:
        """Full run generating a modern portfolio with real validation and clean ZIP extraction."""
        memory = SharedProjectMemory(
            run_id="portfolio-run-001",
            project_id="proj-port-1",
            project_name="Developer Portfolio",
            project_slug="dev-portfolio",
            idea=(
                "Create a modern responsive developer portfolio website with: "
                "Home, About, Skills, Experience, Projects, Contact, "
                "responsive navigation, project cards, contact form validation, "
                "dark/light mode, and accessible markup."
            ),
        )
        memory.tech_stack = TechStack(frontend="react")

        # Canned sequence of realistic model responses for the portfolio run
        responses = [
            # 1. Manager
            {
                "project_name": "DevPulse Portfolio",
                "one_liner": "A modern, highly accessible developer portfolio with dark mode.",
                "delivery_approach": "A fast, responsive single-page React app with Tailwind CSS.",
                "success_criteria": [
                    "Home, About, Skills, Experience, Projects, Contact sections",
                    "Contact form validation",
                    "Dark/Light theme toggle",
                    "Responsive navigation",
                ],
                "key_risks": [
                    {"risk": "Form handling without backend", "mitigation": "Client-side validation and state"}
                ],
            },
            # 2. Business Analyst
            {
                "project_overview": "Personal developer portfolio website showcasing skills and experience.",
                "scope_in": ["Home", "About", "Skills", "Experience", "Projects", "Contact"],
                "scope_out": ["Full backend database", "Payment integration"],
                "user_stories": [
                    {
                        "id": "US-01",
                        "story": "As a visitor, I want to toggle between light and dark themes.",
                        "acceptance_criteria": ["Theme persists in local storage", "Smooth transition"],
                    },
                    {
                        "id": "US-02",
                        "story": "As a visitor, I want to submit a contact message with client validation.",
                        "acceptance_criteria": ["Email format validated", "Required fields enforced"],
                    },
                ],
                "functional_requirements": [
                    {"id": "FR-01", "title": "Navigation", "priority": "high", "module": "UI", "description": "Responsive nav"},
                    {"id": "FR-02", "title": "Contact Form", "priority": "high", "module": "Contact", "description": "Form validation"},
                ],
                "non_functional_requirements": [
                    {"id": "NFR-01", "category": "accessibility", "requirement": "WCAG AA compliant contrast"},
                    {"id": "NFR-02", "category": "performance", "requirement": "Fast initial load"},
                ],
                "use_cases": [],
                "actors": ["Visitor", "Recruiter"],
                "entities": ["Project", "Skill", "ContactMessage"],
                "capabilities": {
                    "needs_authentication": False,
                    "needs_database": False,
                    "needs_api": False,
                    "needs_backend": False,
                    "needs_frontend": True,
                },
                "confidence_score": 0.95,
                "assumptions": ["Static deployment"],
                "clarifications": [],
                "suggested_stack": {"frontend": "react", "backend": None, "database": None},
                "executive_summary": "Modern portfolio single-page application.",
            },
            # 3. Solution Architect
            {
                "style": "Static Single-Page Application (SPA)",
                "overview": "React 18 + Vite + Tailwind CSS with modular component hierarchy.",
                "modules": [
                    {"name": "Core", "responsibility": "Shell, Theme, Nav", "entities": [], "depends_on": []},
                    {"name": "Sections", "responsibility": "About, Skills, Projects, Contact", "entities": ["Project", "Skill"], "depends_on": ["Core"]},
                ],
                "layers": [{"name": "UI", "responsibility": "Components and pages", "rules": []}],
                "folder_structure": "frontend/src/\n  components/\n  pages/\n  hooks/\n  types/",
                "api_endpoints": [],
                "integrations": [],
                "cross_cutting": ["Theme switching", "Form validation"],
                "decisions": [
                    {"decision": "React 18 + Vite", "rationale": "High performance and developer velocity"},
                    {"decision": "Tailwind CSS", "rationale": "Utility-first responsive design"},
                ],
            },
            # 4. Frontend Plan & Bundle
            {
                "files": [
                    {"path": "frontend/src/App.tsx", "purpose": "Main portfolio application layout", "depends_on": [], "priority": 1},
                    {"path": "frontend/src/components/ContactForm.tsx", "purpose": "Accessible contact form with validation", "depends_on": [], "priority": 2},
                    {"path": "frontend/src/components/ProjectCard.tsx", "purpose": "Responsive project showcase card", "depends_on": [], "priority": 3},
                ],
                "rationale": "Clean component breakdown.",
            },
            {
                "files": [
                    {
                        "path": "frontend/src/App.tsx",
                        "content": (
                            "import React, { useState } from 'react';\n"
                            "import { ContactForm } from './components/ContactForm';\n"
                            "import { ProjectCard } from './components/ProjectCard';\n\n"
                            "export function App() {\n"
                            "  const [darkMode, setDarkMode] = useState(true);\n"
                            "  return (\n"
                            "    <div className={darkMode ? 'dark bg-slate-900 text-white min-h-screen' : 'bg-white text-slate-900 min-h-screen'}>\n"
                            "      <header className='p-4 border-b flex justify-between items-center'>\n"
                            "        <h1 className='text-xl font-bold'>DevPulse Portfolio</h1>\n"
                            "        <button onClick={() => setDarkMode(!darkMode)} aria-label='Toggle theme' className='px-3 py-1 border rounded'>\n"
                            "          {darkMode ? 'Light Mode' : 'Dark Mode'}\n"
                            "        </button>\n"
                            "      </header>\n"
                            "      <main className='max-w-4xl mx-auto p-6 space-y-8'>\n"
                            "        <section id='about'><h2>About Me</h2><p>Senior Full-Stack Engineer.</p></section>\n"
                            "        <section id='projects'><ProjectCard title='Aegis AI' desc='Multi-agent platform' tags={['AI', 'React']} /></section>\n"
                            "        <section id='contact'><ContactForm /></section>\n"
                            "      </main>\n"
                            "    </div>\n"
                            "  );\n"
                            "}\n"
                        ),
                        "description": "Root component with theme toggle and section layout",
                    },
                    {
                        "path": "frontend/src/components/ContactForm.tsx",
                        "content": (
                            "import React, { useState } from 'react';\n\n"
                            "export function ContactForm() {\n"
                            "  const [email, setEmail] = useState('');\n"
                            "  const [message, setMessage] = useState('');\n"
                            "  const [error, setError] = useState('');\n"
                            "  const [sent, setSent] = useState(false);\n\n"
                            "  const handleSubmit = (e: React.FormEvent) => {\n"
                            "    e.preventDefault();\n"
                            "    if (!email.includes('@')) {\n"
                            "      setError('Please enter a valid email address');\n"
                            "      return;\n"
                            "    }\n"
                            "    if (!message.trim()) {\n"
                            "      setError('Message cannot be empty');\n"
                            "      return;\n"
                            "    }\n"
                            "    setError('');\n"
                            "    setSent(true);\n"
                            "  };\n\n"
                            "  return (\n"
                            "    <form onSubmit={handleSubmit} className='space-y-4' noValidate>\n"
                            "      <h3>Get in touch</h3>\n"
                            "      {error && <div role='alert' className='text-red-500 text-sm'>{error}</div>}\n"
                            "      {sent && <div className='text-green-500'>Thank you! Message sent.</div>}\n"
                            "      <div>\n"
                            "        <label htmlFor='email' className='block text-sm'>Email</label>\n"
                            "        <input id='email' type='email' value={email} onChange={e => setEmail(e.target.value)} className='border p-2 rounded w-full text-black' required />\n"
                            "      </div>\n"
                            "      <div>\n"
                            "        <label htmlFor='msg' className='block text-sm'>Message</label>\n"
                            "        <textarea id='msg' value={message} onChange={e => setMessage(e.target.value)} className='border p-2 rounded w-full text-black' required />\n"
                            "      </div>\n"
                            "      <button type='submit' className='bg-blue-600 text-white px-4 py-2 rounded'>Send Message</button>\n"
                            "    </form>\n"
                            "  );\n"
                            "}\n"
                        ),
                        "description": "Accessible contact form with inline validation",
                    },
                    {
                        "path": "frontend/src/components/ProjectCard.tsx",
                        "content": (
                            "import React from 'react';\n\n"
                            "interface ProjectCardProps { title: string; desc: string; tags: string[]; }\n\n"
                            "export function ProjectCard({ title, desc, tags }: ProjectCardProps) {\n"
                            "  return (\n"
                            "    <article className='p-4 border rounded shadow-sm hover:shadow-md transition'>\n"
                            "      <h4 className='font-semibold text-lg'>{title}</h4>\n"
                            "      <p className='text-sm text-gray-400 mt-1'>{desc}</p>\n"
                            "      <div className='flex gap-2 mt-3'>\n"
                            "        {tags.map(t => <span key={t} className='px-2 py-0.5 text-xs bg-slate-800 rounded'>{t}</span>)}\n"
                            "      </div>\n"
                            "    </article>\n"
                            "  );\n"
                            "}\n"
                        ),
                        "description": "Card component displaying project details and tags",
                    },
                ],
                "notes": "Generated all portfolio components.",
            },
            # 5. QA Engineer
            {
                "files": [
                    {
                        "path": "frontend/src/App.test.tsx",
                        "content": (
                            "import { render, screen, fireEvent } from '@testing-library/react';\n"
                            "import { App } from './App';\n"
                            "import { describe, it, expect } from 'vitest';\n\n"
                            "describe('Portfolio Application', () => {\n"
                            "  it('renders portfolio heading and toggles theme', () => {\n"
                            "    render(<App />);\n"
                            "    expect(screen.getByText('DevPulse Portfolio')).toBeInTheDocument();\n"
                            "    const toggle = screen.getByRole('button', { name: /toggle theme/i });\n"
                            "    fireEvent.click(toggle);\n"
                            "    expect(screen.getByText('Light Mode')).toBeInTheDocument();\n"
                            "  });\n"
                            "});\n"
                        ),
                        "description": "Comprehensive UI test suite verifying portfolio and theme toggle",
                    }
                ],
                "coverage_notes": "Tests cover theme toggle and core navigation.",
                "manual_checks": ["Verify responsive viewports on mobile"],
            },
            # 6. Review Engineer
            {
                "issues": [],
                "strengths": ["Clear semantics", "Proper ARIA labels", "Robust form validation"],
                "missing_apis": [],
                "duplication": [],
                "overall_assessment": "High quality portfolio with clean accessibility.",
                "quality_score": 0.94,
            },
            # 7. Documentation Engineer
            {
                "readme": (
                    "# DevPulse Portfolio\n\n"
                    "A modern, responsive developer portfolio created with Aegis AI.\n\n"
                    "## Features\n"
                    "- Responsive navigation\n"
                    "- Dark / Light mode toggle\n"
                    "- Accessible contact form with client validation\n"
                    "- Interactive project showcase cards\n\n"
                    "## Development\n"
                    "```bash\n"
                    "cd frontend\n"
                    "npm install\n"
                    "npm run dev\n"
                    "```\n"
                ),
                "installation_guide": "# Installation\n\nRun npm install in frontend/",
                "api_documentation": "No backend required for this client-side portfolio.",
                "developer_guide": "# Developer Guide\n\nComponents are located in frontend/src/components/.",
                "environment_reference": "# Environment Reference\n\nCopy .env.example if custom base URLs are needed.",
            },
        ]

        llm = StubLLM(responses)
        ctx = make_context(memory, llm, adapters)

        engine = WorkflowEngine(agent_registry=AgentRegistry(), llm=llm)
        outcome = await engine.run(ctx)

        # Verification of pipeline guarantees:
        assert not outcome.failed, outcome.failure_reason
        assert outcome.failure_reason == ""

        # Verify DB and Backend correctly skipped for static site
        skipped_roles = {o.role for o in outcome.skipped}
        assert AgentRole.DATABASE_ENGINEER in skipped_roles
        assert AgentRole.BACKEND_ENGINEER in skipped_roles

        # Verify Frontend, QA, Review, Final QA and Docs all executed
        executed_roles = {o.role for o in outcome.executed}
        assert AgentRole.FRONTEND_ENGINEER in executed_roles
        assert AgentRole.QA_ENGINEER in executed_roles
        assert AgentRole.REVIEW_ENGINEER in executed_roles
        assert AgentRole.FINAL_QA in executed_roles
        assert AgentRole.DOCUMENTATION_ENGINEER in executed_roles

        # Final QA must have executed and recorded release eligibility
        assert memory.release_eligible is True
        assert memory.final_qa_result is not None
        assert memory.final_qa_result.passed is True

        # Verify workspace files
        assert memory.workspace.exists("frontend/src/App.tsx")
        assert memory.workspace.exists("frontend/src/components/ContactForm.tsx")
        assert memory.workspace.exists("frontend/src/components/ProjectCard.tsx")
        assert memory.workspace.exists("frontend/src/App.test.tsx")
        assert memory.workspace.exists("README.md")

        # Now test packaging & release
        packager = ZipPackager(artifact_root=tmp_path)
        package = packager.write(
            memory.workspace, run_id="portfolio-rel-1", project_slug=memory.project_slug
        )

        assert package.path.exists()
        assert package.size_bytes > 0

        # Now perform independent extraction and verification
        extract_dir = tmp_path / "extracted_verify"
        extracted = extract_and_verify_zip(package.path, extract_dir)

        # Confirm all key files are extracted cleanly
        assert "frontend/src/App.tsx" in extracted
        assert "frontend/src/components/ContactForm.tsx" in extracted
        assert "README.md" in extracted

        # Confirm exclusions are enforced in the package
        for path in extracted.keys():
            assert not path.startswith(".env") or path.endswith(".example")
            assert "node_modules" not in path
            assert "__pycache__" not in path

    @pytest.mark.asyncio
    async def test_improvement_regression_caught_by_final_qa_and_blocks_release(
        self, adapters
    ) -> None:
        """Section 32: If improvement introduces a regression, Final QA catches it and blocks release."""
        memory = SharedProjectMemory(
            run_id="run-regr-test",
            project_id="p-regr",
            project_name="Regression Test App",
            project_slug="regr-app",
            idea="Portfolio with regression injection",
        )
        memory.workspace.write("frontend/src/App.tsx", "export const App = () => <div>OK</div>;")

        # Initial QA passed
        initial_qa = ValidationResult(
            passed=True,
            stack="frontend",
            total_commands=2,
            failed_commands=0,
            workspace_fingerprint=memory.workspace.fingerprint,
        )
        memory.record_validation_run(initial_qa)
        assert memory.is_validation_current is True

        # Improvement agent modifies file and introduces a type error
        memory.workspace.write("frontend/src/App.tsx", "export const App = () => <broken syntax;")

        # Fingerprint changed! Previous validation is now stale
        assert memory.is_validation_current is False

        # Final QA executes against modified workspace and finds broken command
        final_qa = ValidationResult(
            passed=False,
            stack="frontend",
            total_commands=2,
            failed_commands=1,
            failures=[
                {
                    "command": "npm run build",
                    "file": "frontend/src/App.tsx",
                    "line": 1,
                    "error": "SyntaxError: Unexpected token",
                    "category": "syntax_error",
                    "responsible_agent": "frontend_engineer",
                }
            ],
            workspace_fingerprint=memory.workspace.fingerprint,
        )
        memory.record_final_qa(final_qa)

        # Crucial assertion: release must be strictly BLOCKED!
        assert memory.release_eligible is False
        assert "ZIP release is blocked" in memory.notes[-1]
