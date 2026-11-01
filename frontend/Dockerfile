# The web app: a standalone Next.js build (node server.js) as a non-root user, on port 3000.
#
#   docker build -t travel-planner-web --build-arg BACKEND_URL=http://api:8000 \
#       --build-arg NEXT_PUBLIC_MAPBOX_TOKEN=pk.... frontend
#   docker run -p 3000:3000 travel-planner-web
#
# Fixed when the image builds: BACKEND_URL, the target of the /api proxy (Next.js compiles
# its rewrites into the build), and the map tile settings below.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT=standalone
ARG BACKEND_URL=http://backend:8000
# Map tiles (src/lib/tiles.ts), inlined into the browser code: a public Mapbox token and
# style, or another provider's URL. Left empty, they count as unset.
ARG NEXT_PUBLIC_MAPBOX_TOKEN=
ARG NEXT_PUBLIC_MAPBOX_STYLE=
ARG NEXT_PUBLIC_TILE_URL=
ARG NEXT_PUBLIC_TILE_ATTRIBUTION=
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Git keeps no empty folders: a checkout may have no public/ for the copy below.
RUN mkdir -p public && npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
