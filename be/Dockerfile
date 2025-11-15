FROM ghcr.io/astral-sh/uv:python3.13-alpine

# Set the working directory
WORKDIR /app

# Copy and install dependencies first (for better layer caching)
COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml

# Copy the application code
COPY src ./src

# Create a directory for the SQLite database
RUN mkdir -p /data

# Expose the port Uvicorn will run on
EXPOSE 8000

# Command to run the application (without reload for production)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]