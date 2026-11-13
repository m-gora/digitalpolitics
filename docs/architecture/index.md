# Digital Politics Platform — Architecture

Architecture documentation for the campaign canvas and crowdsourcing platform, following the [arc42](https://arc42.org) template. Each arc42 section lives in its own file:

| Section | File | Content |
|---|---|---|
| 1. Introduction and Goals | [01-introduction-and-goals.md](01-introduction-and-goals.md) | Purpose, quality goals, stakeholders |
| 2. Architecture Constraints | [02-architecture-constraints.md](02-architecture-constraints.md) | Technology, organization and legal constraints |
| 3. Context and Scope | [03-context-and-scope.md](03-context-and-scope.md) | System context, actors, external systems |
| 4. Solution Strategy | [04-solution-strategy.md](04-solution-strategy.md) | Key architectural decisions, mapped to ADRs |
| 5. Building Block View | [05-building-block-view.md](05-building-block-view.md) | Code structure, modules, data model |
| 6. Runtime View | [06-runtime-view.md](06-runtime-view.md) | Key scenarios as sequence diagrams |
| 7. Deployment View | [07-deployment-view.md](07-deployment-view.md) | k3s cluster layout, GitOps, image pipeline |
| 8. Cross-cutting Concepts | [08-concepts.md](08-concepts.md) | Auth, RBAC, events, config, migrations, design |
| 9. Quality Requirements | [09-quality-requirements.md](09-quality-requirements.md) | Quality scenarios and priorities |
| 10. Risks and Technical Debt | [10-risks-and-technical-debt.md](10-risks-and-technical-debt.md) | Known risks and prototype-scale debt |
| 11. Glossary | [11-glossary.md](11-glossary.md) | Domain terms |

## Documentation conventions

This documentation describes the **high-level concepts and decisions** — the *how* and *why* of the system's shape. The fine-grained, binding **requirements** live in the `spec/` directory at the repository root and remain the source of truth for behavior:

- [`spec/00-architecture/`](../../spec/00-architecture/) — cross-cutting requirements (`arch-01` … `arch-07`)
- [`spec/01-adrs/`](../../spec/01-adrs/) — architecture decision records (`adr-01` … `adr-08`)
- [`spec/02-modules/`](../../spec/02-modules/) — module specifications (`canv-01` … `canv-05`, `crowd-01` … `crowd-05`)

Wherever this documentation and `spec/` disagree about *behavior*, `spec/` wins. This documentation is also free to describe implementation details (file names, package layout) that change more often than the specs.

Other entry points:

- [`app/README.md`](../../app/README.md) — local development setup, project layout
- [`k8s/README.md`](../../k8s/README.md) — operational details of the Kubernetes manifests
