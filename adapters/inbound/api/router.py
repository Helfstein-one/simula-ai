"""adapters/inbound/api/router.py - Inbound REST API driving adapter router."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from infrastructure.container import SimulaContainer


class SimulaAPIRouter:
    """Inbound Driving Adapter providing REST endpoints for Simula-AI services."""

    def __init__(self, container: Optional[SimulaContainer] = None) -> None:
        self.container = container or SimulaContainer()

    def inspect_contract(self, yaml_content: str) -> Dict[str, Any]:
        """POST /api/v1/contract/inspect - Inspects schema, PK/FKs, and topological DAG."""
        use_case = self.container.get_inspect_contract_use_case()
        res = use_case.execute(yaml_content)
        return {
            "name": res.name,
            "version": res.version,
            "description": res.description,
            "topological_order": res.topological_order,
            "tables": [
                {
                    "name": t.name,
                    "columns": t.column_count,
                    "primary_key": t.primary_key,
                    "foreign_keys": t.foreign_keys,
                }
                for t in res.tables
            ],
        }

    def generate_diagram(self, yaml_content: str) -> Dict[str, str]:
        """POST /api/v1/contract/diagram - Generates Mermaid ER diagram syntax."""
        use_case = self.container.get_generate_diagram_use_case()
        diagram = use_case.execute(yaml_content)
        return {"mermaid": diagram}

    def run_simulation(
        self,
        yaml_content: str,
        max_iterations: int = 3,
        mock_mode: bool = False,
        model: Optional[str] = None,
        rows: int = 50,
        sandbox_type: str = "auto",
    ) -> Dict[str, Any]:
        """POST /api/v1/simulation/run - Executes CoALA loop and delivers synthetic mock assets."""
        simulate_uc = self.container.get_simulate_mesh_use_case(
            model=model,
            mock_mode=mock_mode,
            sandbox_type=sandbox_type,
        )
        final_state = simulate_uc.execute(yaml_content, max_iterations=max_iterations)
        status = final_state.get("status", "UNKNOWN")

        deliverables = None
        if status == "SUCCESS":
            contract = self.container.get_contract_parser().parse(yaml_content)
            export_uc = self.container.get_export_deliverables_use_case()
            deliverables = export_uc.execute(
                generated_code=final_state.get("working_memory", {}).get("generated_code", ""),
                output_dir="output",
                contract=contract,
                generate_datasets=True,
                rows=rows,
            )

        return {
            "status": status,
            "iterations": final_state.get("iterations", 0),
            "deliverables": deliverables,
            "episodic_failures": len(final_state.get("episodic_memory", [])),
        }

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """GET /api/v1/simulation/sessions/{session_id} - Retrieves timeline of checkpoints."""
        repo = self.container.get_state_repository()
        return repo.get_session_history(session_id)

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """GET /api/v1/simulation/sessions - Lists recorded simulation sessions."""
        repo = self.container.get_state_repository()
        return repo.list_sessions(limit=limit)
