FROM python:3.11-slim

WORKDIR /app

# System deps for pandas/scipy/torch
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8050

CMD ["gunicorn", "app:server", "--config", "gunicorn.conf.py"]
