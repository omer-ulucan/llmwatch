<!-- Epoch 3: Backend Auth & API -->
<!-- 
WHY: With the database and metrics logging ready, we construct the REST API. This epoch enforces zero-trust security principles (JWT routing, rate limits, Pydantic strict typing) and instantiates the multi-LLM routing logic to power the chat experience. 
-->

- [x] Implement Auth (JWT, dependencies)
- [x] Implement Security Middleware (CORS, headers, slowapi)
- [x] Implement LLM Service (Qwen & Gemini Strategy)
- [x] Implement Routers (auth, chat, analytics, health)
- [x] Implement main.py backend entrypoint

**Completion Note:** Fully built out the FastAPI core, enforcing security with JWTs and strict validation, and orchestrating dual LLM interactions via an extensible Strategy pattern. The backend is structurally complete.
