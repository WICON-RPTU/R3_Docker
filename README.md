# R3_Docker
A containerized CLI solution for managing R3 Bridge E devices — enabling state monitoring, configuration management, and ring operations.

## Features

- **State Monitoring:** Offers real-time visibility into the operational status of R3 devices.
- **Configuration Management:** Facilitates efficient deployment and management of device configurations.
- **Ring Operations:** Enables operations related to ring management of R3 devices.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/WICON-RPTU/R3_Docker.git
   sudo apt-get install -y ca-certificates curl gnupg lsb-release
   sudo apt install docker.io

2. Go to the Directory and build the Docker image:
   ```bash
   cd R3_Docker
   sudo usermod -aG docker $USER
   newgrp docker
   docker build -t r3-app .

3. Run the Container:
   ```bash
   docker run -it r3-app
## Usage

Once the container is running, you can interact with the CLI to manage R3 Bridge E devices. Below are the available commands:
# Device Management
## 1. **State Monitoring**
To monitor the state of a device, use the following command:
  ```bash
  poetry run r3erci <ip_address> state
```
## 2. **Configuration**
To configure :
```bash
poetry run ppl configure <ip_address> <config_file>.json
````
To Run "ppl" commands there might be some warning to clear those:
Inside the container run:
```bash
poetry install
poetry lock
````
After this there will be no warning in current container, we can make use of this container by noting down its name or it container ID, in this way the warning doesnt come in future.

To Run Known Container:
```bash
docker start "container_ID"
docker exec -it "container_ID" /bin/bash
```
To Check container ID or name use this:
```bash
docker ps -a
