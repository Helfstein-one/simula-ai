"""adapters/inbound - Inbound Driving Adapters (CLI, Web, and REST API)."""

from adapters.inbound.api.router import SimulaAPIRouter
from adapters.inbound.cli.controller import CLIController
from adapters.inbound.web.view_controller import WebViewController

__all__ = [
    "CLIController",
    "WebViewController",
    "SimulaAPIRouter",
]
