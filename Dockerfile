# Glyph backend - Hugging Face Space (Docker SDK).
#
# Build context is the repo root so the image gets both backend/ and model/.
# Spaces run the container as UID 1000 and expect the app on port 7860.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --chown=user backend/requirements.txt ./requirements.txt
# Swap OpenCV for the headless build: the normal wheel needs libGL, which a
# slim image doesn't ship, and a server never draws windows anyway. CPU-only
# torch keeps the image ~2.5 GB smaller than the default CUDA build.
RUN sed 's/^opencv-python/opencv-python-headless/' requirements.txt > requirements.docker.txt \
    && pip install --no-cache-dir --user -r requirements.docker.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu

COPY --chown=user backend/ ./backend/
COPY --chown=user model/ ./model/

ENV MODEL_DIR=/app/model \
    TORCH_NUM_THREADS=2 \
    PORT=7860
EXPOSE 7860

WORKDIR /app/backend
# Model load takes a few seconds; give it room before the healthcheck bites.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=5).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
