"""Explain why sequential Python filters eliminate records, without dependencies."""

from .core import FilterError, Trace, trace
from .models import Rejection, Step

__version__ = "0.1.0"

__all__ = ["FilterError", "Rejection", "Step", "Trace", "__version__", "trace"]
