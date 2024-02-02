import argparse
import configparser
import logging
import subprocess
import time
import json
import sys


if not sys.version_info >= (3, 7):
    raise RuntimeError('Python version >= 3.7 is required', file=sys.stderr)


CONFIG_PATH = '/etc/kde-bluetooth-lock/config.json'


def get_sessions() -> list:
    out = subprocess.run(
        ['loginctl', '-o', 'json', 'list-sessions'],
        shell=False,
        check=True,
        capture_output=True,
    )
    return json.loads(out.stdout.decode().strip())


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


def get_active_session_id() -> int:
    sessions = get_sessions()
    session_id = None
    for session in sessions:
        session_info = get_session_info(int(session['session']))
        if (
            session.get('seat') == 'seat0'
            and session.get('uid') >= 1000
            and session_info.get('Active') == 'yes'
        ):
            session_id = int(session.get('session'))
            break
    return session_id


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


if __name__ == '__main__':
    config = {}
    try:
        with open(CONFIG_PATH) as fh:
            config = json.loads(fh.read())
    except FileNotFoundError:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--macs', type=str, nargs='+')
    parser.add_argument('-i', '--interval', type=int)
    parser.add_argument('-r', '--retry', type=int)
    parser.add_argument('-l', '--log-level', type=str)
    args = parser.parse_args()

    if args.macs:
        config['macs'] = args.macs
    if args.interval:
        config['interval'] = args.interval
    if args.retry:
        config['retry'] = args.retry
    if args.log_level:
        config['log_level'] = args.log_level

    logging.basicConfig(
        format='%(levelname)s: %(message)s',
        level=config.get('log_level', 'INFO'),
    )

    while True:
        current_id = get_active_session_id()
        if not current_id:
            continue
        if check_locked(current_id):
            continue

        tries = 0
        tries_max = config['retry']
        device_available = False
        while tries < tries_max:
            tries += 1
            for address in config['macs']:
                logging.info(
                    'Probing %s try: %d/%d, session: %d',
                    address,
                    tries,
                    tries_max,
                    current_id,
                )
                if probe_bt_mac(address):
                    device_available = True
                    break
            if device_available:
                break
            time.sleep(config['interval'])

        if not device_available:
            try:
                logging.info('Locking session %d', current_id)
                subprocess.run(
                    ['loginctl', 'lock-session', str(current_id)],
                    shell=False,
                    check=True,
                )
            except subprocess.CalledProcessError:
                logging.error(
                    'Failed to lock session %d',
                    current_id,
                    exc_info=True,
                )
        time.sleep(config['interval'])
