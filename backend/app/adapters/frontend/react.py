"""React + TypeScript + Vite frontend adapter."""

from __future__ import annotations

import json

from app.adapters.base import FrontendAdapter, ScaffoldContext, ScaffoldFile


class ReactAdapter(FrontendAdapter):
    key = "react"
    display_name = "React"
    language = "TypeScript"
    version = "18.3"
    description = (
        "Component-driven UI library with the largest ecosystem. Paired with Vite "
        "for near-instant dev startup and TailwindCSS for styling."
    )
    tags = ("spa", "typescript", "vite", "tailwind")
    best_for = (
        "Dashboards and admin panels",
        "Highly interactive single-page applications",
        "Teams wanting maximum library availability",
    )

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        deps = {
            "clsx": "^2.1.1",
            "lucide-react": "^0.460.0",
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
            "react-router-dom": "^6.28.0",
            "tailwind-merge": "^2.5.4",
        }
        dev_deps = {
            "@types/node": "^20.17.0",
            "@types/react": "^18.3.12",
            "@types/react-dom": "^18.3.1",
            "@vitejs/plugin-react": "^4.3.3",
            "autoprefixer": "^10.4.20",
            "postcss": "^8.4.49",
            "tailwindcss": "^3.4.15",
            "typescript": "^5.6.3",
            "vite": "^5.4.11",
            "vitest": "^2.1.5",
            "jsdom": "^25.0.1",
            "@testing-library/react": "^16.0.1",
            "@testing-library/jest-dom": "^6.6.3",
        }

        package_json = {
            "name": f"{ctx.project_slug}-web",
            "private": True,
            "version": "0.1.0",
            "description": ctx.description[:180],
            "type": "module",
            "engines": {"node": ">=20"},
            "scripts": {
                "dev": f"vite --port {ctx.web_port}",
                "build": "tsc -b && vite build",
                "preview": "vite preview",
                "test": "vitest run",
                "test:watch": "vitest",
                "typecheck": "tsc --noEmit -p tsconfig.app.json",
            },
            "dependencies": dict(sorted(deps.items())),
            "devDependencies": dict(sorted(dev_deps.items())),
        }

        return [
            ScaffoldFile(
                path="frontend/package.json",
                description="Node package manifest with pinned dependencies.",
                content=json.dumps(package_json, indent=2) + "\n",
            ),
            ScaffoldFile(
                path="frontend/vite.config.ts",
                description="Vite build and dev-server configuration.",
                content=f"""/// <reference types="vitest" />
import {{ defineConfig }} from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({{
  plugins: [react()],
  resolve: {{
    alias: {{ '@': path.resolve(__dirname, './src') }},
  }},
  server: {{
    port: {ctx.web_port},
    host: true,
    proxy: {{
      // Dev-only proxy so the browser sees same-origin requests and CORS
      // never enters the local development loop.
      '/api': {{
        target: '{ctx.api_base_url}',
        changeOrigin: true,
      }},
    }},
  }},
  build: {{
    outDir: 'dist',
    sourcemap: true,
  }},
  test: {{
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  }},
}});
""",
            ),
            ScaffoldFile(
                path="frontend/tsconfig.json",
                description="TypeScript project references root.",
                content=json.dumps(
                    {
                        "files": [],
                        "references": [
                            {"path": "./tsconfig.app.json"},
                            {"path": "./tsconfig.node.json"},
                        ],
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/tsconfig.app.json",
                description="Application TypeScript configuration (strict).",
                content=json.dumps(
                    {
                        "compilerOptions": {
                            "target": "ES2022",
                            "lib": ["ES2022", "DOM", "DOM.Iterable"],
                            "module": "ESNext",
                            "moduleResolution": "bundler",
                            "jsx": "react-jsx",
                            "strict": True,
                            "noUncheckedIndexedAccess": True,
                            "noUnusedLocals": True,
                            "noUnusedParameters": True,
                            "noFallthroughCasesInSwitch": True,
                            "skipLibCheck": True,
                            "esModuleInterop": True,
                            "allowImportingTsExtensions": True,
                            "resolveJsonModule": True,
                            "isolatedModules": True,
                            "noEmit": True,
                            "types": ["vitest/globals"],
                            "baseUrl": ".",
                            "paths": {"@/*": ["./src/*"]},
                        },
                        "include": ["src"],
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/tsconfig.node.json",
                description="TypeScript configuration for Vite config files.",
                content=json.dumps(
                    {
                        "compilerOptions": {
                            "target": "ES2022",
                            "lib": ["ES2023"],
                            "module": "ESNext",
                            "moduleResolution": "bundler",
                            "types": ["node", "vitest/globals"],
                            "strict": True,
                            "skipLibCheck": True,
                            "isolatedModules": True,
                            "noEmit": True,
                        },
                        "include": ["vite.config.ts"],
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/tailwind.config.js",
                description="TailwindCSS configuration with the project design tokens.",
                content="""/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef6ff',
          100: '#d9eaff',
          200: '#bcdaff',
          300: '#8ec3ff',
          400: '#59a1ff',
          500: '#337dff',
          600: '#1c5cf5',
          700: '#1547e1',
          800: '#183cb6',
          900: '#1a378f',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
""",
            ),
            ScaffoldFile(
                path="frontend/postcss.config.js",
                description="PostCSS pipeline for Tailwind and autoprefixer.",
                content="export default {\n  plugins: {\n    tailwindcss: {},\n"
                "    autoprefixer: {},\n  },\n};\n",
            ),
            ScaffoldFile(
                path="frontend/index.html",
                description="HTML entry document.",
                content=f"""<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="{ctx.description[:150]}" />
    <title>{ctx.project_name}</title>
  </head>
  <body class="bg-slate-950 text-slate-100 antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
            ),
            ScaffoldFile(
                path="frontend/src/test/setup.ts",
                description="Vitest setup importing jest-dom matchers.",
                content="import '@testing-library/jest-dom';\n",
            ),
            ScaffoldFile(
                path="frontend/src/main.tsx",
                description="Client entrypoint mounting the root React application.",
                content="""import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
""",
            ),
            ScaffoldFile(
                path="frontend/src/index.css",
                description="Global Tailwind styles and typography directives.",
                content="""@tailwind base;
@tailwind components;
@tailwind utilities;
""",
            ),
            ScaffoldFile(
                path="frontend/src/App.tsx",
                description="Root application shell component.",
                content=f"""import React from 'react';

export default function App(): JSX.Element {{
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6">
      <h1 className="text-3xl font-bold text-brand-400">{ctx.project_name}</h1>
      <p className="mt-2 text-slate-400">{ctx.description}</p>
    </div>
  );
}}
""",
            ),
            ScaffoldFile(
                path="frontend/.env.example",
                description="Documented frontend environment variables. Copy to `.env`.",
                content=(
                    "# Base URL of the API. Leave empty to use the Vite dev proxy.\n"
                    f"VITE_API_BASE_URL={ctx.api_base_url if ctx.needs_backend else ''}\n"
                ),
            ),
            ScaffoldFile(
                path="frontend/Dockerfile",
                description="Multi-stage image serving the built SPA via nginx.",
                content=self.dockerfile(ctx),
            ),
            ScaffoldFile(
                path="frontend/nginx.conf",
                description="nginx config with SPA history fallback.",
                content="""server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    # Hashed build assets are immutable.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Client-side routing: unknown paths return the app shell.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
""",
            ),
            ScaffoldFile(
                path="frontend/.dockerignore",
                description="Build-context exclusions.",
                content="node_modules/\ndist/\n.env\n*.log\n.git/\ncoverage/\n",
            ),
        ]

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        return """# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
    CMD wget -q --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
"""

    def compose_service(self, ctx: ScaffoldContext) -> dict:
        return {
            "build": {"context": "./frontend"},
            "ports": [f"{ctx.web_port}:80"],
            "depends_on": ["api"] if ctx.needs_backend else [],
        }

    def conventions(self, ctx: ScaffoldContext) -> str:
        sections = [
            "React 18 + TypeScript + Vite + TailwindCSS conventions. Generated code "
            "MUST follow these exactly.",
            "",
            "## Layout — every file goes under `frontend/src/`",
            "```",
            "frontend/src/",
            "  main.tsx                Root render; mounts <App/> in StrictMode",
            "  App.tsx                 Router definition and layout composition",
            "  index.css               Tailwind directives and CSS custom properties",
            "  pages/<Name>Page.tsx    One component per route",
            "  components/ui/          Presentational primitives (Button, Card, Input)",
            "  components/layout/      Shell pieces (Sidebar, Header, PageContainer)",
            "  hooks/use<Name>.ts      Reusable stateful logic",
            "  types/<domain>.ts       Shared TypeScript interfaces",
            "  lib/utils.ts            Pure helpers (formatters, class merging)",
        ]
        if ctx.needs_backend:
            sections += [
                "  api/client.ts           Single fetch wrapper: base URL, headers, errors",
                "  api/<resource>.ts       Typed functions per resource",
            ]
        if ctx.needs_auth:
            sections += [
                "  context/AuthContext.tsx  Auth provider + useAuth hook",
                "  components/ProtectedRoute.tsx  Redirects unauthenticated users",
            ]
        sections += [
            "```",
            "",
            "## Non-negotiable rules",
            "1. Function components with typed props interfaces. No class components, "
            "no `React.FC`.",
            "2. `strict` TypeScript. No `any`. Props interfaces are named `<Component>Props`.",
            "3. Styling is Tailwind utility classes only. No inline `style` objects, no "
            "CSS-in-JS, no per-component `.css` files.",
            "4. Every interactive element is reachable and operable by keyboard, has an "
            "accessible name, and shows a visible focus ring "
            "(`focus-visible:ring-2 focus-visible:ring-brand-500`).",
            "5. Responsive by default: design mobile-first, then layer `sm: md: lg:` "
            "breakpoints.",
            "6. Import via the `@/` alias for anything outside the current folder.",
            "7. Every list render supplies a stable `key` — never the array index when "
            "the list can reorder.",
            "8. Extract shared markup into `components/ui/`. Do not copy a block of JSX "
            "into a second file.",
        ]
        if ctx.needs_backend:
            sections += [
                "",
                "## Data fetching",
                "- All network calls go through `api/client.ts`. No component calls "
                "`fetch` directly.",
                "- The client reads `import.meta.env.VITE_API_BASE_URL` and falls back "
                "to `/api` so the Vite dev proxy works with no configuration.",
                "- Non-2xx responses throw a typed `ApiError` carrying status and "
                "message.",
                "- Every data-loading view renders three states explicitly: loading, "
                "error (with a retry affordance) and empty. A view that only handles "
                "the success path is incomplete.",
                "- Response types are declared in `types/` and reused; never inline an "
                "anonymous response shape at a call site.",
            ]
        if ctx.needs_auth:
            sections += [
                "",
                "## Authentication",
                "- `AuthContext` holds the token and current user, persists the token to "
                "`localStorage`, and rehydrates on mount.",
                "- `api/client.ts` attaches `Authorization: Bearer <token>` when present.",
                "- A 401 response clears the session and redirects to `/login`.",
                "- `ProtectedRoute` wraps authenticated routes.",
            ]
        sections += [
            "",
            "## Do not generate",
            "`package.json`, `vite.config.ts`, `tsconfig*.json`, `tailwind.config.js`, "
            "`postcss.config.js`, `index.html`, `Dockerfile`, `nginx.conf` — these "
            "already exist in the scaffold and must not be recreated or modified. "
            "You MUST generate `src/index.css` with the three Tailwind directives.",
        ]
        return "\n".join(sections)
