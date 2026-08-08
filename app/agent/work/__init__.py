"""后端工作任务协调。"""

from .coordinator import DuplicateWorkCommand, WorkCoordinator, WorkJobNotFound
from .service import WorkCoordinatorRegistry, validate_stable_user_id
from .completion import WorkCompletionBroker, WorkCompletionReporter, WorkNotification

__all__ = [
    "DuplicateWorkCommand",
    "WorkCoordinator",
    "WorkCoordinatorRegistry",
    "WorkCompletionBroker",
    "WorkCompletionReporter",
    "WorkNotification",
    "WorkJobNotFound",
    "validate_stable_user_id",
]
