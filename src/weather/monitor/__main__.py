from .monitor import check, startup, test_email
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode == "startup":
    startup()
elif mode == "check":
    check()
elif mode == "test":
    test_email()
else:
    from .monitor import __doc__
    print(__doc__)
    sys.exit(1)
