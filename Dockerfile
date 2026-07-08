FROM python:3.12-slim

RUN pip install --no-cache-dir yt-dlp pyyaml

RUN curl -fsSL https://deno.land/install.sh | sh && \
    ln -s /root/.deno/bin/deno /usr/local/bin/deno

WORKDIR /app
COPY generate_feed.py config.yml test_data.json requirements.txt ./

ENTRYPOINT ["python", "generate_feed.py"]
