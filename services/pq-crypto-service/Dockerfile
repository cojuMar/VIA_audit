FROM python:3.12-slim

# liboqs requires cmake and build tools
RUN apt-get update && apt-get install -y \
    cmake ninja-build build-essential libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
EXPOSE 3012
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3012", "--workers", "2"]
