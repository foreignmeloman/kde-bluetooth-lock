#!/bin/bash

if [ $(id -u) -ne 0 ]; then
  echo "ERROR: $0 must be run as root" >&2
  exit 1
fi

function install_kbl {
  set -x
  install -D kde-bluetooth-lock.py /usr/share/kde-bluetooth-lock/kde-bluetooth-lock.py
  mkdir -p /etc/kde-bluetooth-lock/ && cp -n config.json /etc/kde-bluetooth-lock/config.json
  install -D kde-bluetooth-lock.service /etc/systemd/system/kde-bluetooth-lock.service
  systemctl daemon-reload
  set +x
}

function uninstall_kbl {
  set -x
  systemctl stop kde-bluetooth-lock.service || true
  systemctl disable kde-bluetooth-lock.service || true
  rm -rf /usr/share/kde-bluetooth-lock/ /etc/systemd/system/kde-bluetooth-lock.service
  systemctl daemon-reload
  set +x
}

while getopts ":ui" option; do
  case $option in
    u)
      uninstall_kbl
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option ${option}"
      exit 1
  esac
done

install_kbl
