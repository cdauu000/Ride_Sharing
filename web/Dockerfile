FROM node:24-alpine AS build
WORKDIR /web
ARG API_BASE_URL=http://api:8000
ENV API_BASE_URL=$API_BASE_URL
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM node:24-alpine
WORKDIR /web
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
COPY --from=build /web/public ./public
USER node
EXPOSE 3000
CMD ["node","server.js"]
