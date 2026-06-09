FROM python:3.11-slim

WORKDIR /app

# System libraries for the geospatial stack (osmnx → geopandas/shapely/pyproj/rtree).
# Binary wheels bundle GEOS/PROJ/spatialindex for linux/amd64 and linux/arm64, but
# having the system packages here means compilation succeeds even when a wheel is
# unavailable for the target platform (e.g. newer patch releases on linux/arm64).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
