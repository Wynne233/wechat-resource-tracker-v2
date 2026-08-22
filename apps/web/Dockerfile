FROM node:20-alpine

WORKDIR /app

COPY package.json ./package.json
RUN npm install

COPY . .

ARG INTERNAL_API_BASE_URL=http://api:8000
ENV INTERNAL_API_BASE_URL=${INTERNAL_API_BASE_URL}
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start", "--", "-p", "3000"]
