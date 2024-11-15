# Use Python 3.10 as the base image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5000 (or whatever port your application uses)
EXPOSE 5000

# Define the command to run your application
CMD ["gunicorn", "-k", "gevent", "-w", "1", "app:app", "--bind", "0.0.0.0:5000"]
