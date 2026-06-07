FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

CMD uvicorn api:app --host 0.0.0.0 --port ${PORT}
