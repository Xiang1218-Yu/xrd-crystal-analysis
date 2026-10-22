FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /workspace
# Runtime dependency manifest: this application uses only the Python 3.12
# standard library, so no third-party package is installed into the image.
COPY requirements.lock /tmp/requirements.lock
COPY src ./src
COPY examples ./examples
ENV PYTHONUNBUFFERED=1
CMD ["python3", "src/xrd_analyzer.py", "--input", "examples/peaks.json", "--output", "/tmp/xrd-result.json"]
