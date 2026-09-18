FROM python:3.12-slim

WORKDIR /app

# ffmpeg comes from the imageio-ffmpeg pip package (static binary) at runtime,
# so no apt-get ffmpeg install is needed here -- keeps the image small.

COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY assets_bundled ./assets_bundled

RUN pip install --no-cache-dir -e .

ENV AUTOPOST_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8080

CMD ["python", "-m", "autopost"]
