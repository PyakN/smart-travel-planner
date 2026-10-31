# The web app: a standalone Next.js build (node server.js) as a non-root user, on port 3000.
#
#   docker build -t travel-planner-web --build-arg BACKEND_URL=http://api:8000 frontend
#   docker run -p 3000:3000 travel-planner-web
#
# BACKEND_URL, the target of the /api proxy, is fixed when the image builds: Next.js compiles
# its rewrites into the build.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT=standalone
ARG BACKEND_URL=http://backend:8000
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
