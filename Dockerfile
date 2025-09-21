# Use a maintained Python base image
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install any system dependencies you actually need
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy all files into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start FastAPI app
# If main.py is in the repo root:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

# If main.py is inside an 'app' folder, change to:
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
