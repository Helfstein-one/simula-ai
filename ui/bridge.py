"""ui/bridge.py - State bridge between Simula-AI CoALA LangGraph engine and Streamlit UI."""

from __future__ import annotations

from typing import Any, Callable, Dict, Generator, List, Optional

from core.contract_parser import DataContract, parse_contract
from core.diagram import generate_mermaid_er
from core.exporter import export_deliverables
from core.graph import run_simula_loop
from core.llm_client import OpenRouterClient
from core.sandbox import PytestSandbox


class StateBridge:
    """Manages reactive execution and event streaming for Streamlit session state."""

    def __init__(self, contract_yaml: str = "") -> None:
        self.contract_yaml = contract_yaml
        self.parsed_contract: Optional[DataContract] = None
        self.events: List[Dict[str, Any]] = []
        self.current_state: Dict[str, Any] = {}
        if contract_yaml:
            try:
                self.parsed_contract = parse_contract(contract_yaml)
            except Exception:
                pass

    def update_state(self, new_state: Dict[str, Any]) -> None:
        """Updates internal state snapshot."""
        self.current_state.update(new_state)

    def stream_events(
        self,
        mock_mode: bool = False,
        max_iterations: int = 3,
        model: Optional[str] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        """Runs the CoALA cognitive loop and yields progress event dictionaries."""
        client = OpenRouterClient(mock_mode=mock_mode, model=model)
        sandbox = PytestSandbox(timeout_seconds=30)

        for event in run_simula_loop(
            contract_path=self.contract_yaml,
            client=client,
            sandbox=sandbox,
            max_iterations=max_iterations,
            stream_events=True,
        ):
            self.events.append(event)
            self.update_state(event)
            if on_event:
                on_event(event)
            yield event

        return self.current_state

    def get_mermaid_diagram(self) -> str:
        """Returns Mermaid erDiagram representation of the current contract."""
        if not self.parsed_contract and self.contract_yaml:
            try:
                self.parsed_contract = parse_contract(self.contract_yaml)
            except Exception:
                return "erDiagram\n    ERROR {\n        string message\n    }"
        if self.parsed_contract:
            return generate_mermaid_er(self.parsed_contract)
        return "erDiagram\n"
