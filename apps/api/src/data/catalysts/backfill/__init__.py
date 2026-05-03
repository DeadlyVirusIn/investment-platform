"""Historical catalyst backfill — providers, service, dedupe, coverage."""

from apps.api.src.data.catalysts.backfill.base import (
    BackfillProvider, NewsRecord, EarningsRecord,
    BackfillProviderError,
)
from apps.api.src.data.catalysts.backfill.service import (
    BackfillService, BackfillRunConfig, BackfillRunResult,
)
from apps.api.src.data.catalysts.backfill.dedupe import (
    news_dedupe_key, earnings_dedupe_key,
)
from apps.api.src.data.catalysts.backfill.coverage import (
    CoverageReport, build_coverage_report, coverage_for_symbol,
)
from apps.api.src.data.catalysts.backfill.rate_limit import (
    RateLimiter,
)

__all__ = [
    "BackfillProvider", "NewsRecord", "EarningsRecord",
    "BackfillProviderError",
    "BackfillService", "BackfillRunConfig", "BackfillRunResult",
    "news_dedupe_key", "earnings_dedupe_key",
    "CoverageReport", "build_coverage_report", "coverage_for_symbol",
    "RateLimiter",
]
