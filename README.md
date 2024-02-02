## Install

```bash
sudo ./install.sh
```


## Configure

To configure the service edit `/etc/kde-bluetooth-lock/config.json` file after the install.<br>
You can specify multiple mac addresses to be checked.


## Run

```bash
sudo systemctl enable --now kde-bluetooth-lock.service
```


## Uninstall

```bash
sudo ./install.sh -u
```
