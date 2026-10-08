"""Regression tests for the Aegis AI frontend pipeline.

Tests all 6 failure modes specified in the prompt:
- CASE 1: SharedProjectMemory user_prompt access without AttributeError
- CASE 2: Frontend Engineer failure causes Final QA FAIL and release_eligible = False
- CASE 3: Frontend required file empty causes Final QA FAIL
- CASE 4: Blocking review finding remains unresolved causes Final QA FAIL
- CASE 5: Vanilla HTML/CSS/JS project has no requirement for frontend/src/
- CASE 6: Valid static portfolio frontend generation completes successfully
"""

from __future__ import annotations

import os
import pytest
from app.agents.context import AgentContext
from app.agents.final_qa_agent import FinalQAAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.core.enums import AgentRole, AgentStatus
from app.workflow.memory import (
    ArchitectureDesign,
    RequirementAnalysis,
    ReviewFindings,
    SharedProjectMemory,
    TechStack,
)
from tests.conftest import StubLLM


def _make_context(memory: SharedProjectMemory, stub_llm: StubLLM, adapters) -> AgentContext:
    async def _noop_progress(role, percent, msg):
        pass

    async def _noop_log(role, level, msg, payload):
        pass

    return AgentContext(
        memory=memory,
        llm=stub_llm,
        registry=adapters,
        report_progress=_noop_progress,
        report_log=_noop_log,
    )


class TestFrontendPipelineRegression:
    """Regression suite guaranteeing the frontend pipeline contracts."""

    @pytest.mark.asyncio
    async def test_case_1_shared_project_memory_user_prompt_access(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """CASE 1: SharedProjectMemory user_prompt property aliases idea without AttributeError."""
        # 1. Direct property access
        assert memory.user_prompt == memory.idea
        assert memory.user_prompt == "A hospital management system for appointments and patient records"

        # 2. Setter works and updates idea
        memory.user_prompt = "Updated portfolio prompt"
        assert memory.idea == "Updated portfolio prompt"
        assert memory.user_prompt == "Updated portfolio prompt"

        # 3. FrontendEngineer execution does not raise AttributeError
        memory.tech_stack = TechStack(frontend="html_css_js")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
        stub_llm = StubLLM([
            {
                "files": [
                    {
                        "path": "frontend/index.html",
                        "content": "<!DOCTYPE html><html><head><title>Test</title></head><body><main>Content</main></body></html>",
                        "description": "HTML root",
                    },
                    {
                        "path": "frontend/css/styles.css",
                        "content": ":root { --primary: #000; } body { margin: 0; }",
                        "description": "CSS stylesheet",
                    },
                    {
                        "path": "frontend/js/app.js",
                        "content": "console.log('App ready'); window.addEventListener('DOMContentLoaded', () => {});",
                        "description": "JavaScript entrypoint",
                    },
                ]
            }
        ])
        ctx = _make_context(memory, stub_llm, adapters)
        result = await FrontendEngineerAgent().execute(ctx)
        assert result.role == AgentRole.FRONTEND_ENGINEER
        assert result.files_produced >= 3

    @pytest.mark.asyncio
    async def test_case_2_frontend_engineer_fails_blocks_release(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """CASE 2: When Frontend Engineer fails, Final QA FAILS and release_eligible = False."""
        os.environ["AEGIS_MOCK_VALIDATION"] = "true"
        try:
            memory.tech_stack = TechStack(frontend="html_css_js")
            memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
            # Emulate scaffold files but Frontend Engineer crashed
            memory.workspace.write("frontend/index.html", "<!DOCTYPE html><html><head></head><body>Scaffold</body></html>")
            memory.workspace.write("frontend/css/styles.css", "body { margin: 0; }")
            memory.workspace.write("frontend/js/app.js", "console.log('scaffold');")

            # Record that Frontend Engineer FAILED
            memory.record_agent_status(
                AgentRole.FRONTEND_ENGINEER,
                AgentStatus.FAILED,
                error="AttributeError: 'SharedProjectMemory' object has no attribute 'user_prompt'",
            )

            stub_llm = StubLLM([])
            ctx = _make_context(memory, stub_llm, adapters)

            result = await FinalQAAgent().execute(ctx)

            assert result.output["passed"] is False
            assert result.output["release_eligible"] is False
            assert memory.release_eligible is False
            assert any("Frontend Engineer" in f.get("error", "") for f in result.output["failures"])
        finally:
            os.environ.pop("AEGIS_MOCK_VALIDATION", None)

    @pytest.mark.asyncio
    async def test_case_3_frontend_required_file_is_empty_fails_final_qa(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """CASE 3: When a required frontend file is empty, Final QA FAILS."""
        os.environ["AEGIS_MOCK_VALIDATION"] = "true"
        try:
            memory.tech_stack = TechStack(frontend="html_css_js")
            memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
            memory.record_agent_status(AgentRole.FRONTEND_ENGINEER, AgentStatus.COMPLETED)

            # Write files, but index.html is empty!
            memory.workspace.write("frontend/index.html", "")
            memory.workspace.write("frontend/css/styles.css", ":root { --primary: #000; } body { margin: 0; }")
            memory.workspace.write("frontend/js/app.js", "console.log('App ready'); window.addEventListener('DOMContentLoaded', () => {});")

            stub_llm = StubLLM([])
            ctx = _make_context(memory, stub_llm, adapters)

            result = await FinalQAAgent().execute(ctx)

            assert result.output["passed"] is False
            assert result.output["release_eligible"] is False
            assert memory.release_eligible is False
            assert any("empty" in f.get("error", "").lower() for f in result.output["failures"])
        finally:
            os.environ.pop("AEGIS_MOCK_VALIDATION", None)

    @pytest.mark.asyncio
    async def test_case_4_blocking_review_finding_unresolved_fails_final_qa(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """CASE 4: Unresolved blocking review findings cause Final QA to FAIL."""
        os.environ["AEGIS_MOCK_VALIDATION"] = "true"
        try:
            memory.tech_stack = TechStack(frontend="html_css_js")
            memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
            memory.record_agent_status(AgentRole.FRONTEND_ENGINEER, AgentStatus.COMPLETED)

            # Valid files
            memory.workspace.write(
                "frontend/index.html",
                "<!DOCTYPE html><html><head><title>Title</title></head><body><header>Nav</header><main>Content</main></body></html>",
            )
            memory.workspace.write("frontend/css/styles.css", ":root { --primary: #000; } body { margin: 0; color: #fff; }")
            memory.workspace.write("frontend/js/app.js", "console.log('App running'); window.addEventListener('DOMContentLoaded', () => {});")

            # Blocking review finding
            memory.review = ReviewFindings(
                issues=[
                    {
                        "id": "ISS-01",
                        "severity": "critical",
                        "category": "missing-implementation",
                        "file": "frontend/tests/tasks.test.js",
                        "description": "frontend/tests/tasks.test.js imports ../js/tasks.js which does not exist",
                        "recommendation": "Update test to import from ../js/app.js",
                    }
                ]
            )
            # Improvement only resolved nothing or different issue
            memory.improvements_applied = []

            stub_llm = StubLLM([])
            ctx = _make_context(memory, stub_llm, adapters)

            result = await FinalQAAgent().execute(ctx)

            assert result.output["passed"] is False
            assert result.output["release_eligible"] is False
            assert memory.release_eligible is False
            assert any("ISS-01" in f.get("error", "") for f in result.output["failures"])
        finally:
            os.environ.pop("AEGIS_MOCK_VALIDATION", None)

    def test_case_5_vanilla_html_css_js_does_not_require_frontend_src(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """CASE 5: Vanilla HTML/CSS/JS project does not require frontend/src/ directory."""
        memory.tech_stack = TechStack(frontend="html_css_js")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)

        # Emulate vanilla structure with package.json and direct files
        memory.workspace.write("frontend/package.json", '{"name": "portfolio-web"}')
        memory.workspace.write(
            "frontend/index.html",
            "<!DOCTYPE html><html><head><title>Portfolio</title></head><body><header>Nav</header><main>Hero</main></body></html>",
        )
        memory.workspace.write("frontend/css/styles.css", ":root { --c: #fff; } body { margin: 0; }")
        memory.workspace.write("frontend/js/app.js", "console.log('Loaded'); window.addEventListener('load', () => {});")

        stub_llm = StubLLM([])
        ctx = _make_context(memory, stub_llm, adapters)

        findings = QAEngineerAgent()._validate_structure(ctx)

        # Must NOT report frontend/src/ as missing or empty!
        assert not any("frontend/src" in f for f in findings)
        assert not any("empty Python body" in f for f in findings)

    @pytest.mark.asyncio
    async def test_case_6_valid_static_portfolio_generation_completes(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """CASE 6: Valid static portfolio completes generation with complete content."""
        memory.tech_stack = TechStack(frontend="html_css_js")
        memory.analysis = RequirementAnalysis(
            needs_frontend=True,
            needs_backend=False,
            project_overview="Modern responsive personal portfolio with hero, about, skills, projects, contact",
        )
        memory.architecture = ArchitectureDesign(
            style="Client-Side Static Architecture",
            overview="Portfolio application",
            folder_structure="frontend/\n├── index.html\n├── css/\n│   └── styles.css\n└── js/\n    └── app.js",
        )

        portfolio_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jane Doe | Senior Software Engineer Portfolio</title>
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <header class="navbar">
        <nav class="nav-container">
            <a href="#hero" class="nav-logo">Jane Doe</a>
            <ul class="nav-links">
                <li><a href="#about">About</a></li>
                <li><a href="#skills">Skills</a></li>
                <li><a href="#projects">Projects</a></li>
                <li><a href="#contact">Contact</a></li>
            </ul>
        </nav>
    </header>
    <main>
        <section id="hero" class="hero-section">
            <h1>Hi, I'm Jane Doe</h1>
            <p>Senior Full-Stack Engineer crafting resilient cloud software.</p>
        </section>
        <section id="about" class="about-section">
            <h2>About Me</h2>
            <p>Passionate developer with 8+ years building distributed web applications.</p>
        </section>
        <section id="skills" class="skills-section">
            <h2>Technical Skills</h2>
            <div class="skills-grid"><span>Python</span><span>JavaScript</span><span>HTML5/CSS3</span></div>
        </section>
        <section id="projects" class="projects-section">
            <h2>Featured Projects</h2>
            <div class="projects-grid"><div class="card"><h3>Project Alpha</h3></div></div>
        </section>
        <section id="contact" class="contact-section">
            <h2>Get In Touch</h2>
            <form id="contact-form"><input type="email" id="email" required><button type="submit">Send</button></form>
        </section>
    </main>
    <footer><p>&copy; 2026 Jane Doe</p></footer>
    <script type="module" src="js/app.js"></script>
</body>
</html>"""

        portfolio_css = """:root {
    --primary: #6366f1;
    --background: #0f172a;
    --surface: #1e293b;
    --text: #f8fafc;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: sans-serif; background: var(--background); color: var(--text); line-height: 1.6; }
.nav-container { display: flex; justify-content: space-between; padding: 1rem 2rem; }
.hero-section { min-height: 60vh; display: grid; place-items: center; text-align: center; }
"""

        portfolio_js = """// Portfolio interactive application
export function validateContactForm(email) {
    return email && email.includes('@');
}

window.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('contact-form');
    if (form) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            console.log('Message submitted');
        });
    }
});
"""

        stub_llm = StubLLM([
            {
                "files": [
                    {"path": "frontend/index.html", "content": portfolio_html, "description": "HTML root"},
                    {"path": "frontend/css/styles.css", "content": portfolio_css, "description": "Styles"},
                    {"path": "frontend/js/app.js", "content": portfolio_js, "description": "JavaScript entrypoint"},
                ]
            }
        ])

        ctx = _make_context(memory, stub_llm, adapters)
        result = await FrontendEngineerAgent().execute(ctx)

        assert result.role == AgentRole.FRONTEND_ENGINEER
        assert result.files_produced >= 3
        assert memory.workspace.exists("frontend/index.html")
        assert memory.workspace.exists("frontend/css/styles.css")
        assert memory.workspace.exists("frontend/js/app.js")
        assert len(memory.workspace.read("frontend/index.html")) > 200
