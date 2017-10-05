import sys
import traceback

import playlist_fetcher

try:
    playlist_fetcher.main()
except KeyboardInterrupt:
    print("\r\nShutdown requested...exiting", end="")
    sys.stdout.flush()
except Exception:
    traceback.print_exc(file=sys.stdout)
    sys.exit(1)
