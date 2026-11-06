"""goeval: evaluate driver gaze-to-object mapping with protocols where the looked-at object is known."""
__version__ = "0.1.3"

from .config import DEFAULTS, params  # noqa: F401
from .io import Recording, SchemaError, check_recording, read_recording  # noqa: F401
from .table import build, looking  # noqa: F401
from .report import evaluate  # noqa: F401
