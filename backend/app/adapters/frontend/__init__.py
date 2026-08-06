"""Frontend technology adapters."""

from app.adapters.frontend.angular import AngularAdapter
from app.adapters.frontend.nextjs import NextJSAdapter
from app.adapters.frontend.react import ReactAdapter

__all__ = ["AngularAdapter", "NextJSAdapter", "ReactAdapter"]
