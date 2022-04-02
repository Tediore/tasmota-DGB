This is a proof of concept and is very much in alpha stage. There will be likely more to come regarding this with LightConstrue (https://github.com/LightConstrue)

The code is also currently very messy. Sorry.

See config-example.yaml for the required user config.

```
docker run --volume=/path/to/config.yaml:/config.yaml:ro --network=host --name=tasmota-dgb tediore/tasmota-dgb:alpha
```

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