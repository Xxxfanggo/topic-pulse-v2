ARG NODE_IMAGE=docker.m.daocloud.io/library/node:22-bookworm
ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.10-slim

FROM ${NODE_IMAGE} AS frontend

WORKDIR /app/src/topic_pulse_v2_chat/web/frontend

COPY src/topic_pulse_v2_chat/web/frontend/package*.json ./
RUN npm ci

COPY src/topic_pulse_v2_chat/web/frontend ./
RUN npm run build


FROM ${PYTHON_IMAGE} AS app

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV TOPIC_PULSE_DATA_DIR=/app/data

COPY requirements.txt pyproject.toml README.md ./
COPY src ./src
COPY --from=frontend /app/src/topic_pulse_v2_chat/web/frontend/dist ./src/topic_pulse_v2_chat/web/frontend/dist

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "topic_pulse_v2_chat.web:app", "--host", "0.0.0.0", "--port", "8000"]
