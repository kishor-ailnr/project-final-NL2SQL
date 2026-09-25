# PDF Documentation Synchronization Rule

Whenever any feature is added, modified, or deleted in this project:
1. **Backend Changes**:
   - Update `nl2sql-backend/scripts/generate_complete_backend_guide.py` with the updated files, functions, and feature map details.
   - Run the script to regenerate `docs/Backend_Complete_Guide.pdf` and `nl2sql-backend/docs/Backend_Complete_Guide.pdf`.
2. **Frontend Changes**:
   - Update `nl2sql-backend/scripts/generate_complete_frontend_guide.py` with the updated components, hooks, UI behaviors, and feature map details.
   - Run the script to regenerate `frontend/docs/Frontend_Complete_Guide.pdf` and `docs/Frontend_Complete_Guide.pdf`.
3. Commit and push the updated PDF documentation alongside the code changes.
