FROM node:20-slim

WORKDIR /app

# Copy package files first for layer caching
COPY package*.json ./
RUN npm install

# Copy remaining source (will be overridden by volume mount in docker-compose)
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
