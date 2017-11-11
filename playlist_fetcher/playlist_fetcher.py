#! python3

# TODO:
'''
√ Make flake8 know that colorama is needed
√ Fix borked progress bars while downloading
√ Silence errors from pre-count
? Fix progress bars staying on-screen
- More coloured text
- No "Requested formats are incompatible..."
- Make refresh check the database instead of waiting for an error?
- Purging (interactive?)
- Respect starred bool (prevent purging, download first?)
- Statistics of downloaded videos (Time of play, disk size...)
- Enqueue on VLC (by upload order, by playlist folder...)
- Interactive starring? Removal?
- Prettify the code (it's not very Pythonesque...)
'''

import argparse
import copy
import datetime
import logging
import os
import pprint
# import re
import sqlite3
import sys
# import json

import colorama
import youtube_dl
from colorama import Fore, Style
from tqdm import tqdm

colorama.init(autoreset=True)

# Argv Parser
PARSER = argparse.ArgumentParser(fromfile_prefix_chars='@')
PARSER.add_argument('-a', '--add-playlists', metavar='P', type=str, nargs='+',
                    help='add playlists (indexes) for future updates')
PARSER.add_argument('--ignore-archive', action='store_true', help='ignore archive of previously downloaded videos')
PARSER.add_argument('-f', '--refresh-database', action='store_true', help='refreshes index database (updates titles and dates)')
# PARSER.add_argument('-s', '--statistics', action='store_true', help='shows stats for downloaded content')
# PARSER.add_argument('-p', '--purge', action='store_true', help='refreshes database (resets titles and dates)')
PARSER.add_argument('download', metavar='P', type=str, nargs='*', help='playlist URI')
PARSER.add_argument('--skip-index', action='store_true', help='skips indexed playlists for download')
PARSER.add_argument('-d', '--no-downloads', action='store_true', help='do not download videos, only refresh/statistics/...')
PARSER.add_argument('-r', '--reverse', action='store_true', help='reverses the download order for indexed items')

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
# formatter = logging.Formatter("%(levelname)s: %(message)s")

# logging.Formatter()
# handler.setFormatter(formatter)
logger.addHandler(handler)


class SilentLogger(object):
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass

    def critical(self, msg):
        pass


class FluidStream(object):
    """prints to fluid (no-flush) writtable object"""
    def __init__(self, fluid):
        self.fluid = fluid
        self.buffer = ""

    def write(self, string: str):
        self.buffer += string

    def flush(self):
        self.fluid.write(self.buffer.strip())
        self.buffer = ""


def get_tqdm_logger(bar, name="bar"):
    logger = logging.getLogger(f"{__name__}.{name}")
    logger.addHandler(logging.StreamHandler(FluidStream(bar)))
    logger.propagate = False
    return logger


OPTIONS = {
    'format': 'bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best',
    'outtmpl': "%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s",
    'restrictfilenames': True,
    'ignoreerrors': True,
    'no_warnings': True,
    'updatetime': True,
    'quiet': True,
    'logger': logger,
}


def init_files(path):
    """inits the hidden download files"""
    os.makedirs(path, exist_ok=True)

    if not os.path.exists(os.path.join(path, 'playlists.sqlite')):
        conn = sqlite3.connect(os.path.join(path, 'playlists.sqlite'))

        conn.execute("""CREATE TABLE `playlists` (
                        `key`	INTEGER PRIMARY KEY ASC,
                        `id`	TEXT NOT NULL UNIQUE,
                        `url`	TEXT NOT NULL,
                        `title`	TEXT,
                        `date`	INTEGER,
                        `starred`	INTEGER DEFAULT 0
                    );""")
    else:
        conn = sqlite3.connect(os.path.join(path, 'playlists.sqlite'))

    return conn


def get_max_upload_date(entries):
    """return max upload date from entry set"""

    def get_upload_date(entry):
        """turns YYYYMMDD string into datetime"""
        if entry is not None:
            ud = entry["upload_date"]
            # YYYYMMDD, negative quotients because YYYY can be bigger than 2 digits
            return datetime.date(int(ud[:-4]), int(ud[-4:-2]), int(ud[-2:]))
        return None

    return max(map(get_upload_date, filter(lambda x: x is not None, entries)), default=None)


def get_id(playlist_info):
    """returns unique playlist id"""
    return "{}:{}".format(playlist_info['extractor_key'], playlist_info['id'])


def add_playlists(database, args):
    custom_options = copy.copy(OPTIONS)
    custom_options["extract_flat"] = 'in_playlist'

    with youtube_dl.YoutubeDL(custom_options) as ydl:
        for playlist in args.add_playlists:
            info = ydl.extract_info(url=playlist, download=False)

            if info["_type"] != "playlist":
                logger.warning("{} not a playlist, skipping...".format(playlist))
            else:
                try:
                    database.execute("""INSERT INTO `playlists`(`id`,`url`,`title`) VALUES (?,?,?);""",
                                     (get_id(info), info["webpage_url"], info["title"],))
                    print(Fore.GREEN + "Indexed playlist {} ({}).".format(get_id(info), info["title"]))
                except sqlite3.IntegrityError as exc:
                    if exc.args[0] == 'UNIQUE constraint failed: playlists.id':
                        # id must be unique, fail silently
                        pass
                    else:
                        raise exc

                database.commit()


def refresh_database(database, args):
    print(f"{Fore.CYAN}Refreshing database... {Fore.YELLOW}this may take a while.")

    custom_options = copy.copy(OPTIONS)
    custom_options["youtube_include_dash_manifest"] = False

    if 'download_archive' in OPTIONS:
        del custom_options['download_archive']

    bar = tqdm(database.execute("""SELECT `key`, `url` FROM `playlists`""").fetchall())
    custom_options["logger"] = get_tqdm_logger(bar)
    with youtube_dl.YoutubeDL(custom_options) as ydl:
        for playlist in bar:
            # print(entry)
            info = ydl.extract_info(url=playlist[1], download=False)

            database.execute("""UPDATE `playlists` SET `title`=?, `date`=? WHERE `key`=?""", (info["title"], get_max_upload_date(info["entries"]), playlist[0]))
            database.commit()


def download(database, args):
    indexed = list()

    if args.skip_index is not True:
        order = "DESC" if args.reverse else "ASC"
        indexed = database.execute("""SELECT `key`, `url` FROM `playlists` ORDER BY `date` {}""".format(order)).fetchall()

    print(Fore.CYAN + "Updating {} playlists ({} indexed)...".format(len(indexed) + len(args.download), len(indexed)))

    oneoffs = map(lambda e: (None, e), args.download)

    # index_pattern = re.compile(r'^\d+')

    main_bar = tqdm(list(oneoffs) + indexed, unit='pl')
    custom_logger = get_tqdm_logger(main_bar)

    video_bar_options = {
        "total": int(9e9), "position": 2, "unit_scale": True, "unit": "B"
    }

    def main_refresher(parameter_list):
        main_bar.refresh()

    for playlist in main_bar:
        # get total videos count
        silent_options = copy.copy(OPTIONS)
        silent_options["youtube_include_dash_manifest"] = False
        silent_options["logger"] = SilentLogger()

        with youtube_dl.YoutubeDL(silent_options) as ydl:
            info = ydl.extract_info(url=playlist[1], download=False)
            if info is None:
                continue

            info["entries"] = list(filter(lambda x: x is not None, info["entries"]))

            # if n_videos > 0:
            #     with open(str(playlist[0]) + ".log", "w+") as file:
            #     file.write(json.dumps(info))
            for entry in info["entries"]:
                entry["_filename"] = ydl.prepare_filename(entry)

        if len(info["entries"]) <= 0:
            continue

        playlist_bar = tqdm(info["entries"], unit='video')
        playlist_bar.write(Style.DIM + " - " + info["title"])
        # video_bar = None
        # prev_size = 0
        # prev_index = None

        for video in playlist_bar:
            # callback function to report download progress
            video_bar = None
            prev_size = 0

            def report_progress(report):
                """youtube-dl callback function for progress"""
                nonlocal video_bar
                nonlocal prev_size

                if report["status"] == "error" or report["status"] == "finished":
                    video_bar.close()
                    video_bar = None
                elif report["status"] == "downloading":
                    if video_bar is None:
                        prev_size = 0
                        video_bar = tqdm(**video_bar_options)

                    if "total_bytes" in report:
                        video_bar.total = report["total_bytes"]
                    else:
                        video_bar.total = report["total_bytes_estimate"]

                    video_bar.update(report["downloaded_bytes"] - prev_size)
                    prev_size = report["downloaded_bytes"]
                else:
                    pprint.pprint(report)

            custom_options = copy.copy(OPTIONS)
            custom_options["progress_hooks"] = [report_progress, main_refresher]
            custom_options["outtmpl"] = video["_filename"]
            custom_options["logger"] = custom_logger
            custom_options["ignoreerrors"] = False

            with youtube_dl.YoutubeDL(custom_options) as ydl:
                try:
                    # download the video
                    info = ydl.extract_info(url=video["webpage_url"])
                    # with open(str(video["display_id"]) + ".log", "w+") as file:
                    #     file.write(json.dumps(info))
                except (youtube_dl.utils.DownloadError,) as exc:
                    custom_logger.error(exc.msg)
                else:
                    # post-processing: save the newest upload date
                    if playlist[0] is None:
                        continue

                    date = get_max_upload_date([info])
                    if date is None:
                        continue
                    database.execute("""update playlists set date = coalesce(max(?, (select date from playlists where key = ?)), ?) where key = ?""", (date, playlist[0], date, playlist[0]))
                    database.commit()


def main():
    """main program loop"""
    args = PARSER.parse_args()
    path = os.getcwd()
    database = init_files(os.path.join(path, '.playlist_fetcher'))
    archive = os.path.join(path, '.playlist_fetcher', 'archive.txt')

    # print(args.__dict__)

    if args.ignore_archive is False:
        OPTIONS['download_archive'] = archive
        # FLAT_OPTIONS and SHALLOW_OPTIONS don't use archive
    else:
        logger.warning(Fore.YELLOW + "Warning: Ignoring download archive!")

    if args.add_playlists is not None:
        add_playlists(database, args)

    if args.refresh_database is True:
        refresh_database(database, args)

    if args.no_downloads is False:
        download(database, args)


# with youtube_dl.YoutubeDL(ydl_opts) as ydl:
#     ydl.download(['https://www.youtube.com/watch?v=BaW_jenozKc'])


if __name__ == '__main__':
    main()
