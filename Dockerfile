FROM python:3.11-slim-bookworm

WORKDIR /app

# Install unzip and clean up
RUN apt-get update && apt-get install -y unzip && rm -rf /var/lib/apt/lists/*

# Copy all files into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Unzip your app.zip into /app
RUN unzip app.zip -d /app

# 🔍 Debug step: list all files so we can see where main.py is
RUN echo "=== FILE TREE AFTER UNZIP ===" && ls -R /app

# Start FastAPI (adjust path after checking logs)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
