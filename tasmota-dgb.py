import os
import sys
import json
import socket
import struct
import logging
import binascii
from time import sleep
from threading import Thread as t
import paho.mqtt.client as mqtt_client

MQTT_HOST = os.getenv('MQTT_HOST')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
MQTT_QOS = int(os.getenv('MQTT_QOS', 1))
BASE_TOPIC = os.getenv('BASE_TOPIC', 'tasmotadgrb')
HOME_ASSISTANT = os.getenv('HOME_ASSISTANT', True)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

dg_addr = '239.255.250.250'
dg_port = 4447

client = mqtt_client.Client(BASE_TOPIC)

power = ['OFF', 'ON']

devgroups = [
    b'tasmota_test',
    b'tasmota_test2'
]

zigbee2mqtt = {
    b'tasmota_test': '0x001788010383edc0'
}

def mqtt_connect():
    """Connect to MQTT broker and set LWT"""
    try:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        # client.will_set(f'{BASE_TOPIC}/status', 'offline', 1, True)
        client.on_connect = on_connect
        client.connect(MQTT_HOST, MQTT_PORT)
        # client.publish(f'{BASE_TOPIC}/status', 'online', 1, True)
    except Exception as e:
        logging.error(f'Unable to connect to MQTT broker: {e}')
        sys.exit()

def on_connect(client, userdata, flags, rc):
    # The callback for when the client receives a CONNACK response from the MQTT broker.
    logging.info('Connected to MQTT broker with result code ' + str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.

logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)s: %(message)s')
mqtt_connect()

# class DeviceGroup:
#     def device_group_intercept(self):
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
sock.bind((dg_addr, dg_port))
group = socket.inet_aton(dg_addr)
mreq = struct.pack('4sL', group, socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
while True:
    data, src = sock.recvfrom(128)
    for group in devgroups:
        if group in data:
            # print(data[data.find(b'\x00')+4:])
            if b'\xe0' in data:
                # tasmota color command
                info = data[data.find(b'\xe0'):]
                info = binascii.hexlify(info).decode()
                print(info)
                rgb = info[4:10]
                ct = info[10:14]
                print(rgb)
                print(ct)
                cw = int(info[10:12], 16)
                ww = int(info[12:14], 16)
                mired = int(327 - (173 * (cw / 255)) + (173 * (ww / 255)))
                print(mired)
                if rgb != '000000':
                    payload = json.dumps({'color': {'hex': f'#{rgb}'}})
                else:
                    payload = json.dumps({'color_temp': mired})
                client.publish(f'zigbee2mqtt/{zigbee2mqtt[group]}/set', payload)

            if b'\x80' in data:
                # tasmota power command
                info = data[data.find(b'\x80'):]
                info = binascii.hexlify(info).decode()
                pwr = int(info[2:4])
                if pwr in [0, 1]:
                    print(info)
                    print(pwr)
                    client.publish(f'zigbee2mqtt/{zigbee2mqtt[group]}/set', json.dumps({
                        'state': power[pwr]
                        }))

            if b'\x0a' in data:
                # tasmota brightness command
                info = data[data.find(b'\x0a'):]
                info = binascii.hexlify(info).decode()
                print(info)
                brt = int(info[2:4], 16)
                print(brt)
                client.publish(f'zigbee2mqtt/{zigbee2mqtt[group]}/set', json.dumps({
                    'brightness': brt
                    }))

# d = DeviceGroup()
# test = d.device_group_intercept()