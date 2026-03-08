# LLMWatch - Comprehensive Fix Plan

## Overview
18 issues identified across backend, frontend, configuration, and testing.
User selected: Fix ALL issues + Backend-only pytest test suite.

## Issue Inventory

### Build-Breaking (must fix first)

#### #1 - tailwindcss-animate incompatible with Tailwind v4
- **File**: `frontend/src/index.css:8`
- **Problem**: `@import "tailwindcss-animate"` fails because tailwindcss-animate v1.0.7 is a JS plugin (Tailwind v3), not a CSS file importable in Tailwind v4.
- **Fix**: Remove `@import "tailwindcss-animate";` line. The keyframes are already defined in `@theme` block (lines 44-61).

#### #2 - Missing email-validator dependency
- **File**: `backend/requirements.txt`
- **Problem**: `schemas.py` uses `from pydantic import EmailStr` which requires `email-validator` package. Not in requirements.txt.
- **Fix**: Add `email-validator>=2.1.0` to requirements.txt. Also add `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `httpx>=0.27.0` for testing.

### Backend Code Fixes

#### #3 - Deprecated datetime.utcnow()
- **Files**: `backend/auth/jwt_handler.py:37,40`, `backend/services/dynamo_service.py:48`, `backend/routers/auth.py:36`
- **Fix**: Add `from datetime import timezone` and replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.

#### #4 - Deprecated @app.on_event("startup")
- **File**: `backend/main.py:78-81`
- **Fix**: Convert to `lifespan` async context manager pattern.

#### #5 - Unused Optional import
- **File**: `backend/exceptions.py:9`
- **Fix**: Remove `from typing import Optional` line.

#### #6 - Dockerfile healthcheck uses curl (not in slim image)
- **File**: `backend/Dockerfile:21`
- **Fix**: Replace with `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"`.

#### #7 - asyncio.create_task fire-and-forget swallows errors
- **File**: `backend/routers/chat.py:71`
- **Fix**: Use FastAPI `BackgroundTasks` or add try/except inside `log_operations()`.

#### #8 - DynamoDB Decimal serialization
- **File**: `backend/routers/analytics.py:24-25`
- **Fix**: Convert Decimal values to float using a helper: `float(log.get("cost_usd", 0))`.

#### #9 - Module-level service singletons block testing
- **Files**: `backend/services/dynamo_service.py:124`, `backend/services/mlflow_service.py:90`, `backend/services/llm_service.py:166`
- **Fix**: Convert to lazy initialization with `get_*_service()` factory functions. This enables mocking in tests.

### Frontend Fixes

#### #10 - Dashboard uses mock timeseries
- **File**: `frontend/src/routes/dashboard.tsx:18-22`
- **Fix**: Fetch from `/analytics/timeseries` and map response to chart data.

#### #11 - Settings buttons non-functional
- **File**: `frontend/src/routes/settings.tsx`
- **Fix**: Add `onClick` handlers that show `window.alert()` placeholders.

#### #12 - CSV export non-functional
- **File**: `frontend/src/routes/analytics.tsx:32-34`
- **Fix**: Add CSV generation from `filteredLogs` and trigger browser download.

### Configuration Fixes

#### #13 - .gitignore missing venv/
- **File**: `.gitignore`
- **Fix**: Add `venv/` and `.pytest_cache/`.

#### #15 - Missing ESLint config
- **Fix**: Create `frontend/eslint.config.js` with React + hooks + refresh plugins.

### Documentation/Minor Fixes

#### #16 - Misleading Zustand docstring
- **File**: `frontend/src/store/useStore.ts:4`
- **Fix**: Change "Stores JWT securely in memory" to "Stores JWT in localStorage via persist middleware".

#### #17 - Hardcoded API key placeholder
- **File**: `frontend/src/routes/settings.tsx:26`
- **Fix**: Replace with asterisks or "••••••••••••••••".

### Testing

#### #14 - Create backend pytest test suite
- Create `backend/tests/` directory with:
  - `conftest.py` - shared fixtures, mock settings
  - `test_exceptions.py` - exception hierarchy
  - `test_schemas.py` - Pydantic validation
  - `test_jwt_handler.py` - JWT creation/decoding
  - `test_llm_service.py` - cost calculation
  - `test_analytics.py` - aggregation logic, Decimal handling
  - `test_auth_deps.py` - dependency injection

## Execution Order
1. Fix #1, #2 (build-breaking)
2. Fix #3, #4, #5, #6 (backend code, independent)
3. Fix #7, #8, #9 (backend logic, depends on service refactoring)
4. Fix #13, #15 (config)
5. Fix #10, #11, #12, #16, #17 (frontend)
6. Fix #14 (tests - after service refactoring)
7. Verify all fixes (build + test run)
