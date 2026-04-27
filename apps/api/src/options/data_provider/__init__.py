"""Provider adapter layer for options chain data (Phase 11C).

Provides the provider-agnostic boundary. Downstream code consumes the
normalized `OptionChainQuote` dataclass from `base_adapter`. Provider
swap (ThetaData → Polygon → ORATS) is a config + adapter file change
in v2; never a refactor.
"""

from apps.api.src.options.data_provider.base_adapter import (
    BaseOptionsAdapter,
    OptionChainQuote,
    ProviderError,
    ProviderUnavailable,
    PartialChainWarning,
)
from apps.api.src.options.data_provider.thetadata_adapter import (
    ThetaDataAdapter,
)


__all__ = [
    "BaseOptionsAdapter",
    "OptionChainQuote",
    "ProviderError",
    "ProviderUnavailable",
    "PartialChainWarning",
    "ThetaDataAdapter",
]
