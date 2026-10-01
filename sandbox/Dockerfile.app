FROM python:3.14-slim
RUN pip install --no-cache-dir \
    fastapi==0.141.1 sqlmodel==0.0.39 \
    email-validator==2.2.0 httpx==0.28.1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /task
USER 65534:65534
