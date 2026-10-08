"""Deterministic dependency consistency validator.

Scans frontend TypeScript and JavaScript files for external imports,
verifies that every imported package is declared in package.json, and
ensures scripts, tsconfig, and dependencies are internally consistent.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Matches standard ES and TypeScript imports/exports
_IMPORT_REGEX = re.compile(
    r"""(?:import\s+(?:(?:[\w*\s{},$]+from\s+)?['"]([^'"]+)['"])|export\s+(?:[\w*\s{},$]+from\s+)['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)

# Standard Node.js built-ins to ignore
_NODE_BUILTINS = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "fs/promises", "http", "http2", "https", "inspector",
    "module", "net", "os", "path", "path/posix", "path/win32", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl", "stream",
    "stream/consumers", "stream/promises", "stream/web", "string_decoder",
    "timers", "timers/promises", "tls", "trace_events", "tty", "url",
    "util", "util/types", "v8", "vm", "wasi", "worker_threads", "zlib",
})

# Known package versions for automatic safe addition
_KNOWN_PACKAGES: dict[str, str] = {
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.4",
    "lucide-react": "^0.460.0",
    "class-variance-authority": "^0.7.0",
    "@types/node": "^20.17.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "framer-motion": "^11.11.0",
    "react-icons": "^5.3.0",
    "canvas-confetti": "^1.9.3",
    "@types/canvas-confetti": "^1.9.0",
    "axios": "^1.7.7",
    "zod": "^3.23.8",
}


def extract_package_name(import_path: str) -> str | None:
    """Extract package root name from an import path.

    Returns None for relative/alias imports or built-in modules.
    """
    clean = import_path.strip()
    if not clean or clean.startswith((".", "/", "@/", "~/")):
        return None
    if clean.startswith("node:"):
        return None
    if clean in _NODE_BUILTINS:
        return None

    parts = clean.split("/")
    if clean.startswith("@"):
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return parts[0]
    return parts[0]


def scan_source_imports(files: dict[str, str]) -> set[str]:
    """Scan all frontend TS/JS source files for external imported packages."""
    packages: set[str] = set()
    for path, content in files.items():
        if not path.startswith("frontend/"):
            continue
        if not path.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs")):
            continue
        for match in _IMPORT_REGEX.finditer(content):
            specifier = match.group(1) or match.group(2) or match.group(3)
            if specifier:
                pkg = extract_package_name(specifier)
                if pkg:
                    packages.add(pkg)
    return packages


def validate_and_sync_dependencies(files: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Verify package.json matches source imports and project configuration.

    Returns (updated_files_dict, log_messages).
    """
    pkg_json_path = "frontend/package.json"
    if pkg_json_path not in files:
        return files, []

    logs: list[str] = []
    try:
        pkg_data = json.loads(files[pkg_json_path])
    except (json.JSONDecodeError, TypeError):
        return files, ["Invalid frontend/package.json JSON format"]

    deps = dict(pkg_data.get("dependencies", {}))
    dev_deps = dict(pkg_data.get("devDependencies", {}))
    scripts = dict(pkg_data.get("scripts", {}))
    installed = set(deps.keys()) | set(dev_deps.keys())

    # 1. Check external source imports
    imported_packages = scan_source_imports(files)
    missing = imported_packages - installed

    modified_pkg = False

    for pkg in missing:
        version = _KNOWN_PACKAGES.get(pkg, "latest")
        deps[pkg] = version
        modified_pkg = True
        logs.append(f"Auto-added missing dependency '{pkg}' ({version}) to frontend/package.json")

    # 2. Check TypeScript node types consistency (BUG 4)
    tsconfig_node_path = "frontend/tsconfig.node.json"
    tsconfig_path = "frontend/tsconfig.json"
    requires_node_types = False

    for ts_path in (tsconfig_node_path, tsconfig_path):
        if ts_path in files:
            try:
                ts_data = json.loads(files[ts_path])
                types = ts_data.get("compilerOptions", {}).get("types", [])
                if "node" in types:
                    requires_node_types = True
                    break
            except Exception:
                pass

    if requires_node_types and "@types/node" not in installed:
        dev_deps["@types/node"] = "^20.17.0"
        modified_pkg = True
        logs.append("Added '@types/node' to devDependencies to satisfy tsconfig 'types': ['node']")

    # 3. Check ESLint configuration consistency (BUG 5)
    lint_script = scripts.get("lint", "")
    if "eslint" in lint_script:
        has_eslint = "eslint" in installed
        has_eslint_config = any(
            f in files
            for f in (
                "frontend/.eslintrc",
                "frontend/.eslintrc.js",
                "frontend/.eslintrc.json",
                "frontend/.eslintrc.cjs",
                "frontend/eslint.config.js",
                "frontend/eslint.config.mjs",
            )
        )
        if not has_eslint or not has_eslint_config:
            del scripts["lint"]
            modified_pkg = True
            logs.append("Removed broken 'lint' script from package.json because eslint is not installed/configured")

    if modified_pkg:
        pkg_data["dependencies"] = dict(sorted(deps.items()))
        pkg_data["devDependencies"] = dict(sorted(dev_deps.items()))
        pkg_data["scripts"] = scripts
        files[pkg_json_path] = json.dumps(pkg_data, indent=2) + "\n"

    # 4. Check utils.ts for clean implementation
    utils_path = "frontend/src/lib/utils.ts"
    if utils_path in files:
        utils_content = files[utils_path]
        if "clsx" in utils_content and "clsx" not in deps:
            files[utils_path] = (
                "export function cn(...inputs: any[]): string {\n"
                "  return inputs.flat().filter(Boolean).join(' ');\n"
                "}\n"
            )
            logs.append("Replaced utils.ts with pure TypeScript class joiner")

    return files, logs
