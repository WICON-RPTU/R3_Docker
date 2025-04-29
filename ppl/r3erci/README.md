Starting r3erci
======

In order to launch r3erci, execute

```shell
poetry install
poetry run r3erci <IP> <CMD>
```

This will first install all dependencies using [python-poetry](https://python-poetry.org/docs/), then launch the actual application.

If you have poetry not available, you can use the basic run file with following command:

```shell
python3 -m r3erci <IP> <CMD>
```

If you install the package, you can use r3erci directly in the terminal

```shell
r3erci <IP> <CMD>
```

Additional commands
======

Run a command (without arguments like ring id or config id) on multiple nodes (defined in file IP_LIST):

```shell
poetry run r3erci-batch <CMD> <PATH_TO_IP_LIST>
```

Use the sequencer to cycle through two configs (each 5s) on one EREB

```shell
poetry run r3erci-sequencer <IP>
```

Use the simulate ereb to open a r3erci host on a real interface

```shell
poetry run r3erci-simulate-ereb
```

Recommended tools
======

```bash
poetry run pre-commit install
poetry run pre-commit run --all-files
```
