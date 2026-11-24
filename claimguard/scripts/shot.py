"""Decode a CDP Page.captureScreenshot JSON response into a PNG: python scripts/shot.py <json> <png>."""

import base64
import json
import re
import sys

raw = open(sys.argv[1], encoding="utf-8").read()
try:
    data = json.loads(raw)["data"]
except (json.JSONDecodeError, KeyError):
    data = re.search(r'"data"\s*:\s*"([^"]+)"', raw).group(1)
open(sys.argv[2], "wb").write(base64.b64decode(data))
print(sys.argv[2])
