FROM python:3.11-slim-buster

WORKDIR /app

# Install unzip and any system deps
RUN apt-get update && apt-get install -y unzip && rm -rf /var/lib/apt/lists/*

# Copy everything into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Unzip your app.zip into /app
RUN unzip app.zip -d /app

# Start FastAPI from main.py inside the unzipped folder
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
