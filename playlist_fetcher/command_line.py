import sys
import traceback
from time import sleep


def main():
    try:
        import playlist_fetcher
        playlist_fetcher.main()
    except KeyboardInterrupt:
        playlist_fetcher.abort()
        sleep(0.1)
    except Exception:
        traceback.print_exc(file=sys.stdout)
        return 1
