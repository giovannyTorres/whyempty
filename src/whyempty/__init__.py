"""Explain why sequential Python filters eliminate records, without dependencies."""

from .audit import AuditResult
from .core import FilterError, Trace, trace
from .models import FilterStats, Rejection, Relaxation, Step
from .pipeline import Pipeline

__version__ = "0.2.1"

__all__ = [
    "AuditResult",
    "FilterError",
    "FilterStats",
    "Pipeline",
    "Rejection",
    "Relaxation",
    "Step",
    "Trace",
    "__version__",
    "trace",
]
