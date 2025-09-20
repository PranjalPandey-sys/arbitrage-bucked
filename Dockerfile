# Use official Python base image
FROM python:3.11-slim

# Install system dependencies for Playwright + Chromium
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0 libatk-bridge2.0 \
    libxkbcommon0 libxcomposite1 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 \
    libpango-1.0-0 libgtk-3-0 wget curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium
RUN pip install playwright && playwright install

# Copy all project files into /app in container
COPY . /app
WORKDIR /app

# ✅ Unzip app.zip into ./app
RUN apt-get update && apt-get install -y unzip \
    && unzip app.zip -d ./app \
    && rm app.zip

# Expose the port your app will run on
EXPOSE 5000

# Start the backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
