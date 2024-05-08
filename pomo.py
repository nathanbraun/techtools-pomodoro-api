import os
import argparse
import json
import requests
from textwrap import dedent
import humanfriendly
from tzlocal import get_localzone
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PASSKEY = os.environ.get('PASSKEY', 'TECHTOOLS1')
API_URL = os.environ.get('API_URL')

parser = argparse.ArgumentParser(
  description="Run a pomodoro.")

parser.add_argument(
    '-n', '--name',
    help="Description. Defaults to directory name.",
    required=False)

parser.add_argument(
    '-d', '--duration',
    help="Duration in minutes. Defaults to 30m.",
    default="30m",
    required=False)

parser.add_argument(
    '-t', '--test',
    nargs='?',
    const='default_test',
    help="Run in test mode. If a date is provided, run with date-specific logic.",
    default=None  # default=None means by default -t/--test is not considered
)

args = vars(parser.parse_args())

desc = args['name']
dur = args['duration']

dur_sec = round(humanfriendly.parse_timespan(dur))

if desc is None:
    desc = os.getcwd().split('/')[-1]

if args['test'] is not None:
    if args['test'] == 'default_test':
        # -t or --test was provided with no argument
        mutation = dedent(
            f"""
            mutation {{
                pomodoro (key: "{PASSKEY}", duration: {dur_sec}, project: "{desc}", test: true) {{
                    id,
                    duration
                }}
                }}
            """)

    else:
        # -t or --test was provided with an argument
        date_arg = args['test']
        try:
            local_timezone = get_localzone()
            specific_datetime = datetime.fromisoformat(date_arg)
            local_datetime = specific_datetime.astimezone(local_timezone)
            # local_datetime = local_timezone.localize(specific_datetime)
            posix_timestamp = int(local_datetime.timestamp())

            print(f"Do something else for the date and time: {posix_timestamp}")

            # send to API
            mutation = dedent(
                f"""
                mutation {{
                    pomodoro (key: "{PASSKEY}", duration: {dur_sec}, project: "{desc}", start: {posix_timestamp}, test: true) {{
                        id,
                        duration
                    }}
                    }}
                """)

        except ValueError:
            print("Invalid date format. Please use the ISO 8601 format: YYYY-MM-DDTHH:MM:SS")

    r = requests.post(API_URL, json={'query': mutation})
    if 'data' in json.loads(r.text):
        print('Pomodoro added to db successfully.')
else:
    # neither -t nor --test was provided
    # duration in seconds

    # run actual pomodoro

    pomo_command = os.path.expanduser("~/go/bin/pomodoro")
    pomo = os.system(f'noti {pomo_command} --simple {dur}')
    zone = str(get_localzone())

    if pomo == 0:
        mutation = dedent(
            f"""
            mutation {{
                pomodoro (key: "{PASSKEY}", duration: {dur_sec}, project: "{desc}") {{
                    id,
                    duration
                }}
                }}
            """)

        r = requests.post(API_URL, json={'query': mutation})
        if 'data' in json.loads(r.text):
            print('Pomodoro added to db successfully.')
