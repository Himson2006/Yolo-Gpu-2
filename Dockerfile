# 1. GPU-enabled base with CUDA & cuDNN
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# 2. System packages for OpenCV, ffmpeg & PostgreSQL client libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libgl1-mesa-glx \
      libglib2.0-0 \
      libpq-dev \
      ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 3. Set working directory
WORKDIR /usr/src/app

# 4. Copy & install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 5. Copy application code
COPY . .

# 6. Ensure both incoming & detections folders exist
RUN mkdir -p app/uploads/incoming \
 && mkdir -p app/uploads/detections

# 7. Expose Flask port
EXPOSE 5000

# 8. Entrypoint: run the watcher in background, then launch Gunicorn
#    (all runtime env vars—DATABASE_URL, WATCH_FOLDER, etc.—come from docker-compose)
CMD ["sh", "-c", "\
    python watcher.py & \
    gunicorn --bind 0.0.0.0:5000 run:app --workers 2 --threads 4 \
"]