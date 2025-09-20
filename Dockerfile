FROM python:3.11-slim

# Install system dependencies for Playwright Chromium
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libgtk-3-0 wget curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium
RUN pip install playwright && playwright install chromium

# Copy all project files into /app inside the container
COPY . /app
WORKDIR /app

# Expose the port your app will run on
EXPOSE 5000

# Start the backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]