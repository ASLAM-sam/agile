"""Next.js (App Router) frontend adapter."""

from __future__ import annotations

import json

from app.adapters.base import FrontendAdapter, ScaffoldContext, ScaffoldFile


class NextJSAdapter(FrontendAdapter):
    key = "nextjs"
    display_name = "Next.js"
    language = "TypeScript"
    version = "15.0"
    description = (
        "Full-stack React framework with server components, file-based routing "
        "and built-in SSR/SSG. Strong defaults for SEO and initial load."
    )
    tags = ("react", "ssr", "app-router", "typescript", "seo")
    best_for = (
        "Public, SEO-sensitive sites",
        "Marketing and content-heavy products",
        "Apps that benefit from server-side rendering",
    )
    source_dir = "frontend/src"

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        deps = {
            "next": "^15.0.3",
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
        }
        dev_deps = {
            "@types/node": "^22.9.0",
            "@types/react": "^18.3.12",
            "@types/react-dom": "^18.3.1",
            "autoprefixer": "^10.4.20",
            "postcss": "^8.4.49",
            "tailwindcss": "^3.4.15",
            "typescript": "^5.6.3",
            "eslint": "^9.15.0",
            "eslint-config-next": "^15.0.3",
        }

        package_json = {
            "name": f"{ctx.project_slug}-web",
            "private": True,
            "version": "0.1.0",
            "description": ctx.description[:180],
            "engines": {"node": ">=20"},
            "scripts": {
                "dev": f"next dev -p {ctx.web_port}",
                "build": "next build",
                "start": f"next start -p {ctx.web_port}",
                "lint": "next lint",
                "typecheck": "tsc --noEmit",
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
                path="frontend/next.config.mjs",
                description="Next.js build configuration.",
                content=f"""/** @type {{import('next').NextConfig}} */
const nextConfig = {{
  reactStrictMode: true,
  // `standalone` emits a minimal server bundle for the Docker runtime stage.
  output: 'standalone',
  async rewrites() {{
    return [
      {{
        source: '/api/:path*',
        destination: `${{process.env.API_BASE_URL ?? '{ctx.api_base_url}'}}/api/:path*`,
      }},
    ];
  }},
}};

export default nextConfig;
""",
            ),
            ScaffoldFile(
                path="frontend/tsconfig.json",
                description="TypeScript configuration for the Next.js app.",
                content=json.dumps(
                    {
                        "compilerOptions": {
                            "target": "ES2022",
                            "lib": ["dom", "dom.iterable", "esnext"],
                            "allowJs": True,
                            "skipLibCheck": True,
                            "strict": True,
                            "noUncheckedIndexedAccess": True,
                            "noEmit": True,
                            "esModuleInterop": True,
                            "module": "esnext",
                            "moduleResolution": "bundler",
                            "resolveJsonModule": True,
                            "isolatedModules": True,
                            "jsx": "preserve",
                            "incremental": True,
                            "plugins": [{"name": "next"}],
                            "paths": {"@/*": ["./src/*"]},
                        },
                        "include": [
                            "next-env.d.ts",
                            "**/*.ts",
                            "**/*.tsx",
                            ".next/types/**/*.ts",
                        ],
                        "exclude": ["node_modules"],
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/tailwind.config.ts",
                description="TailwindCSS configuration with the project design tokens.",
                content="""import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
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
    },
  },
  plugins: [],
};

export default config;
""",
            ),
            ScaffoldFile(
                path="frontend/postcss.config.mjs",
                description="PostCSS pipeline for Tailwind and autoprefixer.",
                content="/** @type {import('postcss-load-config').Config} */\n"
                "const config = {\n  plugins: {\n    tailwindcss: {},\n"
                "    autoprefixer: {},\n  },\n};\n\nexport default config;\n",
            ),
            ScaffoldFile(
                path="frontend/next-env.d.ts",
                description="Next.js ambient type references.",
                content="/// <reference types=\"next\" />\n"
                '/// <reference types="next/image-types/global" />\n\n'
                "// NOTE: This file should not be edited.\n",
            ),
            ScaffoldFile(
                path="frontend/.env.example",
                description="Documented frontend environment variables. Copy to `.env.local`.",
                content=(
                    "# Server-side base URL used by the rewrite proxy.\n"
                    f"API_BASE_URL={ctx.api_base_url}\n\n"
                    "# Browser-visible base URL. Leave as /api to use the rewrite.\n"
                    "NEXT_PUBLIC_API_BASE_URL=/api\n"
                ),
            ),
            ScaffoldFile(
                path="frontend/Dockerfile",
                description="Multi-stage image using the Next.js standalone output.",
                content=self.dockerfile(ctx),
            ),
            ScaffoldFile(
                path="frontend/.dockerignore",
                description="Build-context exclusions.",
                content="node_modules/\n.next/\n.env*\n*.log\n.git/\n",
            ),
        ]

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        return f"""# syntax=docker/dockerfile:1

FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT={ctx.web_port}
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# `output: 'standalone'` produces a self-contained server bundle.
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE {ctx.web_port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \\
    CMD wget -q --spider http://localhost:{ctx.web_port}/ || exit 1

CMD ["node", "server.js"]
"""

    def compose_service(self, ctx: ScaffoldContext) -> dict:
        return {
            "build": {"context": "./frontend"},
            "ports": [f"{ctx.web_port}:{ctx.web_port}"],
            "environment": {"API_BASE_URL": f"http://api:{ctx.api_port}"},
            "depends_on": ["api"] if ctx.needs_backend else [],
        }

    def conventions(self, ctx: ScaffoldContext) -> str:
        sections = [
            "Next.js 15 App Router + TypeScript + TailwindCSS conventions. Generated "
            "code MUST follow these exactly.",
            "",
            "## Layout — every file goes under `frontend/src/`",
            "```",
            "frontend/src/",
            "  app/layout.tsx          Root layout: <html>, <body>, providers, metadata",
            "  app/page.tsx            Home route",
            "  app/globals.css         Tailwind directives and CSS custom properties",
            "  app/<segment>/page.tsx  One folder per route segment",
            "  app/<segment>/loading.tsx  Streaming skeleton for that segment",
            "  app/<segment>/error.tsx    Error boundary ('use client' required)",
            "  components/ui/          Presentational primitives",
            "  components/layout/      Shell pieces (Nav, Footer)",
            "  lib/api.ts              Typed fetch helpers",
            "  types/<domain>.ts       Shared TypeScript interfaces",
            "```",
            "",
            "## Non-negotiable rules",
            "1. Components are **Server Components by default**. Add `'use client'` as "
            "the first line only when the component uses state, effects, browser APIs "
            "or event handlers. Adding it unnecessarily forfeits the framework's main "
            "advantage.",
            "2. Never call a React hook in a file without `'use client'` — it will fail "
            "at build time.",
            "3. `error.tsx` must always be a client component.",
            "4. Routing is file-based. Do not install or use `react-router-dom`.",
            "5. Every `page.tsx` exports a `metadata` object (or `generateMetadata`) "
            "with a title and description.",
            "6. Use `next/link` for internal navigation and `next/image` for images — "
            "never a bare `<a>` for an internal route or a bare `<img>`.",
            "7. `strict` TypeScript. No `any`. Props interfaces are named "
            "`<Component>Props`.",
            "8. Styling is Tailwind utility classes only.",
            "9. Every interactive element is keyboard-operable, has an accessible name, "
            "and shows a visible focus ring.",
        ]
        if ctx.needs_backend:
            sections += [
                "",
                "## Data fetching",
                "- Prefer fetching in Server Components with `async` page functions; "
                "this avoids shipping data-fetching code to the browser.",
                "- Set an explicit caching intent on every `fetch`: "
                "`{ cache: 'no-store' }` for per-request data or "
                "`{ next: { revalidate: N } }` for time-based revalidation.",
                "- Client-side fetching goes through `lib/api.ts` and calls `/api/...`, "
                "which the configured rewrite proxies to the backend.",
                "- Every data-loading route provides `loading.tsx` and `error.tsx`.",
            ]
        if ctx.needs_auth:
            sections += [
                "",
                "## Authentication",
                "- Store the session token in an httpOnly cookie set by a Route Handler, "
                "not in `localStorage` — Server Components cannot read `localStorage`.",
                "- Guard protected segments in `middleware.ts` at the project root.",
                "- Read the session in Server Components via `cookies()` from "
                "`next/headers`.",
            ]
        sections += [
            "",
            "## Do not generate",
            "`package.json`, `next.config.mjs`, `tsconfig.json`, `tailwind.config.ts`, "
            "`postcss.config.mjs`, `next-env.d.ts`, `Dockerfile` — these already exist "
            "in the scaffold and must not be recreated or modified. You MUST generate "
            "`src/app/globals.css` with the three Tailwind directives.",
        ]
        return "\n".join(sections)
