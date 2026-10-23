FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS verifier-deps

# Verifier-only dependencies are fetched as immutable wheel artifacts. Every
# remote artifact is accepted only when its SHA-256 digest matches exactly.
ADD --checksum=sha256:9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7 https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl /opt/verifier-wheels/iniconfig-2.3.1-py3-none-any.whl
ADD --checksum=sha256:d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl /opt/verifier-wheels/packaging-26.3-py3-none-any.whl
ADD --checksum=sha256:7dd7b0d8832ba3cb632c306926ded123429211b83641b35dc5c41ad2d34f9bec https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl /opt/verifier-wheels/pluggy-1.7.0-py3-none-any.whl
ADD --checksum=sha256:2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9 https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl /opt/verifier-wheels/pygments-2.21.0-py3-none-any.whl
ADD --checksum=sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c https://files.pythonhosted.org/packages/24/25/1de2678b631f5a49215c6c96fff41ba892b0a34df68d6d80292b1b48aa7f/pytest-9.1.1-py3-none-any.whl /opt/verifier-wheels/pytest-9.1.1-py3-none-any.whl

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /workspace
COPY --from=verifier-deps /opt/verifier-wheels /opt/verifier-wheels
COPY src ./src
COPY examples ./examples
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/verifier-wheels/iniconfig-2.3.1-py3-none-any.whl:/opt/verifier-wheels/packaging-26.3-py3-none-any.whl:/opt/verifier-wheels/pluggy-1.7.0-py3-none-any.whl:/opt/verifier-wheels/pygments-2.21.0-py3-none-any.whl:/opt/verifier-wheels/pytest-9.1.1-py3-none-any.whl
CMD ["python3", "src/xrd_analyzer.py", "--input", "examples/peaks.json", "--output", "/tmp/xrd-result.json"]
