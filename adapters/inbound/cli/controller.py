"""adapters/inbound/cli/controller.py - Driving CLI controller orchestrating use cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from domain.events import SimulaEvent
from infrastructure.container import SimulaContainer


class CLIController:
    """Inbound Driving Adapter controller mapping CLI requests to Application Use Cases."""

    def __init__(self, container: Optional[SimulaContainer] = None) -> None:
        self.container = container or SimulaContainer()

    def inspect_contract(self, contract_path: str | Path) -> Any:
        """Executes InspectContractUseCase for the target data contract."""
        use_case = self.container.get_inspect_contract_use_case()
        return use_case.execute(contract_path)

    def generate_diagram(
        self,
        contract_path: str | Path,
        output_path: Optional[str | Path] = None,
        include_annotations: bool = True,
    ) -> str:
        """Executes GenerateDiagramUseCase returning or persisting Mermaid ER syntax."""
        use_case = self.container.get_generate_diagram_use_case()
        return use_case.execute(
            contract_source=contract_path,
            output_path=output_path,
            include_annotations=include_annotations,
        )

    def run_simulation_stream(
        self,
        contract_path: str | Path,
        max_iterations: int = 3,
        mock_mode: bool = False,
        model: Optional[str] = None,
        sandbox_type: str = "auto",
        on_step: Optional[Callable[[SimulaEvent], None]] = None,
    ) -> Iterator[SimulaEvent]:
        """Executes SimulateMeshUseCase yielding lifecycle events."""
        use_case = self.container.get_simulate_mesh_use_case(
            model=model,
            mock_mode=mock_mode,
            sandbox_type=sandbox_type,
        )
        return use_case.execute_stream(
            contract_source=contract_path,
            max_iterations=max_iterations,
            on_step_callback=on_step,
        )

    def export_artifacts(
        self,
        contract_path: str | Path,
        generated_code: str = "",
        output_dir: str | Path = "output",
        rows: int = 50,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Executes ExportDeliverablesUseCase and exports Mermaid ER diagram."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        contract_parser = self.container.get_contract_parser()
        contract = contract_parser.parse(contract_path)

        export_uc = self.container.get_export_deliverables_use_case()
        artifacts = export_uc.execute(
            generated_code=generated_code,
            output_dir=out_path,
            contract=contract,
            generate_datasets=True,
            rows=rows,
            formats=formats or ["csv", "json", "parquet"],
        )

        diagram_file = out_path / "mesh_er_diagram.mmd"
        diagram_uc = self.container.get_generate_diagram_use_case()
        diagram_uc.execute(contract_source=contract, output_path=diagram_file)

        artifacts["diagram"] = str(diagram_file)
        return artifacts
