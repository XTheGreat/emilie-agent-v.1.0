# Dockerfile patterns

Python:
```dockerfile
FROM python:3.12-slim AS build
WORKDIR /app
COPY pyproject.toml requirements*.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
FROM python:3.12-slim
RUN useradd -r -u 10001 app
WORKDIR /app
COPY --from=build /install /usr/local
COPY --chown=app . .
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8000/health')"
CMD ["python", "-m", "myapp"]
```
Node: `FROM node:22-alpine`, copy `package*.json`, `npm ci --omit=dev`, then source; `USER node`.
Go/Rust: build in a toolchain stage, copy the static binary to `gcr.io/distroless/static` or `scratch`.
.dockerignore: `.git`, `node_modules`, `__pycache__`, `.venv`, `.env*`, `*.log`, `dist`, tests if not needed.
Use exec-form `CMD ["..."]` so the app receives SIGTERM as PID 1; add `tini` if it does not reap children.
