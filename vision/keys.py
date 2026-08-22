"""Read keys from the OpenCV window or the terminal. Either q/ESC quits."""

from __future__ import annotations

import select
import sys
import termios
import tty
from collections.abc import Iterator
from contextlib import contextmanager

import cv2


@contextmanager
def raw_stdin() -> Iterator[None]:
    """Make one keystroke available without pressing Enter. No-op if not a TTY."""
    if not sys.stdin.isatty():
        yield
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def poll(*, use_cv2: bool = True) -> int:
    """Return a key code, or -1 if nothing pressed. HUD window or terminal."""
    if use_cv2:
        key = cv2.waitKey(1) & 0xFF
        if key != 255:
            return key
    if not sys.stdin.isatty():
        return -1
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return -1
    ch = sys.stdin.read(1)
    if not ch:
        return -1
    if ch == "\x1b":
        return 27
    return ord(ch)


def is_quit(key: int) -> bool:
    return key in (ord("q"), ord("Q"), 27)
