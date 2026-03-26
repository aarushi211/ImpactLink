# Use a slender Python image
FROM python:3.11-slim

# Prevent Python from writing pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory inside the container
WORKDIR /app

# Set a fixed location for sentence-transformers to avoid re-downloads at runtime
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache

# Copy the requirements file first to take advantage of Docker layer caching
COPY requirements.txt .

# Install dependencies (CPU-only torch to minimize image size)
# Increased timeout to 100s to handle large package downloads
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Pre-download the embedding model into the image layer.
# This bakes the weights into the build cache.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/app/.cache')"
# Copy the backend source code into the container
COPY . .

# Expose the port FastAPI will run on
EXPOSE 8080

# Run the FastAPI application using uvicorn
# Cloud Run expects the application to listen on the PORT environment variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
