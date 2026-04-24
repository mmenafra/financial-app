# Dev: ng serve with hot reload
FROM node:22-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 4200
CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--poll", "500"]

# Production build
FROM dev AS builder
RUN npx ng build --configuration production

# Nginx for static app
FROM nginx:alpine AS prod
COPY --from=builder /app/dist/web/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
