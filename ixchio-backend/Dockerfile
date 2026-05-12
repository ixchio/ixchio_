FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY auth.py ./
COPY clients/ clients/
COPY core/ core/
COPY pipeline/ pipeline/

ENV PYTHONUNBUFFERED=1
ENV PORT=10000

EXPOSE 10000

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
