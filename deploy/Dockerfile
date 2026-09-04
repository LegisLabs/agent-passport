# Agent Passport skeleton: one container, FastAPI + SQLite.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY deploy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY rulepacks ./rulepacks
COPY fixtures ./fixtures
ENV DATA_DIR=/data
EXPOSE 8013
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8013"]
