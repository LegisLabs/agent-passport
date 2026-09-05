# Agent Passport, payments vertical: one container, FastAPI + SQLite. Same base as the HMRC app.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY deploy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pay ./pay
COPY rulepacks ./rulepacks
COPY fixtures ./fixtures
ENV DATA_DIR=/data
EXPOSE 8014
CMD ["python", "-m", "uvicorn", "pay.main:app", "--host", "0.0.0.0", "--port", "8014"]
