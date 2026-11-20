# Everything preinstalled (Tesseract + Tamil model + Noto Sans Tamil):
#   docker build -t tamilbook .
#   docker run --rm -v "$PWD:/work" tamilbook convert book.pdf -o out
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-tam fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY tamilbook ./tamilbook
RUN pip install --no-cache-dir .
WORKDIR /work
ENTRYPOINT ["tamilbook"]
