# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-07

### Added
- **Frontend**
  - Fully interactive awwwards-level user interface utilizing Glassmorphism.
  - Implemented React 19 concurrent routing with React Router v7 and Vite.
  - Complete Dark Mode theme mapped strictly in Tailwind CSS v4 variables.
  - Live cost tracking, request KPIs, and reasoning trace extraction dashboards.
  - JWT integration via secure memory-bound Zustand stores.
- **Backend**
  - High performance structural FastAPI environment.
  - Implemented secure JWT issue endpoints.
  - Strategy Pattern implementation orchestrating local `Qwen3.5` and `Gemini 3`.
  - Background logging architecture directly streaming metrics to DynamoDB and MLFlow independently.
  - Defensive security integrations targeting rate usage and HTTP header exploitation.
- **Infrastructure**
  - Production-ready Docker networks.
  - Nginx configuration optimized for single page application resolution.
  - Initial configuration `.env` structuring.

### Changed
- Refactored `chat` component structure providing inline reasoning execution dropdowns (a.k.a thinking mode).
- Centralized Axios client intercepts to intercept globally and re-route users during unauthorized exceptions.

### Security
- Injected strict Pydantic model configurations blocking arbitrary metadata injection during database requests.
- Integrated `bcrypt` encoding over legacy MD5 configurations.
