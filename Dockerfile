# Step 1: Use an official Ubuntu base image
FROM ubuntu:20.04

# Step 2: Set environment variables to prevent prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Step 3: Update the package list and install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
# Clone the repository from GitHub
WORKDIR /app/

RUN git clone --branch code_transformations https://github.com/usamsabir/route53-transfer.git

# Step 6: Install Python dependencies from requirements.txt
RUN pip3 install --no-cache-dir -r route53-transfer/requirements.txt

CMD pytest