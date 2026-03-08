"""
Module: rate_limit.py
Purpose: Shared slowapi Limiter instance for the entire application.
WHY: Extracting the limiter into its own module breaks the circular import
between main.py (which creates the app) and routers (which need the limiter
at decoration time).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
