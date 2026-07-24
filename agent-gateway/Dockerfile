FROM node:22.19.0-bookworm-slim

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV NODE_ENV=production
WORKDIR /app

COPY package.json package-lock.json ./
RUN HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} \
    npm ci --omit=dev --ignore-scripts

COPY src ./src

USER node
EXPOSE 8090
CMD ["node", "src/main.ts"]
