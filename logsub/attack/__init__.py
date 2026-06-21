"""S2 — Attack generator (SPECIFICATION.md §4).

Controlled-access component: effectively an attack tool. See SPECIFICATION.md §10.
"""

from logsub.attack.base import Payload
from logsub.attack.ga import GAGenerator
from logsub.attack.gcg import GCGGenerator
from logsub.attack.handwritten import HandwrittenGenerator
from logsub.attack.pair import PairGenerator

__all__ = [
    "Payload", "HandwrittenGenerator", "GAGenerator", "PairGenerator", "GCGGenerator",
]
