import argparse
import sys
import traceback
from time import sleep

# Argv Parser
PARSER = argparse.ArgumentParser(fromfile_prefix_chars='@')
PARSER.add_argument(
    '-a',
    '--add-playlists',
    metavar='P',
    type=str,
    nargs='+',
    help='add playlists (indexes) for future updates')
PARSER.add_argument(
    '--ignore-archive',
    action='store_true',
    help='ignore archive of previously downloaded videos')
PARSER.add_argument(
    '-f',
    '--refresh-database',
    action='store_true',
    help='refreshes index database (updates titles and dates)')
# PARSER.add_argument('-s', '--statistics', action='store_true', help='shows stats for downloaded content')
# PARSER.add_argument('-p', '--purge', action='store_true', help='refreshes database (resets titles and dates)')
PARSER.add_argument(
    'download', metavar='P', type=str, nargs='*', help='playlist URI')
PARSER.add_argument(
    '--skip-index',
    action='store_true',
    help='skips indexed playlists for download')
PARSER.add_argument(
    '-d',
    '--no-downloads',
    action='store_true',
    help='do not download videos, only refresh/statistics/...')
PARSER.add_argument(
    '-r',
    '--reverse',
    action='store_true',
    help='reverses the download order for indexed items')
PARSER.add_argument(
    '-v',
    '--verbose',
    action='count',
    default=0,
    help='log verbosity (-vv for script too)')


def main():
    args = PARSER.parse_args()
    try:
        import playlist_fetcher
        playlist_fetcher.main(**vars(args))
    except KeyboardInterrupt:
        playlist_fetcher.abort()
        sleep(0.1)
    except Exception:
        traceback.print_exc(file=sys.stdout)
        return 1
