#! python3

import sys
import pprint
import os
import sqlite3
import argparse
import youtube_dl as dl


parser = argparse.ArgumentParser()
parser.add_argument()


def init_db(path):
    if os.path.exists('pfdb.db'):
        conn = sqlite3.connect(os.path.join(path, 'pfdb.db'))
        c = conn.cursor()

    else:
        conn = sqlite3.connect(os.path.join(path, 'pfdb.db'))
        c = conn.cursor()

    return c


def main(argv=None):
    print('ready to go')
    print(sys.version)

    args = parser.parse_args()
    init_db(args.path) 

    pprint.pprint(argv)
    print(os.getcwd())

    pass


if __name__ == '__main__':
    main()
