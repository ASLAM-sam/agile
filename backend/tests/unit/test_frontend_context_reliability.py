"""Tests for Frontend LLM Context Reliability.

Verifies:
- Test 1: Frontend prompt contains actual package.json.
- Test 2: Frontend prompt contains actual tsconfig.json.
- Test 3: Frontend prompt does not fabricate dependencies (safety rules enforced).
- Test 4: Protected scaffold files cannot be overwritten accidentally.
- Test 5: Missing optional scaffold files do not crash generation.
- Test 6: Existing generation flow still works.
- Test 7: No additional LLM request is introduced (0 extra LLM calls).
"""

from __future__ import annotations

import json
import pytest

from app.agents.context import AgentContext
from app.agents.frontend_engineer import (
    DEPENDENCY_SAFETY_RULES,
    PROTECTED_SCAFFOLD_FILES,
    SCAFFOLDED_FILES_RULES,
    TYPESCRIPT_SAFETY_RULES,
    FrontendEngineerAgent,
)
from app.core.enums import AgentRole
from app.packaging.workspace import ProjectWorkspace
from app.workflow.memory import (
    ArchitectureDesign,
    RequirementAnalysis,
    SharedProjectMemory,
    TechStack,
)
from tests.conftest import StubLLM


def _make_context(memory: SharedProjectMemory, stub_llm: StubLLM, adapters) -> AgentContext:
    async def _noop_progress(role, percent, msg):
        pass

    async def _noop_log(role, level, msg, payload=None):
        pass

    return AgentContext(
        memory=memory,
        llm=stub_llm,
        registry=adapters,
        report_progress=_noop_progress,
        report_log=_noop_log,
    )


class TestFrontendContextReliability:
    """Verifies that FrontendEngineerAgent injects actual workspace config and protects scaffold files."""

    @pytest.mark.asyncio
    async def test_1_frontend_prompt_contains_actual_package_json(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """Test 1: Frontend prompt contains actual package.json from the workspace."""
        memory.tech_stack = TechStack(frontend="react")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
        memory.user_prompt = "Build a modern analytics dashboard"

        stub_llm = StubLLM([
            {
                "files": [
                    {
                        "path": "frontend/src/index.css",
                        "content": "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n",
                        "description": "Tailwind styles",
                    },
                    {
                        "path": "frontend/src/App.tsx",
                        "content": "export default function App() { return <div>Dashboard</div>; }",
                        "description": "App component",
                    },
                    {
                        "path": "frontend/src/main.tsx",
                        "content": "import React from 'react'; import App from './App';\n",
                        "description": "Main entry",
                    },
                ]
            }
        ])

        ctx = _make_context(memory, stub_llm, adapters)
        agent = FrontendEngineerAgent()
        result = await agent.execute(ctx)

        assert result.role == AgentRole.FRONTEND_ENGINEER
        assert len(stub_llm.calls) == 1

        prompt = stub_llm.calls[0].user_message
        assert "PROJECT CONFIGURATION CONTEXT" in prompt
        assert "The following files already exist in the project." in prompt
        assert "You MUST treat them as authoritative." in prompt
        assert "=== frontend/package.json ===" in prompt

        # Verify that actual dependencies from the scaffolded package.json are in the prompt
        pkg_json = memory.workspace.read("frontend/package.json")
        assert pkg_json is not None
        assert "lucide-react" in pkg_json
        assert "lucide-react" in prompt
        assert "react-router-dom" in prompt

    @pytest.mark.asyncio
    async def test_2_frontend_prompt_contains_actual_tsconfig_json(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """Test 2: Frontend prompt contains actual tsconfig.json and related configs."""
        memory.tech_stack = TechStack(frontend="react")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
        memory.user_prompt = "Build a modern task manager"

        stub_llm = StubLLM([
            {
                "files": [
                    {
                        "path": "frontend/src/index.css",
                        "content": "body { margin: 0; }",
                        "description": "styles",
                    },
                    {
                        "path": "frontend/src/App.tsx",
                        "content": "export default function App() { return <h1>Tasks</h1>; }",
                        "description": "App",
                    },
                    {
                        "path": "frontend/src/main.tsx",
                        "content": "import App from './App';",
                        "description": "entry",
                    },
                ]
            }
        ])

        ctx = _make_context(memory, stub_llm, adapters)
        agent = FrontendEngineerAgent()
        await agent.execute(ctx)

        prompt = stub_llm.calls[0].user_message
        assert "=== frontend/tsconfig.json ===" in prompt
        assert "=== frontend/tsconfig.app.json ===" in prompt
        assert "=== frontend/tsconfig.node.json ===" in prompt
        assert "=== frontend/vite.config.ts ===" in prompt
        assert "=== frontend/index.html ===" in prompt

        # Verify actual tsconfig content from workspace is present in prompt
        tsconfig_app = memory.workspace.read("frontend/tsconfig.app.json")
        assert tsconfig_app is not None
        assert "compilerOptions" in tsconfig_app
        assert "compilerOptions" in prompt
        assert "noUnusedLocals" in prompt

    @pytest.mark.asyncio
    async def test_3_frontend_prompt_does_not_fabricate_dependencies(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """Test 3: Prompt enforces Dependency and TypeScript safety rules."""
        memory.tech_stack = TechStack(frontend="react")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
        memory.user_prompt = "Portfolio app"

        stub_llm = StubLLM([
            {
                "files": [
                    {
                        "path": "frontend/src/index.css",
                        "content": "/* css */",
                        "description": "css",
                    },
                    {
                        "path": "frontend/src/App.tsx",
                        "content": "export default function App() { return <h1>Portfolio</h1>; }",
                        "description": "app",
                    },
                    {
                        "path": "frontend/src/main.tsx",
                        "content": "/* main */",
                        "description": "main",
                    },
                ]
            }
        ])

        ctx = _make_context(memory, stub_llm, adapters)
        agent = FrontendEngineerAgent()
        await agent.execute(ctx)

        prompt = stub_llm.calls[0].user_message

        # Assert DEPENDENCY_SAFETY_RULES are present
        assert "DEPENDENCY SAFETY RULES" in prompt
        assert "Only import packages that are present in the provided package.json." in prompt
        assert "Do not invent npm packages." in prompt
        assert "Do not assume a package is installed because it is commonly used." in prompt

        # Assert TYPESCRIPT_SAFETY_RULES are present
        assert "TYPESCRIPT SAFETY RULES" in prompt
        assert "The provided tsconfig files are authoritative." in prompt
        assert "Do not weaken tsconfig settings to make code compile." in prompt

        # Assert SCAFFOLDED_FILES ownership rule is present
        assert "SCAFFOLDED FILES" in prompt
        assert "The following files are controlled by the project scaffold:" in prompt

    @pytest.mark.asyncio
    async def test_4_protected_scaffold_files_cannot_be_overwritten(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """Test 4: LLM attempts to overwrite protected scaffold files are rejected."""
        memory.tech_stack = TechStack(frontend="react")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
        memory.user_prompt = "Portfolio website"

        # LLM returns attempts to overwrite package.json and tsconfig.json with malicious/altered content
        stub_llm = StubLLM([
            {
                "files": [
                    {
                        "path": "frontend/package.json",
                        "content": '{"name": "malicious-overwrite", "dependencies": {}}',
                        "description": "malicious package.json overwrite",
                    },
                    {
                        "path": "frontend/tsconfig.json",
                        "content": '{"compilerOptions": {"strict": false}}',
                        "description": "weakened tsconfig overwrite",
                    },
                    {
                        "path": "frontend/src/index.css",
                        "content": "body { background: #000; }",
                        "description": "valid index.css",
                    },
                    {
                        "path": "frontend/src/App.tsx",
                        "content": "export default function App() { return <h1>Safe</h1>; }",
                        "description": "valid App.tsx",
                    },
                    {
                        "path": "frontend/src/main.tsx",
                        "content": "import App from './App';",
                        "description": "valid main.tsx",
                    },
                ]
            }
        ])

        ctx = _make_context(memory, stub_llm, adapters)
        agent = FrontendEngineerAgent()
        result = await agent.execute(ctx)

        # 1. Package.json in workspace must retain original scaffold content, NOT the LLM overwrite
        pkg = memory.workspace.read("frontend/package.json")
        assert pkg is not None
        assert "malicious-overwrite" not in pkg
        assert "lucide-react" in pkg

        # 2. Tsconfig in workspace must retain original strict content, NOT the LLM overwrite
        tsconfig = memory.workspace.read("frontend/tsconfig.json")
        assert tsconfig is not None
        assert "tsconfig.app.json" in tsconfig
        assert "weakened" not in tsconfig

        # 3. Legitimate planned source files were written successfully
        assert memory.workspace.exists("frontend/src/App.tsx")
        assert memory.workspace.read("frontend/src/App.tsx") == "export default function App() { return <h1>Safe</h1>; }"

        # 4. Warnings record the rejected scaffold overwrite attempts
        assert any("cannot overwrite protected scaffold file" in w for w in result.warnings)

    def test_5_missing_optional_scaffold_files_do_not_crash(self) -> None:
        """Test 5: Missing optional scaffold files do not crash context construction or fabricate files."""
        memory = SharedProjectMemory(
            run_id="test-run-5",
            project_id="test-proj-5",
            project_name="Test Project 5",
            project_slug="test-proj-5",
            idea="test",
            workspace=ProjectWorkspace(),
        )

        # Case A: Empty workspace
        context = FrontendEngineerAgent.build_configuration_context(memory)
        assert context == ""

        # Case B: Only package.json exists, other configs missing
        memory.workspace.write("frontend/package.json", '{"name": "partial-project"}')
        context = FrontendEngineerAgent.build_configuration_context(memory)

        assert "PROJECT CONFIGURATION CONTEXT" in context
        assert "=== frontend/package.json ===" in context
        assert '{"name": "partial-project"}' in context
        # Must not fabricate missing tsconfig or vite config
        assert "=== frontend/tsconfig.json ===" not in context
        assert "=== frontend/vite.config.ts ===" not in context

    @pytest.mark.asyncio
    async def test_6_existing_generation_flow_still_works(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """Test 6: Existing HTML/CSS/JS and React generation flows still work seamlessly."""
        memory.tech_stack = TechStack(frontend="html_css_js")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
        memory.user_prompt = "Simple landing page"

        stub_llm = StubLLM([
            {
                "files": [
                    {
                        "path": "frontend/index.html",
                        "content": "<!DOCTYPE html><html><body><h1>Landing</h1></body></html>",
                        "description": "Index HTML",
                    },
                    {
                        "path": "frontend/css/styles.css",
                        "content": "h1 { color: blue; }",
                        "description": "Styles",
                    },
                    {
                        "path": "frontend/js/app.js",
                        "content": "console.log('Landing loaded');",
                        "description": "App JS",
                    },
                ]
            }
        ])

        ctx = _make_context(memory, stub_llm, adapters)
        agent = FrontendEngineerAgent()
        result = await agent.execute(ctx)

        assert result.role == AgentRole.FRONTEND_ENGINEER
        assert result.files_produced >= 3
        assert memory.workspace.read("frontend/index.html") == "<!DOCTYPE html><html><body><h1>Landing</h1></body></html>"

    @pytest.mark.asyncio
    async def test_7_no_additional_llm_request_introduced(
        self, memory: SharedProjectMemory, adapters
    ) -> None:
        """Test 7: Context injection introduces zero additional LLM requests (exactly 1 call for single-pass)."""
        memory.tech_stack = TechStack(frontend="react")
        memory.analysis = RequirementAnalysis(needs_frontend=True, needs_backend=False)
        memory.user_prompt = "Fast dashboard"

        stub_llm = StubLLM([
            {
                "files": [
                    {
                        "path": "frontend/src/index.css",
                        "content": "/* styles */",
                        "description": "css",
                    },
                    {
                        "path": "frontend/src/App.tsx",
                        "content": "export default function App() { return <div>App</div>; }",
                        "description": "app",
                    },
                    {
                        "path": "frontend/src/main.tsx",
                        "content": "/* main */",
                        "description": "main",
                    },
                ]
            }
        ])

        ctx = _make_context(memory, stub_llm, adapters)
        agent = FrontendEngineerAgent()
        await agent.execute(ctx)

        # Strictly 1 structured LLM call
        assert len(stub_llm.calls) == 1
