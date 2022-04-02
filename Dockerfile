FROM python:3

ADD tasmota-dgb.py /

RUN python3 -m pip install paho.mqtt colormath pyyaml

CMD [ "python", "./tasmota-dgb.py" ]