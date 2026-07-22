# Runtime image for the Brussels job-search pipeline.
#
# By design this container does NOT run the pipeline on start -- it only holds
# the code and its dependencies, ready to run. You spin it up with Dokploy and
# then schedule the actual work (see README "Daily refresh"):
#
#     docker exec <container> python -m jobsearch.refresh
#
# The default command just keeps the container alive so a scheduler always has
# something to exec into.

FROM python:3.10-slim

# lxml needs libxml2/libxslt; the rest is HTTP + parsing, no browser required
# for the daily refresh. tini gives us clean signal handling for the idle PID 1.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libxslt1.1 tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a code change doesn't bust the pip cache layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code. .env is NOT baked in -- it's injected at runtime by Dokploy
# (see .dockerignore); credentials never live in the image.
COPY jobsearch/ ./jobsearch/
COPY app.py ./

# The pipeline caches HTTP responses and writes catalogue.json under /app/data.
# Mount a volume here in Dokploy so the content-hash freshness baseline and the
# cache survive restarts -- otherwise every run looks like a "first scan".
RUN mkdir -p /app/data/cache
VOLUME ["/app/data"]

ENV PYTHONUNBUFFERED=1

# Idle by default: the container is a ready-to-use runtime, and the scheduler
# decides when work happens. tini reaps zombies and forwards signals.
ENTRYPOINT ["tini", "--"]
CMD ["sleep", "infinity"]
