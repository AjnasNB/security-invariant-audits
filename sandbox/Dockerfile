FROM python:3.12-slim
RUN pip install --no-cache-dir \
    fastapi==0.115.12 sqlmodel==0.0.24 sqlalchemy==2.0.41 \
    pydantic==2.11.7 email-validator==2.2.0 httpx==0.28.1 \
    PyYAML==6.0.2 numpy==1.26.4 matplotlib==3.9.4 \
    spacy==3.7.5 Pillow==11.2.1 requests==2.32.3 openai==1.82.0 \
    nltk==3.9.1 \
 && pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.7.1/en_core_web_md-3.7.1-py3-none-any.whl
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /task
USER 65534:65534
