"""Print the screenshots of a test run (IKE_TEST_SHOTS) as text, one line each:
"ICE-SHOT <name> <base64 JPEG>", so they can be read from the job's log too.

    python tests/shots_to_log.py <folder>
"""

import base64
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage

for f in sorted(Path(sys.argv[1]).glob("*.png")):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    QImage(str(f)).save(buf, "JPG", 75)
    print("ICE-SHOT", f.name.replace(" ", "_"), base64.b64encode(bytes(data)).decode())
