# Multi-stage build for the TypeScript Slack Bolt approval app.
# Builds TS → ships only the compiled dist on node:22-alpine so the runtime
# image stays under ~120 MB.
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vitest.config.ts ./
COPY src ./src

RUN npm run build \
    && npm prune --omit=dev


FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    PORT=8080

COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./

EXPOSE 8080

USER node

CMD ["node", "dist/server.js"]
