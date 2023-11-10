install:
	install -D kde-bluetooth-lock.py /usr/share/kde-bluetooth-lock/kde-bluetooth-lock.py
	install -D config.json /etc/kde-bluetooth-lock/config.json
	install -D kde-bluetooth-lock.service /etc/systemd/system/kde-bluetooth-lock.service
	systemctl daemon-reload

uninstall:
	systemctl disable kde-bluetooth-lock.service || true
	rm -rf /usr/share/kde-bluetooth-lock/ /etc/systemd/system/kde-bluetooth-lock.service
	systemctl daemon-reload
