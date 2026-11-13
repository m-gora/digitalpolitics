# 1. Introduction and Goals

## What is it?

The **Digital Politics Platform** is an internal tool for the FDP's party units (*Gliederungen*) to plan, run and evaluate political campaigns, and to collect anonymous citizen feedback in the street. It consists of two functional modules:

1. **Campaign Canvas** (`spec/02-modules/canv-*`): a hierarchical, guided campaign-planning workflow. Party units at any level of the hierarchy create campaign canvasses, group them into initiatives with AI-assisted coherence scoring, run them through a lifecycle, fork past campaigns as templates, and conduct post-mortem retrospectives.
2. **Crowdsourcing** (`spec/02-modules/crowd-*`): anonymous, location-based citizen questionnaires. Admins create questionnaires linked to running campaigns; citizens answer on a kiosk-style respondent app (voice or text), optionally offline; authenticated users analyze the responses on a geospatial map.

## Quality goals (in priority order)

| Priority | Goal | Motivation |
|---|---|---|
| 1 | **Privacy by design** | Citizen data (street feedback) is the most sensitive asset: no identifiers are stored, PII is scrubbed, coordinates are coarsened (arch-04, crowd-03) |
| 2 | **Simple, low-maintenance operation** | The platform is operated by a single developer on a personal k3s cluster: server-rendered monolith, GitOps deployment, no SPAs, no message brokers |
| 3 | **Knowledge retention** | Finished campaigns and their retrospectives form a reusable, forkable knowledge base (canv-03, canv-04) |
| 4 | **Correct scoping** | Write access strictly follows the Gliederung hierarchy; read access is deliberately global (arch-02) |

## Stakeholders

| Role | Interest |
|---|---|
| Campaigners / party staff (authenticated users) | Plan campaigns, coordinate across hierarchy levels, analyze citizen feedback |
| Citizens (anonymous respondents) | Answer street questionnaires quickly and anonymously |
| Operator (single developer) | Low operational overhead, transparent GitOps pipeline |
| Data-protection owner | Privacy properties of the public surface and AI processing (adr-04, adr-07) |

## The system is deliberately a prototype

V1 accepts several prototype-scale simplifications (single-process SSE, last-write-wins concurrency, in-memory rate limiting) — they are tracked in [10-risks-and-technical-debt.md](10-risks-and-technical-debt.md), not hidden.
