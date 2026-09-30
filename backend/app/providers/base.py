from dataclasses import dataclass


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    sport: str
    capability: str
    status: str
    detail: str
    requires_key: bool = False
