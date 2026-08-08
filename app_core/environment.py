"""Configure process environment before application dependencies import."""

import os

import certifi
from dotenv import load_dotenv


load_dotenv()

# Python on macOS may have no default CA bundle, so urllib/pandas HTTPS fetches
# fail certificate verification. Configure the certifi bundle before any route
# module can build an SSL context.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# Py-ART otherwise prints a citation banner on every Windows ProcessPool child
# import.
os.environ.setdefault("PYART_QUIET", "1")
