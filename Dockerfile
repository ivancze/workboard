FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .

# The stylesheet is generated, never committed: build it here so collectstatic
# picks it up, and fail the image if Tailwind fails. bin/tailwind picks the
# binary for this machine's architecture (arm64 locally, amd64 on Render) and
# checks its checksum; the binary is removed in the same layer so it never ships.
RUN python bin/tailwind build --minify && rm -rf .bin

# Collect static during the build so the running container does no startup work
# and needs no writable filesystem. Settings require these variables to exist;
# the throwaway values here are never used for anything but this command.
RUN SECRET_KEY=build-only DATABASE_URL=postgres://u:p@localhost/db \
    python manage.py collectstatic --noinput

CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --access-logfile - --error-logfile -"]
