#! python3

import argparse
import copy
import datetime
import os
import pprint
import sqlite3
import sys
import logging
import string

import colorama
import youtube_dl
from tqdm import tqdm

# Argv Parser
PARSER = argparse.ArgumentParser(fromfile_prefix_chars='@')
PARSER.add_argument('-a', '--add-playlists', metavar='P', type=str, nargs='+',
                    help='add playlists for future updates')
PARSER.add_argument('--ignore-archive', action='store_true', help='ignore previously downloaded video archive')
PARSER.add_argument('-r', '--refresh', action='store_true', help='refreshes database (resets titles and dates)')
PARSER.add_argument('download', metavar='P', type=str, nargs='*', help='download playlists (once)')

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(levelname)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


class FluidStream(object):
    # _stdout_handler = logging.StreamHandler(sys.stdout)

    """prints to fluid (no-flush) if set, stdout otherwise"""
    def __init__(self, fluid):
        self.fluid = fluid
        self.handler = logging.StreamHandler(self)
        self.handler.setFormatter(formatter)

    def write(self, str):
        self.fluid.write(str, end="\n")
        sys.stdout.flush()

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
    # 'no_warnings': True,
    'updatetime': True,
    'quiet': True,
    # 'postprocessors': [{
    #     'key': 'FFmpegExtractAudio',
    #     'preferredcodec': 'mp3',
    #     'preferredquality': '192',
    # }],
    'logger': logger,
    # 'progress_hooks': [my_hook],
}


def init_files(path):
    """inits the hidden download files"""
    os.makedirs(path, exist_ok=True)

    # conf = os.path.join(path, 'youtube-dl.conf')
    # if not os.path.exists(conf):
    #     with open(conf, 'w') as file:
    #         file.write('--restrict-filenames\n'
    #                     '--prefer-free-formats\n'
    #                     '-o "%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s"\n'
    #                     '-f bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best')

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
        return datetime.date.fromtimestamp(0)

    return max(map(get_upload_date, entries), default=datetime.date.fromtimestamp(0))


def get_id(playlist_info):
    """returns unique playlist id"""
    return "{}:{}".format(playlist_info['extractor_key'], playlist_info['id'])


def main():
    """main program loop"""
    args = PARSER.parse_args()
    path = os.getcwd()
    database = init_files(os.path.join(path, '.playlist_fetcher'))
    archive = os.path.join(path, '.playlist_fetcher', 'archive.txt')

    print(args.__dict__)

    # ignore-archive
    if args.ignore_archive is False:
        print(archive)
        OPTIONS['download_archive'] = archive

    flat_options = copy.copy(OPTIONS)
    flat_options["extract_flat"] = "in_playlist"

    # add-playlists
    if args.add_playlists is not None:
        with youtube_dl.YoutubeDL(flat_options) as ydl:
            for playlist in args.add_playlists:
                info = ydl.extract_info(url=playlist, download=False)

                if info["_type"] != "playlist":
                    logger.warning("{} not a playlist, skipping...".format(playlist))
                else:
                    try:
                        database.execute("""INSERT INTO `playlists`(`id`,`url`,`title`) VALUES (?,?,?);""",
                                         (get_id(info), info["webpage_url"], info["title"],))
                        print("Indexed playlist {} ({}).".format(get_id(info), info["title"]))
                    except sqlite3.IntegrityError as exc:
                        if exc.args[0] == 'UNIQUE constraint failed: playlists.id':
                            # id must be unique, fail silently
                            pass
                        else:
                            raise exc

            database.commit()

    # refresh
    if args.refresh is True:
        print("Refreshing database... this may take a while.")

        custom_options = copy.copy(OPTIONS)
        del custom_options["download_archive"]
        custom_options["youtube_include_dash_manifest"] = False

        with youtube_dl.YoutubeDL(custom_options) as ydl:
            pbar = tqdm(database.execute("""SELECT `id`, `url` FROM `playlists`""").fetchall())
            with FluidStream(pbar):
                for entry in pbar:
                    # print(entry)
                    info = ydl.extract_info(url=entry[1], download=False)

                    database.execute("""UPDATE `playlists` SET `title`=?, `date`=? WHERE `id`=?""",
                                     (info["title"], get_max_upload_date(info["entries"]), entry[0]))
                    database.commit()

    # download
    indexed = database.execute("""SELECT `id`, `url` FROM `playlists` ORDER BY `date` ASC""").fetchall()
    print("Updating {} playlists ({} indexed)...".format(len(indexed) + len(args.download), len(indexed)))

    oneoffs = map(lambda elem: (None, elem), args.download)
    pbar = tqdm(list(oneoffs) + indexed)
    with FluidStream(pbar):
        for playlist in pbar:
            with youtube_dl.YoutubeDL(flat_options) as ydl:
                info = ydl.extract_info(url=playlist[1], download=False)
                n_videos = len(info["entries"])

            with tqdm(total=n_videos, position=1) as playlist_bar:
                playlist_bar.write(info["title"])
                video_bar = None
                prev_size = 0

                def report_progress(report):
                    """youtube-dl callback function for progress"""
                    nonlocal video_bar
                    nonlocal prev_size

                    if report["status"] == "error":
                        if video_bar is not None:
                            video_bar.close()
                        prev_size = 0
                    elif report["status"] == "finished":
                        if video_bar is not None:
                            video_bar.close()
                            
                        prev_size = 0
                        playlist_bar.update()
                    elif report["status"] == "downloading":
                        if prev_size == 0:
                            video_bar = tqdm(total=int(9e9), position=2, unit_scale=True, unit="B")
                        if "total_bytes" in report:
                            video_bar.total = report["total_bytes"]
                        else:
                            video_bar.total = report["total_bytes_estimate"]

                        video_bar.update(report["downloaded_bytes"] - prev_size)
                        prev_size = report["downloaded_bytes"]
                    else:
                        logger.warning(pprint.pprint(report))

                progress_options = copy.copy(OPTIONS)
                progress_options["progress_hooks"] = [report_progress]
                progress_options["logger"] = logger

                with youtube_dl.YoutubeDL(progress_options) as ydl:
                    info = ydl.extract_info(url=playlist[1])
                    if len(info["entries"]) > 0:
                        with open("output_{}.txt".format(info["id"]), "w+") as file:
                            pprint.pprint(info, stream=file)

# with youtube_dl.YoutubeDL(ydl_opts) as ydl:
#     ydl.download(['https://www.youtube.com/watch?v=BaW_jenozKc'])


if __name__ == '__main__':
    main()
