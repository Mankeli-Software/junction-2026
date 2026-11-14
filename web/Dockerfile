FROM node:24-alpine AS build
RUN npm install -g pnpm@12.18.0
WORKDIR /app
COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build && pnpm prune --prod

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000
COPY --from=build /app/build build
COPY --from=build /app/node_modules node_modules
COPY package.json .
EXPOSE 3000
CMD ["node", "build"]
