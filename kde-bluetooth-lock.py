import argparse
import subprocess
import time
import json
import sys


if not sys.version_info >= (3, 7):
    raise RuntimeError('Python version >= 3.7 is required', file=sys.stderr)


CONFIG_PATH = '/etc/kde-bluetooth-lock/config.json'


def get_session_id() -> int:
    out = subprocess.run(
        ['loginctl', '-o', 'json', 'list-sessions'],
        shell=False,
        check=True,
        capture_output=True,
    )
    sessions = json.loads(out.stdout.decode().strip())
    session_id = None
    for session in sessions:
        if session.get('seat') == 'seat0' and session.get('uid') >= 1000:
            session_id = int(session.get('session'))
            break
    return session_id


def check_locked(session_id: int) -> bool:
    out = subprocess.run(
        ['loginctl', 'show-session', str(session_id)],
        shell=False,
        check=True,
        capture_output=True,
    )
    lines = out.stdout.decode().strip().split('\n')
    locked_line = list(filter(lambda x: x.startswith('LockedHint'), lines))[0]
    if locked_line.split('=')[1] == 'yes':
        return True
    return False


def probe_bt_mac(mac: str) -> bool:
    try:
        subprocess.run(
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
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
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
    args = parser.parse_args()

    if args.macs:
        config['macs'] = args.macs
    if args.interval:
        config['interval'] = args.interval
    if args.retry:
        config['retry'] = args.retry

    while True:
        current_id = get_session_id()
        if not current_id:
            continue
        is_locked = check_locked(current_id)
        if is_locked:
            continue

        tries = 0
        tries_max = config['retry']
        device_available = False
        while tries < tries_max:
            tries += 1
            for address in config['macs']:
                print(f'Probing {address} try: {tries}/{tries_max}', flush=True)
                if probe_bt_mac(address):
                    device_available = True
                    break
            if device_available:
                break
            time.sleep(config['interval'])

        if not device_available:
            print(f'Locking session {current_id}', flush=True)
            subprocess.run(
                ['loginctl', 'lock-session', str(current_id)],
                shell=False,
                check=True,
            )
        time.sleep(config['interval'])
