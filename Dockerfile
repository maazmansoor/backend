# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port (default 8000, but Railway sets $PORT)
EXPOSE 8000

# Start the app using Gunicorn, binding to $PORT
  CMD gunicorn --bind 0.0.0.0:8000 app:app
