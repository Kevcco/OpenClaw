FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY run.py ./run.py

RUN mkdir -p /app/data /app/uploads

ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/app/data/app.db
ENV UPLOAD_DIR=/app/uploads
ENV PYTHONPATH=/app

COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/app/docker-entrypoint.sh"]
