# Single image: builds the React UI, then runs the FastAPI engine which serves it.
FROM node:20-slim AS ui
WORKDIR /ui
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Uncomment to bake Kokoro TTS into the image (adds ~2 GB):
# RUN pip install --no-cache-dir kokoro soundfile
COPY backend/ ./
COPY --from=ui /ui/dist /app/frontend/dist
ENV DATA_DIR=/data
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
