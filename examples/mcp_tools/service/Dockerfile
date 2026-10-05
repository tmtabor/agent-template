# The calendar MCP server as a container image. Built and started by docker-compose.yml.
FROM python:3.13-slim

RUN pip install --no-cache-dir "fastmcp-slim[server]>=4.0,<5"

WORKDIR /app
COPY server.py .

# Listen on all interfaces inside the container; Compose publishes the port to 127.0.0.1 only.
ENV MCP_HOST=0.0.0.0 MCP_PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]
