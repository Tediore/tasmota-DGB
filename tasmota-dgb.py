import os
import sys
import json
import socket
import struct
import logging
import binascii
from colormath.color_objects import XYZColor, AdobeRGBColor
from colormath.color_conversions import convert_color
from time import sleep
from threading import Thread as t
import paho.mqtt.client as mqtt_client

MQTT_HOST = os.getenv('MQTT_HOST')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
MQTT_QOS = int(os.getenv('MQTT_QOS', 1))
BASE_TOPIC = os.getenv('BASE_TOPIC', 'tasmota-DGB')
HOME_ASSISTANT = os.getenv('HOME_ASSISTANT', True)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

dg_addr = '239.255.250.250'
dg_port = 4447

client = mqtt_client.Client(BASE_TOPIC)

power = ['OFF', 'ON']

devgroups = [
    'tasmota_test',
    'tasmota_test2'
]

zigbee2mqtt = {
    'tasmota_test': '0x001788010383edc0'
}

z2m_base_topic = 'zigbee2mqtt'

def mqtt_connect():
    """Connect to MQTT broker and set LWT"""
    try:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        # client.will_set(f'{BASE_TOPIC}/status', 'offline', 1, True)
        client.on_connect = on_connect
        client.on_message = on_message
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
    client.subscribe(f'{z2m_base_topic}/0x001788010383edc0/set')

def on_message(client, userdata, msg):
    """Listen for MQTT payloads"""
    payload = json.loads(msg.payload.decode('utf-8'))
    print(payload)
    topic = str(msg.topic)
    if 'color' in payload:
        x = float(payload['color']['x'])
        y = float(payload['color']['y'])
        z = 1 - x - y
        xyz_color = XYZColor(x, y, z, 10)
        rgb_color = convert_color(xyz_color, AdobeRGBColor)
        rgb_color = '#%02x%02x%02x' % (int(rgb_color.clamped_rgb_r * 255), int(rgb_color.clamped_rgb_g * 255), int(rgb_color.clamped_rgb_b * 255))
        print(rgb_color)
        d.devgroup_publisher(rgb_color)

logging.basicConfig(level='INFO', format='%(asctime)s %(levelname)s: %(message)s')
mqtt_connect()

class DeviceGroup:
    def __init__(self):
        self.throttle = 0
        self.cmds = {
            'power': b'\x80',
            'brightness': b'\x0a',
            'color': b'\xe0'
        }

    def devgroup_discover(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        for group in devgroups:
            group_name = f'TASMOTA_DGR{group}'
            payload = f'{group_name}\x00\x01\x00\x03\x00'
            try:
                payload_bytes = payload.encode()
            except Exception as e:
                print(f'{e}')
            sock.sendto(payload_bytes, (dg_addr, dg_port))

    def devgroup_listener(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.bind((dg_addr, dg_port))
        group = socket.inet_aton(dg_addr)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def devgroup_publisher(self, payload):
        client.publish('cmnd/tasmota_test/color', payload)
        self.throttle = 1

    def devgroup_converter(self):
        cmd = self.cmds
        while True:
            data, src = self.sock.recvfrom(128)
            print('data_received:', data, src)
            for group in devgroups:
                if group.encode() in data:
                    print(data)
                    # print(data[data.find(b'\x00')+4:])
                 
                    if cmd['color'] in data or (cmd['color'] in data and cmd['power'] in data):
                        if self.throttle:
                            self.throttle = 0
                        else:
                            color = data[data.find(cmd['color']):]
                            color = binascii.hexlify(color).decode()
                            rgb = color[4:10]
                            cw = int(color[10:12], 16)
                            ww = int(color[12:14], 16)
                            mired = int(327 - (173 * (cw / 255)) + (173 * (ww / 255)))
                            pwr = data[data.find(cmd['power']):]
                            print(f'pwr_only: {pwr}')
                            pwr = binascii.hexlify(pwr).decode()
                            pwr = int(pwr[2:4])
                            if rgb != '000000':
                                payload = json.dumps({'color': {'hex': f'#{rgb}'}})
                            else:
                                payload = json.dumps({'color_temp': mired})
                            if pwr:
                                client.publish(f'zigbee2mqtt/{zigbee2mqtt[group]}/set', payload)

                    if cmd['brightness'] in data or (cmd['power'] in data and cmd['brightness'] in data):
                        print(f'brt: {data}')
                        brt = data[data.find(group.encode())+10:]
                        brt = data[data.find(b'\x05'):]
                        brt = binascii.hexlify(brt).decode()
                        print(brt)
                        brt = int(brt[2:4], 16)
                        pwr = data[data.find(cmd['power']):]
                        print(f'pwr: {info}')
                        pwr = binascii.hexlify(pwr).decode()
                        pwr = int(pwr[2:4])
                        if pwr:
                            client.publish(f'zigbee2mqtt/{zigbee2mqtt[group]}/set', json.dumps({'brightness': brt, 'power': power[pwr]}))
                        elif not pwr:
                            client.publish(f'zigbee2mqtt/{zigbee2mqtt[group]}/set', json.dumps({'state': power[pwr]}))

                    elif cmd['power'] in data:
                        info = data[data.find(cmd['power']):]
                        print(f'pwr_only: {info}')
                        info = binascii.hexlify(info).decode()
                        pwr = int(info[2:4])
                        if pwr in [0, 1]:
                            client.publish(f'zigbee2mqtt/{zigbee2mqtt[group]}/set', json.dumps({'state': power[pwr]}))

d = DeviceGroup()
# test = d.device_group_intercept()

dgl = t(target=d.devgroup_listener, daemon=True)
dgl.start()
sleep(3)
d.devgroup_discover()
dgc = t(target=d.devgroup_converter, daemon=True)
dgc.start()
client.loop_forever()