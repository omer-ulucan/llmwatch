<!-- Epoch 2: Backend Core Structure -->
<!-- 
WHY: Before exposing any APIs, the backend needs a solid, typed configuration foundation, robust structured exception handling, and standard operational services. The DynamoDB and MLFlow services act as the foundational external integrations that the rest of the app will rely upon. 
-->

- [x] Create Python requirements.txt
- [x] Implement config.py and exceptions.py
- [x] Implement DynamoDB service
- [x] Implement MLFlow service

**Completion Note:** Established the strong foundational layers of the backend, locking down dependencies in `requirements.txt` and successfully building abstractions for AWS DynamoDB and MLFlow logging. We're now ready for Auth.
