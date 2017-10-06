import sys
import traceback

import playlist_fetcher


def main():
    try:
        playlist_fetcher.main()
    except KeyboardInterrupt:
        print("\rShutdown requested... exiting")
    except Exception:
        traceback.print_exc(file=sys.stdout)
        return 1
