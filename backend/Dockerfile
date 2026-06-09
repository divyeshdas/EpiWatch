FROM python:3.11-slim

WORKDIR /app

# System libraries for the geospatial stack (osmnx → geopandas/shapely/pyproj/rtree/fiona).
#
# fiona (geopandas' I/O backend) has no linux/arm64 wheels on PyPI and must always
# be built from source on that platform.  libgdal-dev provides gdal-config and the
# GDAL 3.6 headers that fiona 1.9.x compiles against.
#
# shapely 2.x, pyproj 3.x, and rtree 1.x ship bundled-library arm64 wheels, so
# libgeos-dev / libproj-dev / libspatialindex-dev are fallbacks for source builds
# on less common patch releases.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Upgrade pip before the main install so it finds the widest set of pre-built wheels
# and respects the updated manylinux/arm64 wheel tags added in pip 21+.
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .
