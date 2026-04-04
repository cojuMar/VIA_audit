FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 3021

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3021", "--workers", "1"]
