"""Express.js backend adapter (TypeScript)."""

from __future__ import annotations

import json

from app.adapters.base import BackendAdapter, ScaffoldContext, ScaffoldFile


class ExpressAdapter(BackendAdapter):
    key = "express"
    display_name = "Express.js"
    language = "TypeScript"
    version = "4.21"
    description = (
        "Minimal, unopinionated Node.js web framework. Shares a language with the "
        "frontend, keeping one toolchain across the stack."
    )
    tags = ("node", "typescript", "javascript", "lightweight")
    best_for = (
        "Full-TypeScript teams",
        "Realtime and streaming APIs",
        "Projects that value a single language across client and server",
    )
    supported_databases = ("postgresql", "mysql", "sqlite")

    _DRIVERS = {
        "postgresql": {"pg": "^8.13.1", "@types/pg": "^8.11.10"},
        "mysql": {"mysql2": "^3.11.4"},
        "sqlite": {"better-sqlite3": "^11.5.0", "@types/better-sqlite3": "^7.6.11"},
    }

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        deps: dict[str, str] = {
            "express": "^4.21.1",
            "cors": "^2.8.5",
            "helmet": "^8.0.0",
            "dotenv": "^16.4.5",
            "zod": "^3.23.8",
        }
        dev_deps: dict[str, str] = {
            "@types/express": "^5.0.0",
            "@types/cors": "^2.8.17",
            "@types/node": "^22.9.0",
            "typescript": "^5.6.3",
            "tsx": "^4.19.2",
            "vitest": "^2.1.5",
            "supertest": "^7.0.0",
            "@types/supertest": "^6.0.2",
        }

        if ctx.needs_database:
            driver = self._DRIVERS.get(ctx.database_key or "sqlite", {})
            for name, spec in driver.items():
                (dev_deps if name.startswith("@types/") else deps)[name] = spec
        if ctx.needs_auth:
            deps["jsonwebtoken"] = "^9.0.2"
            deps["bcryptjs"] = "^2.4.3"
            dev_deps["@types/jsonwebtoken"] = "^9.0.7"
            dev_deps["@types/bcryptjs"] = "^2.4.6"

        package_json = {
            "name": f"{ctx.project_slug}-api",
            "version": "0.1.0",
            "private": True,
            "description": ctx.description[:180],
            "type": "module",
            "engines": {"node": ">=20"},
            "scripts": {
                "dev": "tsx watch src/server.ts",
                "build": "tsc -p tsconfig.json",
                "start": "node dist/server.js",
                "test": "vitest run",
                "test:watch": "vitest",
                "typecheck": "tsc --noEmit",
            },
            "dependencies": dict(sorted(deps.items())),
            "devDependencies": dict(sorted(dev_deps.items())),
        }

        return [
            ScaffoldFile(
                path="backend/package.json",
                description="Node package manifest with pinned dependencies.",
                content=json.dumps(package_json, indent=2) + "\n",
            ),
            ScaffoldFile(
                path="backend/tsconfig.json",
                description="TypeScript compiler configuration (strict).",
                content=json.dumps(
                    {
                        "compilerOptions": {
                            "target": "ES2022",
                            "module": "ESNext",
                            "moduleResolution": "bundler",
                            "lib": ["ES2022"],
                            "outDir": "./dist",
                            "rootDir": "./src",
                            "strict": True,
                            "noUncheckedIndexedAccess": True,
                            "noImplicitOverride": True,
                            "esModuleInterop": True,
                            "skipLibCheck": True,
                            "forceConsistentCasingInFileNames": True,
                            "resolveJsonModule": True,
                            "declaration": True,
                            "sourceMap": True,
                        },
                        "include": ["src/**/*.ts"],
                        "exclude": ["node_modules", "dist", "**/*.test.ts"],
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="backend/Dockerfile",
                description="Multi-stage production container image for the API.",
                content=self.dockerfile(ctx),
            ),
            ScaffoldFile(
                path="backend/.dockerignore",
                description="Build-context exclusions.",
                content="node_modules/\ndist/\n.env\n*.log\n.git/\ncoverage/\n",
            ),
            ScaffoldFile(
                path="backend/.env.example",
                description="Documented environment variables. Copy to `.env`.",
                content=self.env_template(ctx, self._database_url(ctx)),
            ),
        ]

    def _database_url(self, ctx: ScaffoldContext) -> str:
        if not ctx.needs_database:
            return ""
        if ctx.database_key == "sqlite":
            return f"./{ctx.package_name}.db"
        if ctx.database_key == "mysql":
            return (
                f"mysql://{ctx.package_name}:{ctx.package_name}_password"
                f"@localhost:3306/{ctx.package_name}"
            )
        return (
            f"postgresql://{ctx.package_name}:{ctx.package_name}_password"
            f"@localhost:5432/{ctx.package_name}"
        )

    def env_template(self, ctx: ScaffoldContext, database_url: str) -> str:
        lines = [
            "# Application",
            "NODE_ENV=development",
            f"PORT={ctx.api_port}",
            "LOG_LEVEL=info",
            "",
            "# CORS — comma-separated origins allowed to call this API",
            f"CORS_ORIGINS=http://localhost:{ctx.web_port}",
        ]
        if ctx.needs_database:
            lines += ["", "# Database", f"DATABASE_URL={database_url}"]
        if ctx.needs_auth:
            lines += [
                "",
                "# Authentication",
                "# Generate with: node -e \"console.log(require('crypto')"
                '.randomBytes(48).toString(\'base64url\'))"',
                "JWT_SECRET=change-me-before-deploying",
                "JWT_EXPIRES_IN=12h",
            ]
        return "\n".join(lines) + "\n"

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        return f"""# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist

USER node
EXPOSE {ctx.api_port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD node -e "fetch('http://localhost:{ctx.api_port}/health') \\
.then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "dist/server.js"]
"""

    def conventions(self, ctx: ScaffoldContext) -> str:
        sections = [
            "Express.js + TypeScript backend conventions. Generated code MUST follow "
            "these exactly.",
            "",
            "## Layout — every file goes under `backend/src/`",
            "```",
            "backend/src/",
            "  server.ts               Process entrypoint: reads config, starts listener",
            "  app.ts                  Builds and exports the Express app (testable)",
            "  config/index.ts         Typed, validated environment configuration",
            "  routes/index.ts         Mounts every resource router under /api/v1",
            "  routes/<res>.routes.ts  One router per resource, thin HTTP layer only",
            "  controllers/<res>.controller.ts  Request/response handling",
            "  services/<res>.service.ts        Business logic, no Express imports",
        ]
        if ctx.needs_database:
            sections += [
                "  repositories/<res>.repository.ts  All SQL lives here",
                "  db/index.ts             Connection pool + query helper",
            ]
        sections += [
            "  middleware/errorHandler.ts   Central error-to-response mapping",
            "  middleware/validate.ts       Zod schema validation middleware",
        ]
        if ctx.needs_auth:
            sections.append("  middleware/auth.ts           JWT verification middleware")
        sections += [
            "  types/<res>.types.ts    Shared TypeScript interfaces",
            "  utils/AppError.ts       Typed application error class",
            "```",
            "",
            "## Non-negotiable rules",
            "1. ESM only. Every relative import ends in `.js` "
            "(`import { x } from './service.js'`) because the compiled output is ESM. "
            "This is the single most common failure in TypeScript ESM projects.",
            "2. `strict` TypeScript. No `any`. Use `unknown` plus narrowing where a type "
            "is genuinely unknown.",
            "3. Layering is strict: routes -> controllers -> services -> repositories. "
            "A service never imports from `express`.",
            "4. Every request body, query and route param is validated with a Zod schema "
            "before it reaches a controller.",
            "5. Async handlers are wrapped so rejections reach the error middleware — "
            "Express 4 does not forward async errors automatically.",
            "6. Throw `AppError` with an explicit status code; the error middleware is "
            "the only place that formats an error response.",
            "7. `app.ts` exports the configured app without calling `listen`; "
            "`server.ts` performs the listen. This keeps the app testable with supertest.",
            "8. Configuration is read once in `config/index.ts` and validated with Zod. "
            "Never call `process.env` elsewhere.",
            "9. `helmet()` and a configured `cors()` are applied before any route.",
        ]
        if ctx.needs_database:
            driver = {
                "postgresql": "`pg` with a `Pool`, parameterised `$1, $2` placeholders",
                "mysql": "`mysql2/promise` with a pool, parameterised `?` placeholders",
                "sqlite": "`better-sqlite3`, parameterised `?` placeholders",
            }.get(ctx.database_key or "sqlite", "the configured driver")
            sections += [
                "",
                "## Database",
                f"- Use {driver}.",
                "- Every query is parameterised. String concatenation into SQL is "
                "forbidden without exception.",
                "- Repositories own all SQL and return typed domain objects, never raw "
                "driver rows.",
                "- Queries must match the SQL schema already produced for this project.",
            ]
        if ctx.needs_auth:
            sections += [
                "",
                "## Authentication",
                "- Hash passwords with `bcryptjs` (cost factor 10 or higher).",
                "- Sign JWTs with `jsonwebtoken` using `JWT_SECRET` from config.",
                "- `middleware/auth.ts` verifies the bearer token and attaches the user "
                "to `req`; declare the augmented `Request` type explicitly.",
                "- Never return a password hash in any response body.",
            ]
        sections += [
            "",
            "## Do not generate",
            "`package.json`, `tsconfig.json`, `Dockerfile`, `.env.example` — these "
            "already exist in the scaffold and must not be recreated or modified.",
        ]
        return "\n".join(sections)
