# Decision records

Short records of the main design choices. They were written on 2026-11-04,
after the code, so they describe what was built and the options it can be
measured against. They are not minutes of the original discussions. Each date
is when the decision first appeared in the code.

| # | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith plus a separate worker | Accepted |
| [0002](0002-celery-queue.md) | Celery with Redis for background runs | Accepted |
| [0003](0003-normalized-results.md) | Normalized result tables, JSON for snapshots | Accepted |
| [0004](0004-native-metrics.md) | Native metrics, no evaluation framework | Accepted |
| [0005](0005-pricing-table.md) | Bundled, versioned pricing table | Accepted |
| [0006](0006-judge-rubrics.md) | Versioned rubrics in code for LLM judges | Accepted |
| [0007](0007-authentication.md) | No login in the first release | Accepted; must change before deployment |
| [0008](0008-custom-targets.md) | No custom HTTP targets yet | Accepted; revisit with the feature |
