FROM ubuntu:20.04

# Step 2: Set environment variables to prevent prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Step 3: Update the package list and install system dependencies including Git
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Step 4: Set the working directory inside the container
WORKDIR /route53-transfer/

# Step 5: Copy the local repository into the Docker image
COPY . /route53-transfer

# Step 6: Install Python dependencies from requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Step 7: Run pytest
RUN pytest

CMD pytest

# DO NOT CHANGE ANY BELOW CODE
WORKDIR /
RUN apt-get update && apt-get install -y bash
COPY run_tests.sh ./
RUN chmod +x /run_tests.sh
ENTRYPOINT ["/bin/bash", "-s"]