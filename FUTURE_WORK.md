# Future work

Remaining work after the eligibility, grant-refresh, budget, application-structure, privacy, funder AI-policy and consistency-review improvements. This is a prioritized backlog, not a claim that these capabilities exist or a delivery commitment.

[Project overview](README.md) | [Architecture](AI_Architecture.md) | [Evaluation](impactlink-backend/EVALUATION.md)

## 1. Database-level user isolation

**Current:** authenticated routes and application ownership checks protect saved work and sessions. Database-enforced tenant isolation is absent.

- Design least-privilege database roles and row-level policies for private work and checkpoints while preserving shared grant reads.
- Propagate verified identity through transaction-scoped database context safely with connection pooling.
- Review ownership enforcement across reads, updates, exports, sessions, profiles and storage.
- Test cross-account access and pooled-connection reuse against a real database.

**Completion evidence:** deployed migrations/restricted runtime roles and tests proving that an account cannot read, modify, delete or resume another account's work.

## 2. Deeper eligibility rules

**Current:** deadlines, applicant categories and recorded geography are checked; additional conditions remain unverified.

- Model tax status, fiscal sponsorship, organization budget ranges, matching-fund requirements, invitation/LOI prerequisites, prior-grantee conditions and award caps relative to organization size.
- Add applicant inputs and source-backed grant fields with dates/references.
- Distinguish mandatory eligibility from preferences; retain unknowns when evidence is absent.

**Completion evidence:** sourced eligible/ineligible/unknown fixtures for every rule, with only confirmed disqualifications excluded from matches.

## 3. Budget matching contributions and wage review

**Current:** FTE, fringe, MTDC/TDC, rate references/caps, unallowable categories and explicit scope options are implemented.

- Separate the grant request, applicant cash match, third-party cash and in-kind contributions.
- Calculate award-specific match bases without double-counting or assuming every contribution qualifies.
- Record valuations, commitments and supporting documentation; recalculate after scope changes.
- Add a documented workflow for reviewing salary reasonableness, prevailing wages and exempt-salary thresholds where applicable.

**Completion evidence:** deterministic tests for match bases, missing commitments, ineligible contributions and scope changes, with compliance assumptions explicit and reviewable.

## 4. Independent evaluation and broader automated checks

**Current:** regression tests, deterministic budget checks and small synthetic retrieval/drafting evaluations exist. AI scoring and consistency review remain probabilistic.

- Build a larger independently labeled grant-relevance/eligibility dataset and a held-out set.
- Obtain permission for realistic proposal examples and involve human grant reviewers.
- Measure unsupported claims, contradictions, sensitive-content misses, false redactions and recovery behavior alongside completion.
- Re-measure current latency, provider cost and concurrency with sample sizes and failure cases.
- Add the broader backend/frontend suites and production build to CI; repair or replace the default frontend scaffold test.

**Completion evidence:** reproducible reports with independent labels, configuration details, uncertainty and limitations. A separate AI judge alone does not establish real-world quality.

## 5. Grant refresh operations and source coverage

**Current:** California and Grants.gov adapters and a daily GitHub workflow are implemented.

- Publish/enable the workflow where needed, configure `GRANT_REFRESH_DATABASE_URL`, and verify successful scheduled production runs.
- Add failure alerts, stale-data monitoring and visible operational health.
- Validate discovery coverage, source changes and rate-limit/retry behavior before broadening sources.
- Add further state/foundation sources or organization data only with established access terms, provenance and update strategies.

**Completion evidence:** observable scheduled-run history, operator alerts and trustworthy freshness metadata. A workflow file does not prove refreshes are running.

## 6. Document and post-award workflows

**Current:** funder questions/limits, LOI/reporting starters, attachment checklists and saved proposals exist.

- Add attachment uploads, versioning, access controls and links to application requirements.
- Track submission stages, funder correspondence and reporting deadlines.
- Record awards, approved budgets, actual spending, outcome evidence and reporting progress.
- Evaluate funder-specific exports or portal integrations separately from generic PDF export.

**Completion evidence:** users can prepare a complete document set and track reporting obligations without the app claiming independent compliance verification.

## 7. Practitioner feedback and project positioning

- Interview at least three grant writers or nonprofit staff about discovery, eligibility, budgeting, privacy and reporting bottlenecks.
- Run observed task walkthroughs and document failures, unmet needs and resulting changes.
- Research a sourced comparison with relevant grant-discovery/writing tools.
- Keep prototype claims and documentation aligned with implementation. Review remote repository topics/tags and hosted-demo behavior separately from local documentation edits.

**Completion evidence:** consented, anonymized findings and concrete changes informed by feedback. Interviews, independent labels and production operations cannot be completed by documentation alone.
