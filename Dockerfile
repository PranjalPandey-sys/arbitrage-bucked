# Use a maintained base image so apt-get works
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install only what we need (unzip) and clean up
RUN apt-get update && apt-get install -y unzip && rm -rf /var/lib/apt/lists/*

# Copy all files into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Unzip your app.zip into /app
RUN unzip app.zip -d /app

# Start FastAPI from main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
