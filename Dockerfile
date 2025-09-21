FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install any system dependencies you need
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy everything into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start FastAPI app (note: app.main:app because main.py is inside /app)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
