import paho.mqtt.client as mqtt

# MQTT Broker settings
broker_address = "localhost"  
port = 1337
topic = "/echoring"
ack_topic = "/ack"  
Payload = "ON"  

# MQTTv5: Updated connect callback signature
def on_connect(client, userdata, flags, reasonCode, properties):
    print(f"Connected with reason code {reasonCode}")
    client.publish(topic, Payload)
    print(f"Sent {Payload} message to {topic}")

def on_ack_message(client, userdata, msg):
    ack_payload = msg.payload.decode("utf-8")
    print(f"Received ACK from listener: {ack_payload}")

# Create client with MQTTv5 protocol
client = mqtt.Client(protocol=mqtt.MQTTv5)
client.on_connect = on_connect
client.on_message = on_ack_message

client.connect(broker_address, port, 60)
client.subscribe(ack_topic)

client.loop_forever()
