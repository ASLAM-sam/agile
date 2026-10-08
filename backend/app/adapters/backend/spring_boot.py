"""Spring Boot backend adapter (Java)."""

from __future__ import annotations

from app.adapters.base import BackendAdapter, ScaffoldContext, ScaffoldFile


class SpringBootAdapter(BackendAdapter):
    key = "spring-boot"
    display_name = "Spring Boot"
    language = "Java"
    version = "3.4"
    description = (
        "Mature JVM framework with first-class dependency injection, transaction "
        "management and a deep enterprise ecosystem."
    )
    tags = ("java", "jvm", "enterprise", "spring")
    best_for = (
        "Enterprise and regulated environments",
        "Complex transactional domains",
        "Teams with existing JVM infrastructure",
    )
    supported_databases = ("mongodb", "sqlite")

    _JDBC = {
        "sqlite": {
            "artifact": "org.xerial:sqlite-jdbc:3.47.0.0",
            "scheme": "jdbc:sqlite:",
            "driver": "org.sqlite.JDBC",
            "dialect": "org.hibernate.community.dialect.SQLiteDialect",
        },
    }

    @property
    def base_package(self) -> str:
        return "com.example"

    def _java_package(self, ctx: ScaffoldContext) -> str:
        return f"{self.base_package}.{ctx.package_name.replace('_', '')}"

    def _package_path(self, ctx: ScaffoldContext) -> str:
        return self._java_package(ctx).replace(".", "/")

    def scaffold(self, ctx: ScaffoldContext) -> list[ScaffoldFile]:
        jdbc = self._JDBC.get(ctx.database_key or "sqlite", self._JDBC["sqlite"])
        package = self._java_package(ctx)

        db_deps = ""
        if ctx.needs_database and ctx.database_key == "mongodb":
            db_deps = "    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'\n"
        elif ctx.needs_database:
            db_deps = (
                "    implementation 'org.springframework.boot:"
                "spring-boot-starter-data-jpa'\n"
                "    implementation 'org.flywaydb:flyway-core'\n"
                f"    runtimeOnly '{jdbc['artifact']}'\n"
            )

        auth_deps = ""
        if ctx.needs_auth:
            auth_deps = (
                "    implementation 'org.springframework.boot:"
                "spring-boot-starter-security'\n"
                "    implementation 'io.jsonwebtoken:jjwt-api:0.12.6'\n"
                "    runtimeOnly 'io.jsonwebtoken:jjwt-impl:0.12.6'\n"
                "    runtimeOnly 'io.jsonwebtoken:jjwt-jackson:0.12.6'\n"
            )

        return [
            ScaffoldFile(
                path="backend/build.gradle",
                description="Gradle build script with pinned Spring Boot dependencies.",
                content=f"""plugins {{
    id 'java'
    id 'org.springframework.boot' version '3.4.0'
    id 'io.spring.dependency-management' version '1.1.6'
}}

group = '{self.base_package}'
version = '0.1.0'
description = '{ctx.description[:120]}'

java {{
    toolchain {{
        languageVersion = JavaLanguageVersion.of(21)
    }}
}}

repositories {{
    mavenCentral()
}}

dependencies {{
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
{db_deps}{auth_deps}
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}}

tasks.named('test') {{
    useJUnitPlatform()
}}

tasks.named('bootJar') {{
    archiveFileName = '{ctx.project_slug}-api.jar'
}}
""",
            ),
            ScaffoldFile(
                path="backend/settings.gradle",
                description="Gradle project name declaration.",
                content=f"rootProject.name = '{ctx.project_slug}-api'\n",
            ),
            ScaffoldFile(
                path="backend/src/main/resources/application.yml",
                description="Spring configuration with environment-variable overrides.",
                content=self._application_yml(ctx, jdbc),
            ),
            ScaffoldFile(
                path="backend/Dockerfile",
                description="Multi-stage JVM container image for the API.",
                content=self.dockerfile(ctx),
            ),
            ScaffoldFile(
                path="backend/.dockerignore",
                description="Build-context exclusions.",
                content="build/\n.gradle/\n.env\n*.log\n.git/\n",
            ),
            ScaffoldFile(
                path="backend/.env.example",
                description="Documented environment variables. Copy to `.env`.",
                content=self.env_template(ctx, self._database_url(ctx, jdbc)),
            ),
            ScaffoldFile(
                path=f"backend/src/main/java/{self._package_path(ctx)}/package-info.java",
                description="Root package declaration.",
                content=f"/** {ctx.project_name} API. */\npackage {package};\n",
            ),
        ]

    def _application_yml(self, ctx: ScaffoldContext, jdbc: dict[str, str]) -> str:
        lines = [
            "spring:",
            "  application:",
            f"    name: {ctx.project_slug}-api",
        ]
        if ctx.needs_database and ctx.database_key == "mongodb":
            lines += [
                "  data:",
                "    mongodb:",
                f"      uri: ${{MONGODB_URI:mongodb://localhost:27017/{ctx.package_name}}}",
            ]
        elif ctx.needs_database:
            url = f"{jdbc['scheme']}/{ctx.package_name}"
            if ctx.database_key == "sqlite":
                url = f"jdbc:sqlite:{ctx.package_name}.db"
            lines += [
                "  datasource:",
                f"    url: ${{DATABASE_URL:{url}}}",
                f"    username: ${{DATABASE_USER:{ctx.package_name}}}",
                f"    password: ${{DATABASE_PASSWORD:{ctx.package_name}_password}}",
                f"    driver-class-name: {jdbc['driver']}",
                "  jpa:",
                "    hibernate:",
                "      # Schema is owned by Flyway migrations, never by Hibernate.",
                "      ddl-auto: validate",
                "    open-in-view: false",
                "    properties:",
                "      hibernate:",
                f"        dialect: {jdbc['dialect']}",
                "        format_sql: true",
                "  flyway:",
                "    enabled: true",
                "    locations: classpath:db/migration",
                "    baseline-on-migrate: true",
            ]
        lines += [
            "",
            "server:",
            f"  port: ${{PORT:{ctx.api_port}}}",
            "",
            "management:",
            "  endpoints:",
            "    web:",
            "      exposure:",
            "        include: health,info",
            "  endpoint:",
            "    health:",
            "      probes:",
            "        enabled: true",
            "",
            "app:",
            "  cors:",
            f"    allowed-origins: ${{CORS_ORIGINS:http://localhost:{ctx.web_port}}}",
        ]
        if ctx.needs_auth:
            lines += [
                "  jwt:",
                "    secret: ${JWT_SECRET:change-me-before-deploying-min-32-chars}",
                "    expiration-ms: ${JWT_EXPIRATION_MS:43200000}",
            ]
        lines += [
            "",
            "logging:",
            "  level:",
            "    root: ${LOG_LEVEL:INFO}",
        ]
        return "\n".join(lines) + "\n"

    def _database_url(self, ctx: ScaffoldContext, jdbc: dict[str, str]) -> str:
        if not ctx.needs_database:
            return ""
        if ctx.database_key == "mongodb":
            return f"mongodb://localhost:27017/{ctx.package_name}"
        if ctx.database_key == "sqlite":
            return f"jdbc:sqlite:{ctx.package_name}.db"
        return f"{jdbc['scheme']}/{ctx.package_name}"

    def env_template(self, ctx: ScaffoldContext, database_url: str) -> str:
        lines = [
            "# Application",
            f"PORT={ctx.api_port}",
            "LOG_LEVEL=INFO",
            "",
            "# CORS — comma-separated origins allowed to call this API",
            f"CORS_ORIGINS=http://localhost:{ctx.web_port}",
        ]
        if ctx.needs_database and ctx.database_key == "mongodb":
            lines += ["", "# Database", f"MONGODB_URI={database_url}"]
        elif ctx.needs_database:
            lines += [
                "",
                "# Database",
                f"DATABASE_URL={database_url}",
                f"DATABASE_USER={ctx.package_name}",
                f"DATABASE_PASSWORD={ctx.package_name}_password",
            ]
        if ctx.needs_auth:
            lines += [
                "",
                "# Authentication — the secret must be at least 32 characters",
                "JWT_SECRET=change-me-before-deploying-min-32-chars",
                "JWT_EXPIRATION_MS=43200000",
            ]
        return "\n".join(lines) + "\n"

    def dockerfile(self, ctx: ScaffoldContext) -> str:
        return f"""# syntax=docker/dockerfile:1

FROM gradle:8.11-jdk21-alpine AS build
WORKDIR /home/gradle/project
COPY --chown=gradle:gradle build.gradle settings.gradle ./
# Warm the dependency cache before copying sources.
RUN gradle dependencies --no-daemon || true
COPY --chown=gradle:gradle src ./src
RUN gradle bootJar --no-daemon

FROM eclipse-temurin:21-jre-alpine AS runtime
WORKDIR /app
RUN addgroup -S spring && adduser -S spring -G spring
COPY --from=build /home/gradle/project/build/libs/{ctx.project_slug}-api.jar app.jar
RUN chown spring:spring app.jar
USER spring

EXPOSE {ctx.api_port}

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \\
    CMD wget -q --spider http://localhost:{ctx.api_port}/actuator/health || exit 1

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "app.jar"]
"""

    def conventions(self, ctx: ScaffoldContext) -> str:
        package = self._java_package(ctx)
        path = self._package_path(ctx)
        sections = [
            "Spring Boot 3.4 + Java 21 backend conventions. Generated code MUST follow "
            "these exactly.",
            "",
            f"## Base package: `{package}`",
            f"## Layout — every source file goes under `backend/src/main/java/{path}/`",
            "```",
            "  Application.java              @SpringBootApplication entrypoint",
            "  config/CorsConfig.java        CORS configuration from app.cors.*",
            "  controller/<Res>Controller.java   @RestController, thin HTTP layer",
            "  service/<Res>Service.java         Interface",
            "  service/impl/<Res>ServiceImpl.java Business logic",
        ]
        if ctx.needs_database:
            if ctx.database_key == "mongodb":
                sections += [
                    "  repository/<Res>Repository.java    Spring Data MongoDB interface",
                    "  document/<Res>.java               MongoDB @Document",
                ]
            else:
                sections += [
                    "  repository/<Res>Repository.java    Spring Data JPA interface",
                    "  entity/<Res>.java                 JPA @Entity",
                ]
        sections += [
            "  dto/<Res>Request.java         Request record with Jakarta validation",
            "  dto/<Res>Response.java        Response record",
            "  mapper/<Res>Mapper.java       Entity <-> DTO conversion",
            "  exception/ApiException.java   Base application exception",
            "  exception/GlobalExceptionHandler.java  @RestControllerAdvice",
        ]
        if ctx.needs_auth:
            sections += [
                "  security/SecurityConfig.java  SecurityFilterChain bean",
                "  security/JwtService.java      Token issue and verify",
                "  security/JwtAuthFilter.java   OncePerRequestFilter",
            ]
        sections += [
            "```",
            "",
            "## Non-negotiable rules",
            "1. Constructor injection only. Never `@Autowired` on a field.",
            "2. DTOs are Java `record` types. Persistence models are classes.",
            "3. Never expose a persistence model from a controller — always map to a DTO.",
            "4. Request DTOs carry Jakarta validation annotations "
            "(`@NotBlank`, `@Email`, `@Positive`); controllers annotate the body "
            "parameter with `@Valid`.",
            "5. Controllers return `ResponseEntity<T>` with an explicit status.",
            "6. Services are declared as an interface plus an `Impl` class.",
            "7. Throw `ApiException` subclasses; `GlobalExceptionHandler` is the only "
            "place that builds an error response body.",
            "8. `@Transactional` goes on service methods, never on controllers or "
            "repositories.",
            "9. Use `jakarta.*` imports throughout. `javax.*` is Spring Boot 2 and will "
            "not compile.",
            "10. Every public class and method carries a Javadoc comment.",
        ]
        if ctx.needs_database and ctx.database_key == "mongodb":
            sections += [
                "",
                "## Database — MongoDB",
                "- Use `spring.data.mongodb.uri` from `MONGODB_URI`; do not configure JDBC, "
                "JPA, Hibernate, or Flyway.",
                "- Document classes use `@Document(collection = \"...\")`; repositories extend "
                "`MongoRepository<Document, String>` (or the matching identifier type).",
                "- Use `MongoTemplate` only for explicit aggregation or update operations that "
                "a repository method cannot express clearly.",
                "- Collections, validators and indexes must match `database/schema.js`. Keep "
                "MongoDB migration scripts in `database/migrations/` and run them with mongosh.",
            ]
        elif ctx.needs_database:
            sections += [
                "",
                "## Database",
                "- `spring.jpa.hibernate.ddl-auto` is `validate`. The schema is owned by "
                "Flyway; entities must match the SQL schema already produced for this "
                "project exactly, or the application will refuse to start.",
                "- Place migrations at "
                "`backend/src/main/resources/db/migration/V1__initial_schema.sql`, "
                "following Flyway's `V<n>__<description>.sql` naming.",
                "- Repositories extend `JpaRepository<Entity, IdType>`.",
                "- Derived query methods are preferred; use `@Query` only where a "
                "derived name would be unreadable.",
                "- Annotate entity collections `fetch = FetchType.LAZY`.",
            ]
        if ctx.needs_auth:
            sections += [
                "",
                "## Authentication",
                "- `SecurityConfig` defines a `SecurityFilterChain` bean. The deprecated "
                "`WebSecurityConfigurerAdapter` must not appear.",
                "- Disable CSRF for the stateless API and set session management to "
                "`STATELESS`.",
                "- `JwtAuthFilter` extends `OncePerRequestFilter` and is registered "
                "before `UsernamePasswordAuthenticationFilter`.",
                "- Hash passwords with `BCryptPasswordEncoder` exposed as a `@Bean`.",
                "- Use the jjwt 0.12.x API (`Jwts.builder()...signWith(key)`).",
            ]
        sections += [
            "",
            "## Do not generate",
            "`build.gradle`, `settings.gradle`, `application.yml`, `Dockerfile`, "
            "`.env.example` — these already exist in the scaffold and must not be "
            "recreated or modified.",
        ]
        return "\n".join(sections)
