FROM python:3.12-slim
WORKDIR /app
# Install build tools for torch and scipy
RUN apt-get update && apt-get install -y \
    build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
ENV PYTHONPATH=/app
EXPOSE 3007
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3007"]
