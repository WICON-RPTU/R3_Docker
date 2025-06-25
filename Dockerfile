FROM python:3.11-slim
FROM docker
COPY --from=docker/buildx-bin /buildx /usr/libexec/docker/cli-plugins/docker-buildx
# Install curl
RUN apt-get update && apt-get install -y curl iputils-ping nano
RUN pip3 install paho-mqtt

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy everything from the `ppl` folder
COPY ppl/pyproject.toml /app/
COPY ppl/poetry.lock /app/
COPY ppl/ /app/

# Install dependencies
RUN poetry install --no-root

# Default command
CMD ["bash"]







