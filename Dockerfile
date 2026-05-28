# Owner: Amer
FROM python:3.11-slim AS base
WORKDIR /app
RUN pip install --no-cache-dir uv

# Copy source FIRST so editable install (-e .) can resolve the packages
# declared in pyproject.toml's [tool.setuptools].packages.
COPY pyproject.toml ./
COPY app ./app
RUN uv pip install --system -e ".[dev]"
COPY modelserver ./modelserver
COPY guardrails ./guardrails
COPY admin ./admin
COPY scripts ./scripts

RUN uv pip install --system -e ".[dev]"

FROM node:20-alpine AS widget-build
WORKDIR /widget
COPY frontend/widget/package.json frontend/widget/package-lock.json ./
RUN npm ci
COPY frontend/widget ./
RUN npm run build

FROM base AS api
COPY --from=widget-build /widget/dist ./frontend/widget/dist
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS modelserver
CMD ["uvicorn", "modelserver.main:app", "--host", "0.0.0.0", "--port", "8010"]

FROM base AS guardrails
CMD ["uvicorn", "guardrails.main:app", "--host", "0.0.0.0", "--port", "8020"]

FROM base AS admin
CMD ["streamlit", "run", "admin/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
