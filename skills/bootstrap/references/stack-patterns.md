# Stack patterns

Choose the smallest set that makes the selected stack reproducible and inspectable. Prefer native tooling already present in the ecosystem.

| Concern | JavaScript / TypeScript | Python | Rust | Go | Swift |
| --- | --- | --- | --- | --- | --- |
| Version pin | `.nvmrc`, `engines`, package-manager field | `.python-version`, `requires-python` | `rust-toolchain.toml` | `go.mod` | `.swift-version` when needed |
| Dependencies | lockfile + Corepack/package-manager pin | `uv.lock` or project lock | `Cargo.lock` | `go.sum` | `Package.resolved` |
| Types/static | `tsc --noEmit` | pyright/mypy | `cargo check` | `go vet` | compiler + SwiftLint if justified |
| Format/lint | ESLint + Prettier or Biome | Ruff | rustfmt + Clippy | gofmt + vet/staticcheck | swift-format, SwiftLint if justified |
| Unit tests | framework-native runner | pytest/unittest | `cargo test` | `go test` | XCTest / Swift Testing |
| API/schema | Zod/OpenAPI/GraphQL schema | Pydantic/OpenAPI | serde + schema crate | structs + OpenAPI when needed | Codable/OpenAPI when needed |
| Local services | Compose or dev container | Compose or dev container | Compose when external state exists | Compose when external state exists | local service harness |
| Dependency boundaries | dependency-cruiser or ESLint boundaries | Import Linter | module/crate graph + Clippy policy | package graph + architecture tests | module graph + architecture tests |
| Complexity | ESLint/Sonar-compatible analyzer | Ruff/Pylint/Radon or Sonar-compatible analyzer | Clippy + analyzer when justified | golangci-lint complexity rules | SwiftLint/Sonar-compatible analyzer |
| Duplication | jscpd or equivalent | jscpd/Pylint duplicate-code | jscpd or equivalent | dupl or equivalent | jscpd or equivalent |

## Cross-stack affordances

- Add a single task facade only when native commands are fragmented: package scripts, Make, Just, Task, or workspace-native equivalents.
- Keep CI commands identical to local commands.
- Add pre-commit hooks only after the underlying checks are fast and independently runnable.
- Prefer contract fixtures and in-process fakes over network mocks for default tests.
- Add browser automation only for user-visible critical paths.
- Add API clients, database consoles, story catalogs, component previews, or MCP tools only when they shorten a recurring exploration loop.
- Keep generated artifacts reproducible; document the generator and drift check.
- Adopt a stack-native public style guide; record only project-specific deltas in repository docs.
- Keep complexity, dependency-boundary, and clone checks independently runnable; exclude generated and vendored roots explicitly.
- Provide seed/reset commands that refuse unsafe targets.
- Record optional tools as optional; do not make a developer install an observability or orchestration stack to run a small app.
