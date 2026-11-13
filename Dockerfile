FROM python:3.12-slim

# LightGBM needs OpenMP at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system .
COPY app ./app

EXPOSE 8501
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0"]
