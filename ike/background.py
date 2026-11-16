"""Background threads: downloads of filter lists, update checks and the like.

A QThread that is destroyed while it still runs makes Qt abort the whole
program. Threads started through start() are remembered; when I.K.E. closes,
let_go() gives them a moment to end, and a thread that is still busy (waiting
for a slow server) is detached and left to the system to end with the
process, instead of being destroyed.
"""

import time

_running = set()


def start(thread):
    """Start a QThread and keep track of it until it has finished."""
    _running.add(thread)
    thread.finished.connect(lambda t=thread: _running.discard(t))
    thread.start()
    return thread


def busy():
    """The tracked threads that are running now."""
    alive = []
    for t in list(_running):
        try:
            if t.isRunning():
                alive.append(t)
            else:
                _running.discard(t)
        except RuntimeError:            # already destroyed by Qt
            _running.discard(t)
    return alive


def let_go(wait_ms=1500):
    """Call once, when the program is closing. Returns the number of threads
    that were still busy and were detached."""
    deadline = time.monotonic() + wait_ms / 1000.0
    left = 0
    for t in busy():
        remaining = max(0, int((deadline - time.monotonic()) * 1000))
        try:
            if t.wait(remaining):
                continue
            # still waiting for the network: neither its owner nor Python may
            # destroy it now
            t.setParent(None)
            from PyQt6 import sip
            sip.transferto(t, None)
            left += 1
        except RuntimeError:
            pass
    _running.clear()
    return left
