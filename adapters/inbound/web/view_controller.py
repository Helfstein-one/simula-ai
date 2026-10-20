"""adapters/inbound/web/view_controller.py - Driving Web adapter controller for UI interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from infrastructure.container import SimulaContainer


class WebViewController:
    """Inbound Driving Adapter bridging Web UI frameworks (Streamlit) to Hexagonal Use Cases."""

    def __init__(self, container: Optional[SimulaContainer] = None) -> None:
        self.container = container or SimulaContainer()

    def inspect_contract(self, yaml_content: str) -> Any:
        """Validates contract text and returns structured inspection summary."""
        use_case = self.container.get_inspect_contract_use_case()
        return use_case.execute(yaml_content)

    def generate_diagram(self, yaml_content: str) -> str:
        """Renders Mermaid ER diagram string from contract YAML."""
        use_case = self.container.get_generate_diagram_use_case()
        return use_case.execute(yaml_content)

    def run_simulation(
        self,
        yaml_content: str,
        model: Optional[str] = None,
        mock_mode: bool = False,
        max_iterations: int = 3,
        row_count: int = 25,
        output_dir: str | Path = "output",
        sandbox_type: str = "auto",
    ) -> Dict[str, Any]:
        """Runs the CoALA cognitive loop and exports deliverables upon success."""
        simulate_uc = self.container.get_simulate_mesh_use_case(
            model=model,
            mock_mode=mock_mode,
            sandbox_type=sandbox_type,
        )
        final_state = simulate_uc.execute(
            contract_source=yaml_content,
            max_iterations=max_iterations,
        )

        artifacts = None
        if final_state.get("status") == "SUCCESS":
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            contract = self.container.get_contract_parser().parse(yaml_content)
            export_uc = self.container.get_export_deliverables_use_case()
            artifacts = export_uc.execute(
                generated_code=final_state.get("working_memory", {}).get("generated_code", ""),
                output_dir=out_path,
                contract=contract,
                generate_datasets=True,
                rows=row_count,
                formats=["csv", "json", "parquet"],
            )

        return {
            "final_state": final_state,
            "artifacts": artifacts,
        }
