from .main import TestClient, WorkerError, deploy
from .version import VERSION

__version__ = VERSION
__all__ = VERSION, 'TestClient', 'deploy', 'WorkerError'
