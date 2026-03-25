# Stage 1: Build the React application
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# Pass the API URL at build time if needed, 
# though for React it's often better to use env vars or a config.json at runtime.
# For now, we'll build it with the localhost:8081 default.
ARG REACT_APP_API_URL=http://localhost:8081
ENV REACT_APP_API_URL=$REACT_APP_API_URL

RUN npm run build

# Stage 2: Serve the application using Nginx
FROM nginx:stable-alpine
COPY --from=build /app/build /usr/share/nginx/html

# Add a basic Nginx config to handle React Router routes (SPA)
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
