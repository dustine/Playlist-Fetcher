#! python3

import argparse
import copy
import datetime
import os
import pprint
import sqlite3
import sys

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


class Logger(object):
    """quick and dirty logger for yt-dl"""
    def debug(self, msg):
        """prints debug message"""
        pass

    def warning(self, msg):
        """prints warning message on stdout"""
        print("WARNING: " + msg)

    def error(self, msg):
        """prints error message on stderr"""
        print("ERROR: " + msg, file=sys.stderr)

LOGGER = Logger()


def my_hook(data):
    """hook function for yt-dl updates"""
    if data['status'] == 'finished':
        print('Done downloading, now converting ...')


OPTIONS = {
    'format': 'bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best',
    'outtmpl': "%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s",
    'prefer-free-formats': True,
    'restrictfilenames': True,
    'ignoreerrors': True,
    'updatetime': True,
    # 'postprocessors': [{
    #     'key': 'FFmpegExtractAudio',
    #     'preferredcodec': 'mp3',
    #     'preferredquality': '192',
    # }],
    'logger': Logger(),
    'progress_hooks': [my_hook],
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
                        `key`	INTEGER,
                        `id`	TEXT NOT NULL UNIQUE,
                        `url`	TEXT NOT NULL,
                        `title`	TEXT,
                        `date`	INTEGER,
                        `starred`	INTEGER DEFAULT 0,
                        PRIMARY KEY(`key`)
                    );""")
    else:
        conn = sqlite3.connect(os.path.join(path, 'playlists.sqlite'))

    return conn


def get_max_upload_date(entries):
    """return max upload date from entry set"""
    def str_to_date(string):
        """turns YYYYMMDD string into datetime"""
        # YYYYMMDD, negative quotients because YYYY can be bigger than 2 digits
        return datetime.date(int(string[:-4]), int(string[-4:-2]), int(string[-2:]))

    dates_str = map(lambda entry: entry["upload_date"], entries)
    dates = map(str_to_date, dates_str)

    return max(dates)


def get_id(playlist_info):
    """returns unique playlist id"""
    return "{}:{}".format(playlist_info['extractor_key'], playlist_info['id'])


def main():
    """main program loop"""
    args = PARSER.parse_args()
    path = os.getcwd()
    database = init_files(os.path.join(path, '.playlist_fetcher'))
    archive = os.path.join(path, '.playlist_fetcher', 'archive.txt')

    # ignore-archive
    if args.ignore_archive is None:
        OPTIONS['download_archive'] = archive

    flat_options = copy.deepcopy(OPTIONS)
    flat_options["extract_flat"] = "in_playlist"

    # add-playlists
    if args.add_playlists is not None:
        with youtube_dl.YoutubeDL(flat_options) as ydl:
            for playlist in args.add_playlists:
                info = ydl.extract_info(url=playlist, download=False)

                if info["_type"] != "playlist":
                    LOGGER.warning("{} not a playlist, skipping...".format(playlist))
                else:
                    try:
                        database.execute("""INSERT INTO `playlists`(`id`,`url`,`title`)
                                        VALUES (?,?,?);""",
                                         (get_id(info), info["webpage_url"], info["title"],
                                         ))
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
        with youtube_dl.YoutubeDL(OPTIONS) as ydl:
            for entry in tqdm(database.execute("""SELECT `id`, `url` FROM `playlists`""").fetchall()):
                # print(entry)
                info = ydl.extract_info(url=entry[1], download=False)

                database.execute("""UPDATE `playlists` SET `title`=?, `date`=? WHERE `id`=?""",
                    (info["title"], get_max_upload_date(info["entries"]), entry[0])
                )
                database.commit()
                # print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = '\r', flush=True)

    # download
    indexed = database.execute("""SELECT `id`, `url` FROM `playlists` ORDER BY `date` DESC""").fetchall()
    print("Updating {} playlists ({} indexed)...".format(len(indexed) + len(args.download), len(indexed)))

    flat2_options = copy.deepcopy(OPTIONS)
    flat2_options["extract_flat"] = True

    oneoffs = map(lambda elem: ("", elem), args.download)
    with youtube_dl.YoutubeDL(flat2_options) as ydl:
        for playlist in tqdm(list(oneoffs) + indexed):
            info = ydl.extract_info(url=playlist[1], download=False)

            
            for video in tqdm(info["entries"]):
                result = ydl.extract_info(url=video["url"])



# with youtube_dl.YoutubeDL(ydl_opts) as ydl:
#     ydl.download(['https://www.youtube.com/watch?v=BaW_jenozKc'])

if __name__ == '__main__':
    main()
