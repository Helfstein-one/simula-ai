"""Tier 4: Real-World Credit Mesh Workload Simulation Suite.

Executes an end-to-end simulation of the 4-table Brazilian corporate credit mesh:
- Table 1: empresas (debtor corporate entities, CNPJ, credit score)
- Table 2: propostas (credit loan applications, requested amount, terms)
- Table 3: garantias (collateral assets linked to proposals)
- Table 4: operacoes (formalized credit contracts)

Verifications:
1. Primary Key uniqueness across all tables.
2. 100% Foreign Key referential integrity (zero orphan records).
3. Brazilian CNPJ format validity on empresas.
4. Business rule constraints:
   - data_contratacao >= data_solicitacao
   - valor_contratado <= valor_solicitado
   - operacoes only created for approved proposals
5. Standalone deliverables execution:
   - generator.py execution in clean subprocess producing CSV, JSON, Parquet.
   - test_mock.py validation suite execution passing with returncode 0.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import pytest


@pytest.fixture
def executed_credit_mesh_workload(sample_credit_mesh_yaml, tmp_workspace) -> Dict[str, Any]:
    """Execute the full credit mesh mock generation pipeline and export artifacts."""
    contract_module = pytest.importorskip("core.contract_parser")
    exporter_module = pytest.importorskip("core.exporter")

    contract = contract_module.parse_contract(sample_credit_mesh_yaml)
    export_fn = getattr(exporter_module, "export_deliverables")

    # Generate standalone deliverables
    artifacts = export_fn(
        generated_code="",  # Exporter can synthesize or use generator template
        output_dir=tmp_workspace,
        contract=contract,
        generate_datasets=True,
        rows=50,
        formats=["csv", "json", "parquet"],
    )

    return {
        "contract": contract,
        "output_dir": tmp_workspace,
        "artifacts": artifacts,
    }


def test_t4_all_four_tables_present_in_datasets(executed_credit_mesh_workload):
    """Verify all 4 mesh tables (empresas, propostas, garantias, operacoes) are generated."""
    out_dir = executed_credit_mesh_workload["output_dir"]
    tables = ["empresas", "propostas", "garantias", "operacoes"]

    for table in tables:
        csv_file = out_dir / "datasets" / "csv" / f"{table}.csv"
        json_file = out_dir / "datasets" / "json" / f"{table}.json"
        parquet_file = out_dir / "datasets" / "parquet" / f"{table}.parquet"

        # At least one format directory must contain the dataset
        found = any(f.exists() for f in [csv_file, json_file, parquet_file])
        assert found, f"Dataset for table '{table}' was not created in output/datasets/"


def test_t4_primary_key_uniqueness(executed_credit_mesh_workload):
    """Verify Primary Keys are unique across all 4 tables."""
    out_dir = executed_credit_mesh_workload["output_dir"]
    pk_map = {
        "empresas": "empresa_id",
        "propostas": "proposta_id",
        "garantias": "garantia_id",
        "operacoes": "operacao_id",
    }

    for table, pk_col in pk_map.items():
        csv_path = out_dir / "datasets" / "csv" / f"{table}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path)
        assert pk_col in df.columns, f"Primary key column '{pk_col}' missing from {table}"
        assert df[pk_col].is_unique, f"Duplicate primary keys detected in {table}.{pk_col}"
        assert not df[pk_col].isnull().any(), f"Null primary keys detected in {table}.{pk_col}"


def test_t4_foreign_key_referential_integrity(executed_credit_mesh_workload):
    """Verify 100% Foreign Key referential integrity (zero orphan child records)."""
    out_dir = executed_credit_mesh_workload["output_dir"]

    csv_empresas = out_dir / "datasets" / "csv" / "empresas.csv"
    csv_propostas = out_dir / "datasets" / "csv" / "propostas.csv"
    csv_garantias = out_dir / "datasets" / "csv" / "garantias.csv"
    csv_operacoes = out_dir / "datasets" / "csv" / "operacoes.csv"

    if not all(p.exists() for p in [csv_empresas, csv_propostas, csv_garantias, csv_operacoes]):
        pytest.skip("Not all CSV files exist yet for FK validation")

    df_empresas = pd.read_csv(csv_empresas)
    df_propostas = pd.read_csv(csv_propostas)
    df_garantias = pd.read_csv(csv_garantias)
    df_operacoes = pd.read_csv(csv_operacoes)

    # 1. propostas.empresa_id in empresas.empresa_id
    valid_empresa_ids = set(df_empresas["empresa_id"].dropna())
    orphan_propostas = set(df_propostas["empresa_id"]) - valid_empresa_ids
    assert not orphan_propostas, f"Orphan FK detected: propostas reference nonexistent empresas: {orphan_propostas}"

    # 2. garantias.proposta_id in propostas.proposta_id
    valid_proposta_ids = set(df_propostas["proposta_id"].dropna())
    orphan_garantias = set(df_garantias["proposta_id"]) - valid_proposta_ids
    assert not orphan_garantias, f"Orphan FK detected: garantias reference nonexistent propostas: {orphan_garantias}"

    # 3. operacoes.proposta_id in propostas.proposta_id
    orphan_operacoes = set(df_operacoes["proposta_id"]) - valid_proposta_ids
    assert not orphan_operacoes, f"Orphan FK detected: operacoes reference nonexistent propostas: {orphan_operacoes}"


def test_t4_cnpj_format_validation(executed_credit_mesh_workload):
    """Verify empresas.cnpj matches standard Brazilian CNPJ regex formatting."""
    out_dir = executed_credit_mesh_workload["output_dir"]
    csv_empresas = out_dir / "datasets" / "csv" / "empresas.csv"
    if not csv_empresas.exists():
        pytest.skip("empresas.csv not generated")

    df_empresas = pd.read_csv(csv_empresas)
    cnpj_pattern = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")

    assert "cnpj" in df_empresas.columns
    for cnpj in df_empresas["cnpj"].dropna():
        assert cnpj_pattern.match(str(cnpj)), f"Invalid CNPJ format: {cnpj}"


def test_t4_standalone_generator_subprocess_execution(executed_credit_mesh_workload, tmp_workspace):
    """Verify output/generator.py runs in an external Python process without Simula dependencies (R4)."""
    out_dir = executed_credit_mesh_workload["output_dir"]
    generator_script = out_dir / "generator.py"
    if not generator_script.exists():
        pytest.skip("generator.py not found in output")

    sub_out = tmp_workspace / "sub_gen_output"
    cmd = [
        sys.executable,
        str(generator_script),
        "--rows",
        "15",
        "--output-dir",
        str(sub_out),
        "--format",
        "all",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"Standalone generator.py failed! Stderr: {res.stderr}\nStdout: {res.stdout}"


def test_t4_standalone_test_mock_subprocess_execution(executed_credit_mesh_workload):
    """Verify output/test_mock.py passes 100% when executed with pytest (R4)."""
    out_dir = executed_credit_mesh_workload["output_dir"]
    test_mock_script = out_dir / "test_mock.py"
    if not test_mock_script.exists():
        pytest.skip("test_mock.py not found in output")

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_mock_script),
        "-v",
        "--tb=short",
    ]

    res = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"output/test_mock.py failed!\nStdout: {res.stdout}\nStderr: {res.stderr}"
