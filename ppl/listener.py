import paho.mqtt.client as mqtt
import subprocess
import os

# MQTT Broker settings
broker_address = "192.168.0.100"
port = 1883
topic = "/echoring"
ack_topic = "/ack"
ip1 = '192.168.0.118'

# Directory where you want to run the command
command_directory = "/app"

# Callback when connected to the broker
def on_connect(client, userdata, flags, rc, *extra):
    print(f"Connected with result code {rc}")
    client.subscribe(topic)

# Callback when a message is received
def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    print(f"Received message: {payload}")

    if payload == "ON":
        command = f"poetry run r3erci {ip1} ring 2 1"
    elif payload == "OFF":
        command = f"poetry run r3erci {ip1} ring 1 1"
    else:
        print("Invalid payload. Expected 'ON' or 'OFF'.")
        return

    try:
        print(f"Running command: {command}")
        result = subprocess.run(command, shell=True, check=True, cwd=command_directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        stdout_output = result.stdout.decode("utf-8").strip()

        if "SUCCESS" in stdout_output:
            ack_message = f"Tx_Power of {ip1} changed"
        elif "no response in 10 seconds" in stdout_output.lower() or "raised error" in stdout_output.lower():
            ack_message = f"Error: No response from {ip1}"
        else:
            ack_message = stdout_output

        print(f"Sending ACK: {ack_message}")
        client.publish(ack_topic, ack_message)

    except subprocess.CalledProcessError as e:
        print(f"Command failed with exception: {e}")
        client.publish(ack_topic, f"Error: Command execution failed")

# Create MQTT client instance
client = mqtt.Client(protocol=mqtt.MQTTv5)
client.on_connect = on_connect
client.on_message = on_message

client.connect(broker_address, port, 60)
client.loop_forever()
