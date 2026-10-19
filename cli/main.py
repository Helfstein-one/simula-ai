"""cli/main.py - Interactive Typer & Rich CLI for Simula-AI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from core.llm_client import DEFAULT_PRIMARY_MODEL
from infrastructure.container import SimulaContainer

app = typer.Typer(
    name="simula",
    help="Simula-AI: Autonomous Relational Data Mocking Framework for Data Mesh.",
    add_completion=False,
)
console = Console()


@app.command("run")
def run_command(
    contract: str = typer.Argument(..., help="Path to Data Contract YAML file"),
    output_dir: str = typer.Option("output", "--output-dir", "-o", help="Target output directory"),
    iterations: int = typer.Option(3, "--iterations", "-i", help="Maximum CoALA reflection iterations"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Run in deterministic offline mock mode"),
    rows: int = typer.Option(50, "--rows", "-r", help="Number of rows to generate per table"),
    model: Optional[str] = typer.Option(None, "--model", help="OpenRouter model (defaults to Hermes 3)"),
) -> None:
    """Execute the CoALA cognitive loop to synthesize generators, test suites, and mock datasets."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel.fit(
            f"[bold cyan]Simula-AI CoALA Loop[/bold cyan]\n"
            f"[dim]Contract:[/dim] {contract}\n"
            f"[dim]Output Directory:[/dim] {out_path}\n"
            f"[dim]Model:[/dim] {model or os.environ.get('OPENROUTER_MODEL', DEFAULT_PRIMARY_MODEL)}\n"
            f"[dim]Mode:[/dim] {'Mock (Offline)' if mock else 'OpenRouter Active'}",
            border_style="cyan",
        )
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Ingesting data contract...", total=None)
        contract_parser = SimulaContainer.get_contract_parser()
        parsed_contract = contract_parser.parse(contract)

        progress.update(task, description="[cyan]Initializing LLM provider & sandbox...")
        simulate_uc = SimulaContainer.get_simulate_mesh_use_case(
            model=model,
            mock_mode=mock or (os.environ.get("SIMULA_MOCK_LLM", "").lower() in ("true", "1", "yes")),
            sandbox_timeout=30,
            parser=contract_parser,
        )

        progress.update(task, description="[green]Executing CoALA LangGraph cognitive loop...")
        final_event = None
        for ev in simulate_uc.execute_stream(
            contract_source=parsed_contract,
            max_iterations=iterations,
        ):
            final_event = ev
            if getattr(ev, "message", None):
                progress.update(task, description=f"[green]{ev.message}")

        final_state = final_event.state if final_event else {}

    status = final_state.get("status", "UNKNOWN")
    if status == "SUCCESS":
        console.print(f"[bold green]✓ CoALA Loop Succeeded in {final_state.get('iterations', 1)} iterations![/bold green]")
        generated_code = final_state.get("working_memory", {}).get("generated_code", "")

        # Export deliverables
        export_uc = SimulaContainer.get_export_deliverables_use_case()
        artifacts = export_uc.execute(
            generated_code=generated_code,
            output_dir=out_path,
            contract=parsed_contract,
            generate_datasets=True,
            rows=rows,
            formats=["csv", "json", "parquet"],
        )
        # Export Mermaid ER diagram
        diagram_file = out_path / "mesh_er_diagram.mmd"
        diagram_uc = SimulaContainer.get_generate_diagram_use_case()
        diagram_uc.execute(contract_source=parsed_contract, output_path=diagram_file)

        console.print(f"[bold blue]✓ Artifacts exported successfully:[/bold blue]")
        console.print(f"  • Standalone Generator: {artifacts.get('generator')}")
        console.print(f"  • Validation Test Suite: {artifacts.get('test_mock')}")
        console.print(f"  • Mermaid ER Diagram: {diagram_file}")
        console.print(f"  • Datasets: {out_path / 'datasets'}")
    else:
        console.print(f"[bold red]✗ Loop ended with status: {status}[/bold red]")
        last_error = final_state.get("working_memory", {}).get("pytest_output", "")
        if last_error:
            console.print(Panel(last_error, title="Last Pytest Traceback", border_style="red"))
        raise typer.Exit(code=1)


@app.command("inspect")
def inspect_command(
    contract: str = typer.Argument(..., help="Path to Data Contract YAML file to inspect"),
) -> None:
    """Inspect and display data mesh tables, schema DAG topological order, and constraints."""
    inspect_uc = SimulaContainer.get_inspect_contract_use_case()
    result = inspect_uc.execute(contract)

    console.print(
        Panel.fit(
            f"[bold magenta]Data Contract: {result.name}[/bold magenta] (v{result.version})\n"
            f"[dim]{result.description or 'No description provided'}[/dim]",
            border_style="magenta",
        )
    )

    # Topological order
    console.print(f"[bold yellow]Topological Ingestion DAG Order:[/bold yellow] {' ➔ '.join(result.topological_order)}")

    # Tables summary table
    table = Table(title="Mesh Tables & Schemas", border_style="dim")
    table.add_column("Table Name", style="bold cyan")
    table.add_column("Columns", justify="right")
    table.add_column("Primary Key", style="green")
    table.add_column("Foreign Keys", style="yellow")

    for tbl in result.tables:
        table.add_row(
            tbl.name,
            str(tbl.column_count),
            tbl.primary_key or "N/A",
            ", ".join(tbl.foreign_keys) or "None",
        )

    console.print(table)


@app.command("diagram")
def diagram_command(
    contract: str = typer.Argument(..., help="Path to Data Contract YAML file"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Target file for .mmd diagram"),
) -> None:
    """Generate and display the hybrid Mermaid ER diagram from data contract."""
    diagram_uc = SimulaContainer.get_generate_diagram_use_case()
    mmd = diagram_uc.execute(contract_source=contract, output_path=output)

    if output:
        console.print(f"[bold green]✓ Mermaid ER diagram saved to {output}[/bold green]")
    else:
        console.print(Panel(mmd, title="Mermaid ER Diagram", border_style="cyan"))


@app.command("export")
def export_command(
    contract: str = typer.Argument(..., help="Path to Data Contract YAML file"),
    output_dir: str = typer.Option("output", "--output-dir", "-o", help="Target output directory"),
    rows: int = typer.Option(50, "--rows", "-r", help="Number of rows to generate"),
    format: str = typer.Option("all", "--format", "-f", help="Output formats: csv, json, parquet, or all"),
) -> None:
    """Export standalone generator, test suite, and datasets for the given contract."""
    contract_parser = SimulaContainer.get_contract_parser()
    parsed_contract = contract_parser.parse(contract)
    out_path = Path(output_dir)

    formats = ["all"] if format == "all" else [f.strip() for f in format.split(",")]
    export_uc = SimulaContainer.get_export_deliverables_use_case()
    artifacts = export_uc.execute(
        output_dir=out_path,
        contract=parsed_contract,
        generate_datasets=True,
        rows=rows,
        formats=formats,
    )
    diagram_uc = SimulaContainer.get_generate_diagram_use_case()
    diagram_uc.execute(contract_source=parsed_contract, output_path=out_path / "mesh_er_diagram.mmd")
    console.print(f"[bold green]✓ Deliverables exported to {out_path}[/bold green]")


@app.command("test")
def test_command(
    test_path: str = typer.Argument("output/test_mock.py", help="Path to test file to run with Pytest"),
) -> None:
    """Execute Pytest on the generated mock validation test suite."""
    if not Path(test_path).exists():
        console.print(f"[bold red]Test file '{test_path}' does not exist![/bold red]")
        raise typer.Exit(code=1)

    cmd = [sys.executable, "-m", "pytest", test_path, "-v"]
    res = subprocess.run(cmd)
    raise typer.Exit(code=res.returncode)


@app.command("ui")
def ui_command(
    port: int = typer.Option(8501, "--port", "-p", help="Port to bind Streamlit server"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host interface to bind"),
) -> None:
    """Launch the interactive Simula-AI Streamlit Web UI dashboard."""
    app_script = Path(__file__).resolve().parent.parent / "ui" / "app.py"
    if not app_script.exists():
        console.print(f"[bold red]Web UI script not found at {app_script}![/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Launching Simula-AI Streamlit Web UI on http://{host}:{port}...[/bold green]")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_script),
        "--server.port",
        str(port),
        "--server.address",
        str(host),
    ]
    subprocess.run(cmd)


if __name__ == "__main__":
    app()
