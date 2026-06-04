# Two-stage: build the static bundle in Node, serve it from Nginx. We don't
# actually use this for the production Vercel deploy — Vercel builds from the
# `frontend/` directory itself — but it lets `docker-compose up` give a
# self-contained local stack and demonstrates the deploy story for non-Vercel
# hyperscalers.

FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline --no-audit --no-fund
COPY . .
# Vite reads the VITE_* vars from frontend/.env (copied in above) at build time
# and bakes them into the static bundle. Those values are public by design —
# they ship in the browser bundle either way — and .env only lives in this
# builder stage, which is discarded; the runtime image is just dist/.
RUN npm run build


FROM nginx:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
