import configparser
import logging
import subprocess
import time
import json
import sys

from typing import Literal

REQUIRED_MIN_VERSION = (3, 8)

if sys.version_info < REQUIRED_MIN_VERSION:
    raise RuntimeError(f'Python version >= {REQUIRED_MIN_VERSION} is required')


CONFIG_PATH = '/etc/kde-bluetooth-lock/config.json'


def get_sessions() -> list:
    out = subprocess.run(
        ['loginctl', 'list-sessions', '--no-legend'],
        shell=False,
        check=True,
        capture_output=True,
    )
    sessions_raw = [
        row.split() for row in out.stdout.decode().strip().split('\n')
    ]
    sessions = [
        {
            'session': session[0],
            'uid': int(session[1]),
            'user': session[2],
            'seat': session[3],
            'leader': session[4],
            'class': session[5],
            'tty': session[6],
            'idle': bool(session[7]),
            'since': session[8],
        }
        for session in sessions_raw
    ]
    return sessions


def get_session_info(session_id: int) -> dict:
    try:
        out = subprocess.run(
            ['loginctl', 'show-session', str(session_id)],
            shell=False,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return {}
    session_info_config = configparser.RawConfigParser()
    session_info_config.optionxform = str  # Make configparser case sensitive
    # Hack: add a stub section header for configparser
    session_info_config.read_string(f'[0]\n{out.stdout.decode().strip()}')
    return dict(session_info_config['0'])


def get_active_session(sessions: list) -> int:
    for session in sessions:
        session_info = get_session_info(int(session['session']))
        if (
            session.get('seat') == 'seat0'
            and session.get('uid') >= 1000
            and session_info.get('Active') == 'yes'
        ):
            return session


def check_locked(session_id: int) -> bool:
    session_info = get_session_info(session_id)
    if session_info.get('LockedHint') == 'yes':
        return True
    return False


def probe_bt_mac(mac: str) -> bool:
    out = subprocess.run(
        [
            'l2ping',
            mac,
            '-t',
            '1',
            '-c',
            '1',
            '-s',
            '10',
        ],
        shell=False,
        check=False,
        capture_output=True,
    )
    if out.returncode == 0:
        logging.info(out.stdout.decode().strip().replace('\n', ' '))
        return True
    logging.error(out.stderr.decode().strip())
    return False


def send_system_notification(
    user_id: int,
    urgency: Literal['low', 'normal', 'critical'],
    title: str,
    message: str,
):
    subprocess.run(
        [
            'notify-send',
            '-u',
            urgency,
            '-a',
            title,
            message,
        ],
        shell=False,
        check=True,
        user=user_id,
        env={'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{user_id}/bus'},
    )


if __name__ == '__main__':
    with open(CONFIG_PATH) as fh:
        config = json.loads(fh.read())

    logging.basicConfig(
        format='%(levelname)s: %(message)s',
        level=config.get('log_level', 'INFO'),
    )

    while True:
        sessions = get_sessions()
        active_session = get_active_session(sessions)
        session_id = active_session.get('session')
        user_id = active_session.get('uid')
        if not session_id:
            continue
        if check_locked(session_id):
            continue

        tries = 0
        tries_max = config['retry']
        device_available = False
        while tries < tries_max:
            tries += 1
            for address in config['macs']:
                logging.info(
                    'Probing %s try: %d/%d, session: %s',
                    address,
                    tries,
                    tries_max,
                    session_id,
                )
                if probe_bt_mac(address):
                    device_available = True
                    break
                if config.get('notify', False):
                    send_system_notification(
                        user_id=user_id,
                        urgency='normal',
                        title='KDE Bluetooth Lock service',
                        message=(
                            f'Probing {address} failed\nTry {tries}/{tries_max}'
                        ),
                    )
            if device_available:
                break
            time.sleep(config['interval'])

        if not device_available:
            try:
                logging.info('Locking session %s', session_id)
                subprocess.run(
                    ['loginctl', 'lock-session', session_id],
                    shell=False,
                    check=True,
                )
            except subprocess.CalledProcessError:
                logging.error(
                    'Failed to lock session %s',
                    session_id,
                    exc_info=True,
                )
        time.sleep(config['interval'])
