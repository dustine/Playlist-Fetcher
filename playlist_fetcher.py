#! python3

# TODO:
'''
√ Make flake8 know that colorama is needed
√ Fix borked progress bars while downloading
- Fix progress bars staying on-screen
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
import re
import sqlite3
import sys

import colorama
import youtube_dl
from colorama import Back, Fore, Style
from tqdm import tqdm

colorama.init(autoreset=True)

# Argv Parser
PARSER = argparse.ArgumentParser(fromfile_prefix_chars='@')
PARSER.add_argument('-a', '--add-playlists', metavar='P', type=str, nargs='+',
                    help='add playlists for future updates')
PARSER.add_argument('--ignore-archive', action='store_true', help='ignore previously downloaded video archive')
PARSER.add_argument('-r', '--refresh', action='store_true', help='refreshes database (resets titles and dates)')
PARSER.add_argument('download', metavar='P', type=str, nargs='*', help='download playlists (once)')

logger = logging.getLogger(__name__)
logger.propagate = False
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(levelname)s: %(message)s")

logging.Formatter()
handler.setFormatter(formatter)
logger.addHandler(handler)


class FluidStream(object):
    # _stdout_handler = logging.StreamHandler(sys.stdout)

    """prints to fluid (no-flush) if set, stdout otherwise"""
    def __init__(self, fluid):
        self.fluid = fluid
        self.handler = logging.StreamHandler(self)
        # self.handler.setFormatter(formatter)

    def write(self, string: str):
        # print("print")
        if string.strip():
            self.fluid.write(string.strip())
        # sys.stdout.flush()

    def flush(self):
        pass

    def __enter__(self):
        logger.removeHandler(handler)
        logger.addHandler(self.handler)

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.removeHandler(self.handler)
        logger.addHandler(handler)


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
                    print(Fore.CYAN + "Indexed playlist {} ({}).".format(get_id(info), info["title"]))
                except sqlite3.IntegrityError as exc:
                    if exc.args[0] == 'UNIQUE constraint failed: playlists.id':
                        # id must be unique, fail silently
                        pass
                    else:
                        raise exc

                database.commit()


def refresh(database, args):
    print("Refreshing database... this may take a while.")

    custom_options = copy.copy(OPTIONS)
    custom_options["youtube_include_dash_manifest"] = True

    if 'download_archive' in OPTIONS:
        del custom_options['download_archive']

    with youtube_dl.YoutubeDL(custom_options) as ydl:
        pbar = tqdm(database.execute("""SELECT `key`, `url` FROM `playlists`""").fetchall())
        with FluidStream(pbar):
            for entry in pbar:
                # print(entry)
                info = ydl.extract_info(url=entry[1], download=False)

                database.execute("""UPDATE `playlists` SET `title`=?, `date`=? WHERE `key`=?""",
                                 (info["title"], get_max_upload_date(info["entries"]), entry[0]))
                database.commit()


def download(database, args):
    indexed = database.execute("""SELECT `key`, `url` FROM `playlists` ORDER BY `date` ASC""").fetchall()
    print("Updating {} playlists ({} indexed)...".format(len(indexed) + len(args.download), len(indexed)))

    oneoffs = map(lambda elem: (None, elem), args.download)
    custom_options = copy.copy(OPTIONS)
    custom_options["youtube_include_dash_manifest"] = True

    index_pattern = re.compile(r'^\d+')

    pbar = tqdm(list(oneoffs) + indexed)
    with FluidStream(pbar):
        for playlist in pbar:
            # get total videos count
            with youtube_dl.YoutubeDL(custom_options) as ydl:
                info = ydl.extract_info(url=playlist[1], download=False)
                n_videos = len(info["entries"])

            if n_videos <= 0:
                continue

            with tqdm(total=n_videos) as playlist_bar:
                playlist_bar.write(Style.DIM + " - " + info["title"])
                video_bar = None
                prev_size = 0
                prev_index = None

                # callback function to report download progress
                def report_progress(report):
                    """youtube-dl callback function for progress"""
                    nonlocal video_bar
                    nonlocal prev_size
                    nonlocal prev_index

                    if report["status"] == "error":
                        if video_bar is not None:
                            video_bar.close()
                        prev_size = 0
                        playlist_bar.update()
                    elif report["status"] == "finished":
                        if video_bar is not None:
                            video_bar.close()
                        prev_size = 0
                    elif report["status"] == "downloading":
                        if prev_size == 0:
                            video_bar = tqdm(total=int(9e9), position=2, unit_scale=True, unit="B")
                            playlist_bar.refresh()

                            # iterate playlist_bar with filename index
                            match = re.match(index_pattern, os.path.basename(report["filename"]))
                            if match is not None:
                                new_index = int(match.group())
                                if new_index != prev_index:
                                    # don't interate on invalid indexes
                                    if prev_index is not None:
                                        playlist_bar.update()
                                    prev_index = new_index

                        if "total_bytes" in report:
                            video_bar.total = report["total_bytes"]
                        else:
                            video_bar.total = report["total_bytes_estimate"]

                        video_bar.update(report["downloaded_bytes"] - prev_size)
                        prev_size = report["downloaded_bytes"]
                    else:
                        pprint.pprint(report)

                custom_options = copy.copy(OPTIONS)
                custom_options["progress_hooks"] = [report_progress]

                with youtube_dl.YoutubeDL(custom_options) as ydl:
                    # download the playlist
                    info = ydl.extract_info(url=playlist[1])
                    playlist_bar.close()

                    # post-processing: save the newest upload date
                    if playlist[0] is None:
                        continue
                    date = get_max_upload_date(info["entries"])
                    if date is None:
                        continue
                    database.execute("""update playlists set date = coalesce(
                        max(?, (select date from playlists where key = ?)), ?)
                        where key = ?""",
                                     (date, playlist[0], date, playlist[0]))
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

    if args.add_playlists is not None:
        add_playlists(database, args)

    if args.refresh is True:
        refresh(database, args)

    download(database, args)


# with youtube_dl.YoutubeDL(ydl_opts) as ydl:
#     ydl.download(['https://www.youtube.com/watch?v=BaW_jenozKc'])


if __name__ == '__main__':
    main()
