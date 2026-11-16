"""I.K.E. AdBlock Engine.

The filter engine is I.K.E.'s own native module (ike_adblock), built from the
sources in ike-adblock/ on top of adblock-rust. If it cannot be loaded, an
optional python-adblock binding placed next to it is used instead; without
either, I.K.E. falls back to basic domain blocking. BACKEND tells which one
is active.
"""

try:
    from .ike_adblock import (  # noqa: F401
        ENGINE_VERSION,
        BlockerResult,
        Engine,
        FilterSet,
        Request,
        UrlSpecificResources,
        __version__,
    )
    BACKEND = "ike-adblock %s (adblock-rust %s)" % (__version__, ENGINE_VERSION)
    MODERN = True
except ImportError as _error:        # pragma: no cover - depends on the system
    from .adblock import BlockerResult, Engine, FilterSet, UrlSpecificResources, __version__  # noqa: F401
    ENGINE_VERSION = "0.5"
    BACKEND = "python-adblock %s (fallback: %s)" % (__version__, _error)
    MODERN = False

__all__ = ("Engine", "FilterSet", "BlockerResult", "UrlSpecificResources",
           "BACKEND", "ENGINE_VERSION", "MODERN")
