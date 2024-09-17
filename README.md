## Install

```bash
sudo ./install.sh
```


## Configure

To configure the service edit `/etc/kde-bluetooth-lock/config.json` file after the install.<br>

Available configuration options:

| Option | Description
| ------ | -----------
| `macs` | A json list of mac address strings of the deivices to be monitored
| `interval` | Interval in seconds between polls
| `retry` | Retry count
| `log_level` | Verbosity level of the logs. Possible values: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
| `notify` | A json boolean to enable desktop notifications
| `notify_after_loss_percent`| Notifications will be sent after the percentage of failed poll tries exceeds the specified threshold

## Run

```bash
sudo systemctl enable --now kde-bluetooth-lock.service
```


## Uninstall

```bash
sudo ./install.sh -u
```
