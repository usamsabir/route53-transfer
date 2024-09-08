# Step 1: Use an official Ubuntu base image
FROM ubuntu:20.04

# Step 2: Set environment variables to prevent prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Step 3: Update the package list and install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Step 4: Set the working directory inside the container
WORKDIR /app/

# Step 5: Copy the local repository into the Docker image
COPY . /app

# Step 6: Install Python dependencies from requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Step 7: Set the command to run pytest
RUN pytest

CMD pytest