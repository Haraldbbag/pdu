"""Test setup."""

import sys

if sys.platform == "win32":
    # On Windows asyncio needs a local socket pair, which pytest_socket blocks.
    # Tests use mocked HTTP only, so socket blocking is not needed there.
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None
    pytest_socket.socket_allow_hosts = lambda *args, **kwargs: None
