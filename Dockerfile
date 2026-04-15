FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt requirements-deploy.txt requirements-trends.txt ./

# Production image installs only runtime dependencies by default.
# If trend-pipeline image is needed, build with:
#   docker build --build-arg INSTALL_TRENDS_DEPS=1 -t <tag> .
ARG INSTALL_TRENDS_DEPS=0
RUN set -eux; \
    if [ "$INSTALL_TRENDS_DEPS" = "1" ]; then \
      apt-get update; \
      apt-get install -y --no-install-recommends build-essential libpq-dev; \
      pip install --no-cache-dir -r requirements-trends.txt; \
      python -m playwright install --with-deps --only-shell chromium; \
      apt-get purge -y --auto-remove build-essential libpq-dev; \
      rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* /root/.cache/pip; \
    else \
      pip install --no-cache-dir -r requirements-deploy.txt; \
    fi

COPY . .

# Normalize shell scripts copied from Windows checkouts so the container can
# execute them reliably in Linux environments.
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh
RUN mkdir -p storage/captures storage/processed storage/synthetic

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py verify_static_manifest --require shared/styles/base.css && python manage.py migrate --noinput && gunicorn --bind 0.0.0.0:8000 --timeout 120 --pythonpath /app mirrai_project.wsgi:application"]
