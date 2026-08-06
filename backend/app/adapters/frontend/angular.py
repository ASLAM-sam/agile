"""Angular frontend adapter."""

from __future__ import annotations

import json

from app.adapters.base import FrontendAdapter, ScaffoldContext, ScaffoldFile


class AngularAdapter(FrontendAdapter):
    key = "angular"
    display_name = "Angular"
    language = "TypeScript"
    version = "18.2"
    description = (
        "Batteries-included framework with dependency injection, RxJS and a "
        "prescriptive structure. Strong fit for large, long-lived applications."
    )
    tags = ("spa", "typescript", "rxjs", "enterprise")
    best_for = (
        "Large teams needing enforced structure",
        "Long-lived enterprise applications",
        "Complex forms and data-entry workflows",
    )
    source_dir = "frontend/src/app"

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        deps = {
            "@angular/animations": "^18.2.0",
            "@angular/common": "^18.2.0",
            "@angular/compiler": "^18.2.0",
            "@angular/core": "^18.2.0",
            "@angular/forms": "^18.2.0",
            "@angular/platform-browser": "^18.2.0",
            "@angular/platform-browser-dynamic": "^18.2.0",
            "@angular/router": "^18.2.0",
            "rxjs": "~7.8.0",
            "tslib": "^2.7.0",
            "zone.js": "~0.14.10",
        }
        dev_deps = {
            "@angular-devkit/build-angular": "^18.2.0",
            "@angular/cli": "^18.2.0",
            "@angular/compiler-cli": "^18.2.0",
            "@types/jasmine": "~5.1.0",
            "autoprefixer": "^10.4.20",
            "jasmine-core": "~5.4.0",
            "karma": "~6.4.0",
            "karma-chrome-launcher": "~3.2.0",
            "karma-coverage": "~2.2.0",
            "karma-jasmine": "~5.1.0",
            "karma-jasmine-html-reporter": "~2.1.0",
            "postcss": "^8.4.49",
            "tailwindcss": "^3.4.15",
            "typescript": "~5.5.4",
        }

        package_json = {
            "name": f"{ctx.project_slug}-web",
            "version": "0.1.0",
            "private": True,
            "description": ctx.description[:180],
            "engines": {"node": ">=20"},
            "scripts": {
                "ng": "ng",
                "dev": f"ng serve --port {ctx.web_port}",
                "start": f"ng serve --port {ctx.web_port}",
                "build": "ng build",
                "watch": "ng build --watch --configuration development",
                "test": "ng test --watch=false --browsers=ChromeHeadless",
            },
            "dependencies": dict(sorted(deps.items())),
            "devDependencies": dict(sorted(dev_deps.items())),
        }

        angular_json = {
            "$schema": "./node_modules/@angular/cli/lib/config/schema.json",
            "version": 1,
            "newProjectRoot": "projects",
            "projects": {
                f"{ctx.project_slug}-web": {
                    "projectType": "application",
                    "root": "",
                    "sourceRoot": "src",
                    "prefix": "app",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:application",
                            "options": {
                                "outputPath": "dist",
                                "index": "src/index.html",
                                "browser": "src/main.ts",
                                "polyfills": ["zone.js"],
                                "tsConfig": "tsconfig.app.json",
                                "assets": [
                                    {
                                        "glob": "**/*",
                                        "input": "public",
                                    }
                                ],
                                "styles": ["src/styles.css"],
                            },
                            "configurations": {
                                "production": {
                                    "budgets": [
                                        {
                                            "type": "initial",
                                            "maximumWarning": "500kB",
                                            "maximumError": "1MB",
                                        }
                                    ],
                                    "outputHashing": "all",
                                },
                                "development": {
                                    "optimization": False,
                                    "sourceMap": True,
                                },
                            },
                            "defaultConfiguration": "production",
                        },
                        "serve": {
                            "builder": "@angular-devkit/build-angular:dev-server",
                            "configurations": {
                                "production": {
                                    "buildTarget": f"{ctx.project_slug}-web:build:production"
                                },
                                "development": {
                                    "buildTarget": f"{ctx.project_slug}-web:build:development"
                                },
                            },
                            "defaultConfiguration": "development",
                            "options": {"proxyConfig": "proxy.conf.json"},
                        },
                        "test": {
                            "builder": "@angular-devkit/build-angular:karma",
                            "options": {
                                "polyfills": ["zone.js", "zone.js/testing"],
                                "tsConfig": "tsconfig.spec.json",
                                "styles": ["src/styles.css"],
                            },
                        },
                    },
                }
            },
        }

        return [
            ScaffoldFile(
                path="frontend/package.json",
                description="Node package manifest with pinned dependencies.",
                content=json.dumps(package_json, indent=2) + "\n",
            ),
            ScaffoldFile(
                path="frontend/angular.json",
                description="Angular CLI workspace configuration.",
                content=json.dumps(angular_json, indent=2) + "\n",
            ),
            ScaffoldFile(
                path="frontend/tsconfig.json",
                description="Base TypeScript configuration (strict).",
                content=json.dumps(
                    {
                        "compileOnSave": False,
                        "compilerOptions": {
                            "outDir": "./dist/out-tsc",
                            "strict": True,
                            "noImplicitOverride": True,
                            "noPropertyAccessFromIndexSignature": True,
                            "noImplicitReturns": True,
                            "noFallthroughCasesInSwitch": True,
                            "skipLibCheck": True,
                            "esModuleInterop": True,
                            "sourceMap": True,
                            "declaration": False,
                            "experimentalDecorators": True,
                            "moduleResolution": "bundler",
                            "importHelpers": True,
                            "target": "ES2022",
                            "module": "ES2022",
                            "lib": ["ES2022", "dom"],
                            "paths": {"@/*": ["./src/app/*"]},
                        },
                        "angularCompilerOptions": {
                            "enableI18nLegacyMessageIdFormat": False,
                            "strictInjectionParameters": True,
                            "strictInputAccessModifiers": True,
                            "strictTemplates": True,
                        },
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/tsconfig.app.json",
                description="Application build TypeScript configuration.",
                content=json.dumps(
                    {
                        "extends": "./tsconfig.json",
                        "compilerOptions": {"outDir": "./out-tsc/app", "types": []},
                        "files": ["src/main.ts"],
                        "include": ["src/**/*.d.ts"],
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/tsconfig.spec.json",
                description="Unit-test TypeScript configuration.",
                content=json.dumps(
                    {
                        "extends": "./tsconfig.json",
                        "compilerOptions": {
                            "outDir": "./out-tsc/spec",
                            "types": ["jasmine"],
                        },
                        "include": ["src/**/*.spec.ts", "src/**/*.d.ts"],
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/proxy.conf.json",
                description="Dev-server proxy so the browser sees same-origin requests.",
                content=json.dumps(
                    {
                        "/api": {
                            "target": ctx.api_base_url,
                            "secure": False,
                            "changeOrigin": True,
                        }
                    },
                    indent=2,
                )
                + "\n",
            ),
            ScaffoldFile(
                path="frontend/tailwind.config.js",
                description="TailwindCSS configuration with the project design tokens.",
                content="""/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
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
""",
            ),
            ScaffoldFile(
                path="frontend/postcss.config.js",
                description="PostCSS pipeline for Tailwind and autoprefixer.",
                content="module.exports = {\n  plugins: {\n    tailwindcss: {},\n"
                "    autoprefixer: {},\n  },\n};\n",
            ),
            ScaffoldFile(
                path="frontend/src/index.html",
                description="HTML entry document.",
                content=f"""<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="utf-8" />
    <title>{ctx.project_name}</title>
    <base href="/" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="{ctx.description[:150]}" />
  </head>
  <body class="bg-slate-950 text-slate-100 antialiased">
    <app-root></app-root>
  </body>
</html>
""",
            ),
            ScaffoldFile(
                path="frontend/public/.gitkeep",
                description="Static asset directory placeholder.",
                content="",
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

    location / {
        try_files $uri $uri/ /index.html;
    }
}
""",
            ),
            ScaffoldFile(
                path="frontend/.dockerignore",
                description="Build-context exclusions.",
                content="node_modules/\ndist/\n.angular/\n*.log\n.git/\n",
            ),
            ScaffoldFile(
                path="frontend/.env.example",
                description="Documented frontend environment variables.",
                content=(
                    "# Angular reads configuration from src/environments/*.ts, not from\n"
                    "# process.env. This file documents the values used at build time.\n"
                    f"API_BASE_URL={ctx.api_base_url}\n"
                ),
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
# The Angular application builder emits browser assets under dist/browser.
COPY --from=build /app/dist/browser /usr/share/nginx/html
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
            "Angular 18 + TypeScript + TailwindCSS conventions. Generated code MUST "
            "follow these exactly.",
            "",
            "## Layout — every file goes under `frontend/src/`",
            "```",
            "frontend/src/",
            "  main.ts                 bootstrapApplication(AppComponent, appConfig)",
            "  styles.css              Tailwind directives and global styles",
            "  app/app.component.ts    Root standalone component",
            "  app/app.config.ts       ApplicationConfig: providers and router",
            "  app/app.routes.ts       Route definitions",
            "  app/pages/<name>/       One folder per routed page component",
            "  app/components/<name>/  Reusable presentational components",
            "  app/services/<name>.service.ts   Injectable data services",
            "  app/models/<name>.model.ts       Interfaces and types",
            "  environments/environment.ts      Build-time configuration",
            "```",
            "",
            "## Non-negotiable rules",
            "1. **Standalone components only.** Every component sets "
            "`standalone: true` and declares its own `imports`. Do not generate "
            "`NgModule` classes — `app.module.ts` must not exist.",
            "2. Bootstrap with `bootstrapApplication()` in `main.ts`, never "
            "`platformBrowserDynamic().bootstrapModule()`.",
            "3. Dependency injection uses the `inject()` function or constructor "
            "parameters. Services are `@Injectable({ providedIn: 'root' })`.",
            "4. `strictTemplates` is on. Every template binding must type-check.",
            "5. Use the modern control-flow syntax `@if`, `@for`, `@switch` in "
            "templates rather than the older structural directives. Every `@for` "
            "declares a `track` expression.",
            "6. Components with only bound inputs set "
            "`changeDetection: ChangeDetectionStrategy.OnPush`.",
            "7. Styling is Tailwind utility classes in templates. Leave the "
            "component `styles` array empty.",
            "8. Unsubscribe from every long-lived subscription, or prefer the "
            "`async` pipe so the framework manages the lifecycle.",
            "9. Reactive forms (`FormBuilder`, `FormGroup`) for anything beyond a "
            "single input. Template-driven forms are not used.",
            "10. Every interactive element is keyboard-operable and has an "
            "accessible name.",
        ]
        if ctx.needs_backend:
            sections += [
                "",
                "## Data fetching",
                "- `provideHttpClient()` is registered in `app.config.ts`.",
                "- Services wrap `HttpClient` and return typed `Observable<T>`. "
                "Components never inject `HttpClient` directly.",
                "- The API base URL comes from `environments/environment.ts`; use "
                "`/api` so the configured dev proxy applies.",
                "- Handle errors with `catchError` and surface a typed error to the "
                "component.",
                "- Every data-loading view renders loading, error and empty states "
                "explicitly.",
            ]
        if ctx.needs_auth:
            sections += [
                "",
                "## Authentication",
                "- An `HttpInterceptorFn` registered via "
                "`provideHttpClient(withInterceptors([...]))` attaches the bearer "
                "token.",
                "- `AuthService` owns token storage and exposes the current user as "
                "an observable or signal.",
                "- Protect routes with a functional `CanActivateFn` guard.",
            ]
        sections += [
            "",
            "## Do not generate",
            "`package.json`, `angular.json`, `tsconfig*.json`, `tailwind.config.js`, "
            "`postcss.config.js`, `src/index.html`, `proxy.conf.json`, `Dockerfile`, "
            "`nginx.conf` — these already exist in the scaffold and must not be "
            "recreated or modified. You MUST generate `src/styles.css` with the three "
            "Tailwind directives.",
        ]
        return "\n".join(sections)
