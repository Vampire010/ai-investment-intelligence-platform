from __future__ import annotations

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "market_agent"
if _SRC_PACKAGE.exists():
    __path__ = [str(_SRC_PACKAGE), *[path for path in __path__ if path != str(_SRC_PACKAGE)]]

from .services.agent import MarketAnalysisAgent

__all__ = ["MarketAnalysisAgent"]
