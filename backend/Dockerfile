# Contexte de build attendu : la racine du monorepo (pas backend/), car ce
# Dockerfile copie aussi frontend/ depuis la racine du repo.
# docker build -f backend/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY frontend/ ./app/static/

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
