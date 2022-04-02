import os
import sys
import json
import yaml
import socket
import struct
import logging
import binascii
from colormath.color_objects import XYZColor, AdobeRGBColor
from colormath.color_conversions import convert_color
from time import sleep
from threading import Thread as t
import paho.mqtt.client as mqtt_client

with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

mqtt_config = config['mqtt']
tasmota_config = config['tasmota']

MQTT_HOST = str(mqtt_config['host'])
MQTT_PORT = int(mqtt_config['port'])
MQTT_USER = str(mqtt_config['user'])
MQTT_PASSWORD = str(mqtt_config['password'])
MQTT_QOS = int(os.getenv('MQTT_QOS', 1))
LOG_LEVEL = str(config['general']['log_level'].upper())

dg_addr = str(tasmota_config['devgroup_address'])
dg_port = int(tasmota_config['devgroup_port'])

config_dg = tasmota_config['devgroups']
client = mqtt_client.Client('tasmota-DGB')
devgroups = list(config_dg.keys())
devgroups_z2m = dict(config_dg.items())
z2m_devgroups = {}
z2m_topics = []

for k,v in devgroups_z2m.items():
    for v1 in v:
        z2m_devgroups[v1] = k

logging.debug(devgroups_z2m)
logging.debug(z2m_devgroups)

def extract_topics(topic):
    for v in config_dg.values():
        if isinstance(v, dict):
            yield from extract_topics(v)
        else:
            yield v

z2m_topics = list(extract_topics(config_dg))
extracted_z2m_topics = []
for item in z2m_topics:
    extracted_z2m_topics += item

z2m_base_topic = config['zigbee2mqtt']['base_topic']
power = ['OFF', 'ON']

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
    for topic in extracted_z2m_topics:
        client.subscribe(f'{z2m_base_topic}/{topic}/set')

def on_message(client, userdata, msg):
    """Listen for MQTT payloads"""
    payload = json.loads(msg.payload.decode('utf-8'))
    logging.debug(payload)
    topic = str(msg.topic.replace(f'{z2m_base_topic}/',"").replace('/set',""))
    if 'color' in payload:
        x = float(payload['color']['x'])
        y = float(payload['color']['y'])
        z = 1 - x - y
        xyz_color = XYZColor(x, y, z, 10)
        rgb_color = convert_color(xyz_color, AdobeRGBColor)
        value = '#%02x%02x%02x' % (int(rgb_color.clamped_rgb_r * 255), int(rgb_color.clamped_rgb_g * 255), int(rgb_color.clamped_rgb_b * 255))
        logging.debug(rgb_color)
        d.devgroup_publisher(f'cmnd/{z2m_devgroups[topic]}/color', value, z2m_devgroups[topic])

    if 'color_temp' in payload:
        value = payload['color_temp']
        d.devgroup_publisher(f'cmnd/{z2m_devgroups[topic]}/ct', value, z2m_devgroups[topic])

    if 'state' in payload:
        value = payload['state']
        d.devgroup_publisher(f'cmnd/{z2m_devgroups[topic]}/power', value, z2m_devgroups[topic])

    if 'brightness' in payload:
        value = payload['brightness']
        d.devgroup_publisher(f'cmnd/{z2m_devgroups[topic]}/dimmer', int(value / 2.55), z2m_devgroups[topic])
    
    if 'throttled' in payload:
        value = payload['throttled']
        d.mark_throttled(topic, value)

logging.basicConfig(level='INFO', format='%(asctime)s %(levelname)s: %(message)s')
mqtt_connect()

class DeviceGroup:
    def __init__(self):
        self.cmds = {
            'power': b'\x80',
            'brightness': b'\x0a',
            'color': b'\xe0'
        }
        self.payloads = {}
        for group in devgroups:
            self.payloads[group] = {}
        self.throttled = {}
        for group in devgroups:
            self.throttled[group] = False

    def mark_throttled(self, group, value):
        self.throttled[devgroups[group]] = value

    def devgroup_discover(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        for group in devgroups:
            group_name = f'TASMOTA_DGR{group}'
            payload = f'{group_name}\x00\x01\x00\x03\x00'
            try:
                payload_bytes = payload.encode()
            except Exception as e:
                logging.debug(f'{e}')
            sock.sendto(payload_bytes, (dg_addr, dg_port))

    def devgroup_listener(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.bind((dg_addr, dg_port))
        group = socket.inet_aton(dg_addr)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def devgroup_publisher(self, topic, payload, devgroup):
        if not self.throttled[devgroup]:
            client.publish(topic, payload)
            self.throttled[devgroup] = False

    def devgroup_converter(self):
        cmd = self.cmds
        while True:
            data, src = self.sock.recvfrom(128)
            logging.debug('data_received:', data, src)
            devgroup = data[:data.find(b'\x00')].replace(b'TASMOTA_DGR',b'').decode('utf-8')
            logging.debug(devgroup)
            for group in devgroups:
                if group.encode() in data:
                    logging.debug(data)
                    if cmd['color'] in data or (cmd['color'] in data and cmd['power'] in data):
                        color = data[data.find(cmd['color']):]
                        color = binascii.hexlify(color).decode()
                        rgb = color[4:10]
                        cw = int(color[10:12], 16)
                        ww = int(color[12:14], 16)
                        mired = int(327 - (173 * (cw / 255)) + (173 * (ww / 255)))
                        pwr = data[data.find(cmd['power']):]
                        logging.debug(f'pwr_only: {pwr}')
                        pwr = binascii.hexlify(pwr).decode()
                        try:
                            pwr = int(pwr[2:4])
                        except Exception as e:
                            logging.error(e)
                        if pwr:
                            if rgb != '000000':
                                self.payloads[group]['color'] = {'hex': f'#{rgb}'}
                            else:
                                self.payloads[group]['color_temp'] = mired
                        # if pwr:
                        #     for topic in devgroups_z2m[devgroup]:
                        #         print('color send')
                        #         client.publish(f'zigbee2mqtt/{topic}/set', payload)

                    if cmd['brightness'] in data or (cmd['power'] in data and cmd['brightness'] in data):
                        logging.debug(f'brt: {data}')
                        brt = data[data.find(group.encode())+10:]
                        brt = data[data.find(b'\x05'):]
                        brt = binascii.hexlify(brt).decode()
                        logging.debug(brt)
                        brt = int(brt[2:4], 16)
                        pwr = data[data.find(cmd['power']):]
                        logging.debug(f'pwr: {pwr}')
                        pwr = binascii.hexlify(pwr).decode()
                        pwr = int(pwr[2:4])
                        self.payloads[group]['state'] = power[pwr]
                        if pwr:
                            self.payloads[group]['brightness'] = brt
                        #     for topic in devgroups_z2m[devgroup]:
                        #         print('brt send')
                        #         client.publish(f'zigbee2mqtt/{topic}/set', json.dumps({'brightness': brt, 'power': power[pwr]}))
                        # elif not pwr:
                        #     for topic in devgroups_z2m[devgroup]:
                        #         print('brt send')
                        #         client.publish(f'zigbee2mqtt/{topic}/set', json.dumps({'state': power[pwr]}))

                    elif cmd['power'] in data:
                        info = data[data.find(cmd['power']):]
                        logging.debug(f'pwr_only: {info}')
                        info = binascii.hexlify(info).decode()
                        pwr = int(info[2:4])
                        if pwr in [0, 1]:
                            self.payloads[group]['state'] = power[pwr]
                            # for topic in devgroups_z2m[devgroup]:
                            #     print('power send')
                            #     client.publish(f'zigbee2mqtt/{topic}/set', json.dumps({'state': power[pwr]}))
                if not self.throttled[group]:
                    for topic in devgroups_z2m[devgroup]:
                        client.publish(f'zigbee2mqtt/{topic}/set', json.dumps(self.payloads[group]))
                        self.payloads[group] = {}
                        self.throttled[group] = False

d = DeviceGroup()

dgl = t(target=d.devgroup_listener, daemon=True)
dgl.start()
sleep(3)
d.devgroup_discover()
dgc = t(target=d.devgroup_converter, daemon=True)
dgc.start()
client.loop_forever()