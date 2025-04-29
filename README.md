# R3_Docker
A containerized CLI solution for managing R3 Bridge E devices — enabling state monitoring, configuration management, and ring operations.

## Features

- **State Monitoring:** Monitors the state of R3 devices in real-time.
- **Configuration Management:** Provides a CLI interface for managing configurations.
- **Ring Operations:** Enables operations related to ring management of R3 devices.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/WICON-RPTU/Docker_R3Device_manager.git

2. Build the Docker image:
   ```bash
   docker build -t r3device_manager .

3. Run the Container:
   ```bash
   docker run -it r3device_manager
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



