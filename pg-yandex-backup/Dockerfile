FROM python:3.12-slim

# Install PostgreSQL client tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY pyproject.toml .

# Install the package in editable mode so the entry points are available
RUN pip install --no-cache-dir -e .

# Local backup staging directory
RUN mkdir -p /backups

ENV PYTHONUNBUFFERED=1

CMD ["pg-backup"]
