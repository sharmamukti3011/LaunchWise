# Backend image. Build from the repo root: docker build -f backend/Dockerfile .
# TODO(verify): pin the base image by digest on the server.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# A fixed non-root user. /data holds SQLite and is a volume owned by this user.
RUN useradd --system --uid 10001 --user-group --no-create-home app \
    && mkdir /data \
    && chown app:app /data

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Application code only: no tests, no dev requirements, no .env.
COPY backend/app ./app

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

# --proxy-headers makes request.client the real visitor address behind Caddy. Which proxy is
# trusted is set at run time with FORWARDED_ALLOW_IPS (see docker-compose.yml); the uvicorn
# default of 127.0.0.1 applies if it is not set.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
