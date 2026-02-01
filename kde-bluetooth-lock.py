import configparser
import json
import logging
import shutil
import subprocess
import sys
import threading
import time

from typing import Literal

REQUIRED_MIN_VERSION = (3, 8)

if sys.version_info < REQUIRED_MIN_VERSION:
    raise RuntimeError(f'Python version >= {REQUIRED_MIN_VERSION} is required')


CONFIG_PATH = '/etc/kde-bluetooth-lock/config.json'


class RawCaseSensitiveConfigParser(configparser.RawConfigParser):
    """
    A case sensitive variant of configparser.RawConfigParser class
    """

    def optionxform(self, optionstr: str) -> str:
        return str(optionstr)


def get_loginctl_version() -> int:
    out = subprocess.run(
        ['loginctl', '--version'],
        shell=False,
        check=True,
        capture_output=True,
    )
    version_line = out.stdout.decode().strip().split('\n')[0]
    return int(version_line.split()[1])


LOGINCTL_VERSION = get_loginctl_version()


def get_sessions() -> list:
    cmd = ['loginctl', '-o', 'json', 'list-sessions']
    if LOGINCTL_VERSION >= 256:
        cmd = ['loginctl', '--json=short', 'list-sessions']
    out = subprocess.run(
        cmd,
        shell=False,
        check=True,
        capture_output=True,
    )
    return json.loads(out.stdout.decode().strip())


def get_session_info(session_id: str) -> dict:
    try:
        out = subprocess.run(
            ['loginctl', 'show-session', session_id],
            shell=False,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return {}
    session_info_config = RawCaseSensitiveConfigParser()
    # Hack: add a stub section header for configparser
    session_info_config.read_string(f'[0]\n{out.stdout.decode().strip()}')
    return dict(session_info_config['0'])


def get_active_session(sessions: list) -> tuple[dict, dict]:
    """Returns (session, session_info) tuple for the active session."""
    for session in sessions:
        session_id = str(session['session'])
        session_info = get_session_info(session_id)
        if (
            session.get('seat') == 'seat0'
            and session.get('uid') >= 1000
            and session_info.get('Active') == 'yes'
        ):
            return {**session, 'session': session_id}, session_info
    return {}, {}


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


def _run_notification(
    cmd: list,
    user_id: int,
    env: dict,
    postpone_event: threading.Event | None,
):
    try:
        out = subprocess.run(
            cmd,
            shell=False,
            check=True,
            capture_output=True,
            user=user_id,
            env=env,
        )
        if (
            postpone_event is not None
            and out.stdout.decode().strip() == 'postpone'
        ):
            logging.info('User requested postpone')
            postpone_event.set()
    except subprocess.CalledProcessError as err:
        logging.warning(
            'Failed to send desktop notification: %s',
            err.stderr.decode().strip(),
        )


def send_system_notification(
    user_id: int,
    urgency: Literal['low', 'normal', 'critical'],
    title: str,
    message: str,
    postpone_event: threading.Event | None = None,
):
    if not shutil.which('notify-send'):
        logging.warning(
            'notify-send was not found in your PATH. '
            'Skipping desktop notifications'
        )
        return

    cmd = ['notify-send', '-u', urgency, '-a', title]
    if postpone_event is not None:
        cmd.extend(['--action=postpone=Postpone', '--wait'])
    cmd.append(message)

    env = {'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{user_id}/bus'}

    if postpone_event is not None:
        thread = threading.Thread(
            target=_run_notification,
            args=(cmd, user_id, env, postpone_event),
            daemon=True,
        )
        thread.start()
    else:
        _run_notification(cmd, user_id, env, postpone_event)


if __name__ == '__main__':
    with open(CONFIG_PATH) as fh:
        config = json.loads(fh.read())

    logging.basicConfig(
        format='%(levelname)s: %(message)s',
        level=config.get('log_level', 'INFO'),
    )

    interval = config.get('interval', 10)

    while True:
        sessions = get_sessions()
        active_session, session_info = get_active_session(sessions)
        if not active_session:
            logging.debug('sessions = %s', str(sessions))
            time.sleep(interval)
            continue
        session_id = active_session['session']
        user_id = active_session['uid']
        if session_info.get('LockedHint') == 'yes':
            time.sleep(interval)
            continue

        tries = 0
        tries_max = config.get('retry', 3)
        notify_threshold = (
            tries_max * config.get('notify_after_loss_percent', 50)
        ) // 100
        device_available = False
        postpone_event = threading.Event()
        while tries < tries_max:
            if postpone_event.is_set():
                logging.info('Postpone requested, resetting retry count')
                tries = 0
                postpone_event.clear()
            tries += 1
            for address in config.get('macs', []):
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
            if device_available:
                break
            if config.get('notify', False) and tries >= notify_threshold:
                send_system_notification(
                    user_id=user_id,
                    urgency='normal',
                    title='KDE Bluetooth Lock service',
                    message=f'All devices unreachable\nTry {tries}/{tries_max}',
                    postpone_event=postpone_event,
                )
            time.sleep(interval)

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
        time.sleep(interval)
