# Dev: ng serve with hot reload
FROM node:22-alpine AS dev
WORKDIR /app
COPY package*.json ./
# `npm ci` is strict about every nested optional peer; lockfiles that validate on one OS
# can still fail in Alpine Linux. `npm install` uses the lockfile and reconciles the tree.
RUN npm install --no-audit --no-fund
COPY . .
EXPOSE 4200
# Compose bind-mounts the repo over /app; a fresh `node_modules` volume can be empty, so
# install before serve. Unchanged lockfiles resolve quickly.
CMD ["sh", "-c", "npm install --no-audit --no-fund && exec npx ng serve --host 0.0.0.0 --poll 500"]

# Production build
FROM dev AS builder
RUN npx ng build --configuration production

# Nginx for static app
FROM nginx:alpine AS prod
COPY --from=builder /app/dist/web/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
