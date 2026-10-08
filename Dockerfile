# GarAI su Cloud Run: frontend compilato + backend Python + LibreOffice per anteprime delle slide.
# Il PPTX e' prodotto da python-pptx: PowerPoint non serve. La misura del testo usa la stima con i font del template.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    DATA_DIR=/data \
    LLM_CACHE_DIR=/data/cache/llm \
    OUT_DIR=/tmp/out \
    RENDERER=libreoffice \
    TRUSTED_PROXY_HOPS=1

# LibreOffice (solo Impress) e font metricamente compatibili con quelli Microsoft (Arial -> Liberation, Calibri -> Carlito)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-impress fonts-liberation fonts-crosextra-carlito fonts-dejavu-core fontconfig \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-cloud.txt ./
RUN pip install -r requirements.txt -r requirements-cloud.txt

# font del template (Work Sans; Clash Display se presente in assets/fonts/private, non versionata)
COPY assets/fonts/ /usr/local/share/fonts/garai/
RUN fc-cache -f

COPY app/ app/
COPY templates/ templates/
COPY assets/ assets/
COPY --from=web /web/dist web/dist

RUN useradd --create-home --uid 1000 garai && mkdir -p /data && chown garai /data
USER garai
EXPOSE 8080
CMD ["python", "-m", "app", "--host", "0.0.0.0", "--no-browser"]
