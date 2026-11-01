# Self-hosted OSRM: walking routes (foot profile) in the areas around the supported cities
# (areas.txt). The street data is downloaded and processed while the image builds (~900 MB
# of Geofabrik downloads, then about a minute and 1.2 GB of RAM); the image then routes on
# its own, on port 5000.
#
#   docker build -t travel-planner-osrm osrm
#   docker run -p 5000:5000 travel-planner-osrm
#
# Builds reuse the processed data while areas.txt is unchanged: `--no-cache` takes fresh
# OpenStreetMap data.
ARG OSRM_IMAGE=ghcr.io/project-osrm/osrm-backend:v26.10.0-debian

FROM debian:trixie-slim AS extract
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl osmium-tool \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /data
COPY areas.txt prepare.sh ./
RUN sh prepare.sh

FROM ${OSRM_IMAGE} AS graph
WORKDIR /data
COPY --from=extract /data/areas.osm.pbf .
# Multi-level Dijkstra: tables of 25 points in 50-300 ms, from a graph that builds in about
# a minute (contraction hierarchies took over 10). The files only partitioning and
# customizing read are left out of the image (~290 MB).
RUN osrm-extract -p /opt/foot.lua areas.osm.pbf \
    && osrm-partition areas.osrm \
    && osrm-customize areas.osrm \
    && rm areas.osm.pbf areas.osrm.ebg areas.osrm.enw areas.osrm.cnbg areas.osrm.cnbg_to_ebg \
        areas.osrm.turn_penalties_index

FROM ${OSRM_IMAGE}
RUN useradd --system --no-create-home osrm
COPY --from=graph --chown=osrm:osrm /data /data
USER osrm
EXPOSE 5000
# Memory-mapped data: ~100 MB of RAM in use instead of ~600 MB, as fast here. At most 100
# points per table, as many as the API's OsrmProvider sends.
CMD ["osrm-routed", "--algorithm", "mld", "--mmap", "on", "--max-table-size", "100", "/data/areas.osrm"]
