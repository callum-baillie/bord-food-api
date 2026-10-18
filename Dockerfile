FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/callum-baillie/bord-food-api" \
    org.opencontainers.image.description="Immutable food and store reference catalogs for Bord"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    IMPORT_DIR=/imports \
    PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 foodapi \
    && useradd --uid 10001 --gid foodapi --no-create-home foodapi \
    && mkdir /data /imports \
    && chown foodapi:foodapi /data /imports
COPY bord_food_api ./bord_food_api
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/live', timeout=3)"
ENTRYPOINT ["python", "-m", "bord_food_api"]
CMD ["run"]
