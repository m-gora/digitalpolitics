FROM postgis/postgis:16-3.4

# The postgis image already configures the PGDG apt repo, which also ships
# pgvector packages for the matching Postgres major version.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
