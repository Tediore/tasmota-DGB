This allows you to control zigbee2mqtt devices via Tasmota device groups. This is a proof of concept and is very much in alpha stage. There will be likely more to come regarding this with LightConstrue (https://github.com/LightConstrue)

Each device in each Tasmota device group needs to have a grouptopic that's the same as the devgroupname. **Don't use grouptopic1!** Use grouptopic2, 3, or 4

The code is also currently very messy. Sorry.

See config-example.yaml for the required user config.

docker run
```
docker run --volume=/path/to/config.yaml:/config.yaml:ro --network=host --name=tasmota-dgb tediore/tasmota-dgb:alpha
```

docker compose
```yaml
version: '3'
services:
  tasmota-dgb:
    container_name: tasmota-dgb
    image: tediore/tasmota-dgb:alpha
    volumes:
    - /path/to/config.yaml:/config.yaml:ro
    restart: unless-stopped
    network_mode: host #required
```