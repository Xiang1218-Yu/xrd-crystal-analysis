FROM python:3.12-slim
WORKDIR /workspace
COPY src ./src
COPY examples ./examples
ENV PYTHONUNBUFFERED=1
CMD ["python3", "src/xrd_analyzer.py", "--input", "examples/peaks.json", "--output", "/tmp/xrd-result.json"]
