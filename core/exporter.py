"""core/exporter.py - Standalone deliverables and multi-format data exporter.

Exports:
1. output/generator.py: Standalone Python script executable without framework dependencies.
2. output/test_mock.py: Standalone Pytest test suite asserting schema & business integrity.
3. output/datasets/{csv,json,parquet}/: Exported synthetic datasets across multiple formats.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from faker import Faker

from core.contract_parser import DataContract, parse_contract

GENERATOR_SCRIPT_TEMPLATE = '''"""Standalone Data Generator for Simula-AI Mocking Framework.

Generated automatically by Simula-AI.
Executable independently in production, staging, and CI/CD environments.
"""

import argparse
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from faker import Faker

fake = Faker(["pt_BR"])
Faker.seed(42)
random.seed(42)


def generate_mock_data(rows: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """Generates relational credit mesh entities with 100% referential integrity."""
    if rows <= 0:
        return {
            "empresas": [],
            "propostas": [],
            "garantias": [],
            "operacoes": [],
        }

    # 1. Parent Entity: empresas
    empresas: List[Dict[str, Any]] = []
    empresa_ids: List[str] = []
    for _ in range(rows):
        e_id = str(uuid.uuid4())
        empresa_ids.append(e_id)
        empresas.append({
            "empresa_id": e_id,
            "cnpj": fake.cnpj(),
            "razao_social": fake.company(),
            "faturamento_anual": round(random.uniform(100000.0, 50000000.0), 2),
            "status_cadastral": random.choice(["ATIVO", "INATIVO", "SUSPENSO"]),
        })

    # 2. Child Entity: propostas
    propostas: List[Dict[str, Any]] = []
    base_date = datetime.now() - timedelta(days=90)
    for _ in range(rows):
        p_id = str(uuid.uuid4())
        dt_solic = base_date + timedelta(days=random.randint(1, 45))
        propostas.append({
            "proposta_id": p_id,
            "empresa_id": random.choice(empresa_ids),
            "data_solicitacao": dt_solic.strftime("%Y-%m-%d"),
            "valor_solicitado": round(random.uniform(20000.0, 500000.0), 2),
            "status_proposta": random.choice(["APROVADA", "ANALISE", "RECUSADA"]),
        })

    # Ensure at least some approved proposals exist for operacoes
    approved_propostas = [p for p in propostas if p["status_proposta"] == "APROVADA"]
    if not approved_propostas and propostas:
        propostas[0]["status_proposta"] = "APROVADA"
        approved_propostas = [propostas[0]]

    # 3. Child Entity: garantias
    garantias: List[Dict[str, Any]] = []
    for _ in range(rows):
        parent_prop = random.choice(propostas)
        garantias.append({
            "garantia_id": str(uuid.uuid4()),
            "proposta_id": parent_prop["proposta_id"],
            "tipo_garantia": random.choice(["IMOVEL", "VEICULO", "AVAL", "RECEBIVEIS"]),
            "valor_estimado": round(parent_prop["valor_solicitado"] * random.uniform(0.5, 1.8), 2),
            "grau_risco": random.choice(["BAIXO", "MEDIO", "ALTO"]),
        })

    # 4. Child Entity: operacoes (Only formalised for APROVADA proposals)
    operacoes: List[Dict[str, Any]] = []
    for _ in range(min(rows, len(approved_propostas))):
        prop = random.choice(approved_propostas)
        dt_solic = datetime.strptime(prop["data_solicitacao"], "%Y-%m-%d")
        dt_contrato = dt_solic + timedelta(days=random.randint(1, 30))
        valor_contratado = round(min(prop["valor_solicitado"], prop["valor_solicitado"] * random.uniform(0.7, 1.0)), 2)
        operacoes.append({
            "operacao_id": str(uuid.uuid4()),
            "proposta_id": prop["proposta_id"],
            "data_contratacao": dt_contrato.strftime("%Y-%m-%d"),
            "valor_contratado": valor_contratado,
            "taxa_juros_mensal": round(random.uniform(1.2, 3.5), 2),
            "prazo_meses": random.choice([12, 24, 36, 48, 60]),
        })

    return {
        "empresas": empresas,
        "propostas": propostas,
        "garantias": garantias,
        "operacoes": operacoes,
    }


def save_datasets(
    data: Dict[str, List[Dict[str, Any]]],
    output_dir: Path,
    formats: List[str],
) -> Dict[str, List[str]]:
    """Exports dataset tables to CSV, JSON, and Parquet."""
    saved_files: Dict[str, List[str]] = {}
    normalized_formats = set()
    for fmt in formats:
        f = fmt.strip().lower()
        if f == "all":
            normalized_formats.update(["csv", "json", "parquet"])
        elif "," in f:
            normalized_formats.update(x.strip().lower() for x in f.split(","))
        else:
            normalized_formats.add(f)

    for table_name, records in data.items():
        df = pd.DataFrame(records)
        for fmt in normalized_formats:
            fmt_dir = output_dir / "datasets" / fmt
            fmt_dir.mkdir(parents=True, exist_ok=True)
            out_file = fmt_dir / f"{table_name}.{fmt}"

            if fmt == "csv":
                df.to_csv(out_file, index=False)
            elif fmt == "json":
                df.to_json(out_file, orient="records", indent=2)
            elif fmt == "parquet":
                df.to_parquet(out_file, index=False)

            saved_files.setdefault(table_name, []).append(str(out_file))

    return saved_files


def main():
    parser = argparse.ArgumentParser(description="Simula-AI Standalone Relational Mock Generator")
    parser.add_argument("--rows", type=int, default=50, help="Number of records to generate per table")
    parser.add_argument("--output-dir", type=str, default=".", help="Target output directory")
    parser.add_argument("--format", type=str, default="all", help="Output formats: csv, json, parquet or all")
    args = parser.parse_args()

    out_path = Path(args.output_dir)
    formats = ["all"] if args.format == "all" else args.format.split(",")
    data = generate_mock_data(rows=args.rows)
    saved = save_datasets(data, out_path, formats)
    print(f"Generated {args.rows} rows for {len(data)} tables into {out_path}")


if __name__ == "__main__":
    main()
'''

TEST_MOCK_SCRIPT_TEMPLATE = '''"""Standalone Validation Suite for Simula-AI Mock Datasets.

Tests referential integrity, constraints, business rules, and CNPJ formats.
"""

import re
import pytest
from generator import generate_mock_data


@pytest.fixture(scope="module")
def mock_dataset():
    return generate_mock_data(rows=30)


def test_tables_present(mock_dataset):
    assert "empresas" in mock_dataset
    assert "propostas" in mock_dataset
    assert "garantias" in mock_dataset
    assert "operacoes" in mock_dataset


def test_primary_key_uniqueness(mock_dataset):
    pk_map = {
        "empresas": "empresa_id",
        "propostas": "proposta_id",
        "garantias": "garantia_id",
        "operacoes": "operacao_id",
    }
    for table, pk in pk_map.items():
        records = mock_dataset[table]
        keys = [r[pk] for r in records]
        assert len(keys) == len(set(keys)), f"Duplicate PK in {table}"
        assert all(k for k in keys), f"Empty or null PK in {table}"


def test_cnpj_format(mock_dataset):
    cnpj_pattern = re.compile(r"^\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}$")
    for empresa in mock_dataset["empresas"]:
        assert cnpj_pattern.match(empresa["cnpj"]), f"Invalid CNPJ: {empresa['cnpj']}"


def test_foreign_key_referential_integrity(mock_dataset):
    empresa_ids = {e["empresa_id"] for e in mock_dataset["empresas"]}
    for p in mock_dataset["propostas"]:
        assert p["empresa_id"] in empresa_ids, "Orphan proposal detected"

    proposta_ids = {p["proposta_id"] for p in mock_dataset["propostas"]}
    for g in mock_dataset["garantias"]:
        assert g["proposta_id"] in proposta_ids, "Orphan guarantee detected"

    for op in mock_dataset["operacoes"]:
        assert op["proposta_id"] in proposta_ids, "Orphan operation detected"


def test_business_rules(mock_dataset):
    prop_map = {p["proposta_id"]: p for p in mock_dataset["propostas"]}
    for op in mock_dataset["operacoes"]:
        parent = prop_map[op["proposta_id"]]
        assert parent["status_proposta"] == "APROVADA"
        assert op["valor_contratado"] <= parent["valor_solicitado"]
        assert op["data_contratacao"] >= parent["data_solicitacao"]
'''


def export_deliverables(
    generated_code: str = "",
    output_dir: Path | str = ".",
    contract: Any = None,
    generate_datasets: bool = True,
    rows: int = 10,
    formats: list[str] | None = None,
) -> dict[str, Any]:
    """Generates output/generator.py, output/test_mock.py, and synthetic datasets."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if formats is None:
        formats = ["csv", "json", "parquet"]

    # 1. Determine generator content: use generated_code if valid, otherwise clean template
    generator_file = out_path / "generator.py"
    if generated_code and "def generate_mock_data" in generated_code and "if __name__" in generated_code:
        generator_file.write_text(generated_code, encoding="utf-8")
    else:
        generator_file.write_text(GENERATOR_SCRIPT_TEMPLATE, encoding="utf-8")

    # 2. Write standalone Pytest test suite
    test_mock_file = out_path / "test_mock.py"
    test_mock_file.write_text(TEST_MOCK_SCRIPT_TEMPLATE, encoding="utf-8")

    results: dict[str, Any] = {
        "generator": generator_file,
        "test_mock": test_mock_file,
        "datasets": [],
    }

    # 3. Generate datasets if requested
    if generate_datasets:
        # Dynamically load the generator logic or use built-in generator
        from core.llm_client import MockLLMClient

        fake = Faker(["pt_BR"])
        Faker.seed(42)
        random.seed(42)

        # Generate data
        if rows <= 0:
            tables_data: dict[str, list[dict[str, Any]]] = {
                "empresas": [],
                "propostas": [],
                "garantias": [],
                "operacoes": [],
            }
        else:
            empresas = []
            empresa_ids = []
            for _ in range(rows):
                e_id = str(uuid.uuid4())
                empresa_ids.append(e_id)
                empresas.append({
                    "empresa_id": e_id,
                    "cnpj": fake.cnpj(),
                    "razao_social": fake.company(),
                    "faturamento_anual": round(random.uniform(100000.0, 50000000.0), 2),
                    "status_cadastral": random.choice(["ATIVO", "INATIVO", "SUSPENSO"]),
                })

            propostas = []
            base_date = datetime.now() - timedelta(days=90)
            for _ in range(rows):
                p_id = str(uuid.uuid4())
                dt_solic = base_date + timedelta(days=random.randint(1, 45))
                propostas.append({
                    "proposta_id": p_id,
                    "empresa_id": random.choice(empresa_ids),
                    "data_solicitacao": dt_solic.strftime("%Y-%m-%d"),
                    "valor_solicitado": round(random.uniform(20000.0, 500000.0), 2),
                    "status_proposta": random.choice(["APROVADA", "ANALISE", "RECUSADA"]),
                })

            approved_propostas = [p for p in propostas if p["status_proposta"] == "APROVADA"]
            if not approved_propostas and propostas:
                propostas[0]["status_proposta"] = "APROVADA"
                approved_propostas = [propostas[0]]

            garantias = []
            for _ in range(rows):
                parent_prop = random.choice(propostas)
                garantias.append({
                    "garantia_id": str(uuid.uuid4()),
                    "proposta_id": parent_prop["proposta_id"],
                    "tipo_garantia": random.choice(["IMOVEL", "VEICULO", "AVAL", "RECEBIVEIS"]),
                    "valor_estimado": round(parent_prop["valor_solicitado"] * random.uniform(0.5, 1.8), 2),
                    "grau_risco": random.choice(["BAIXO", "MEDIO", "ALTO"]),
                })

            operacoes = []
            for _ in range(min(rows, len(approved_propostas))):
                prop = random.choice(approved_propostas)
                dt_solic = datetime.strptime(prop["data_solicitacao"], "%Y-%m-%d")
                dt_contrato = dt_solic + timedelta(days=random.randint(1, 30))
                valor_contratado = round(min(prop["valor_solicitado"], prop["valor_solicitado"] * random.uniform(0.7, 1.0)), 2)
                operacoes.append({
                    "operacao_id": str(uuid.uuid4()),
                    "proposta_id": prop["proposta_id"],
                    "data_contratacao": dt_contrato.strftime("%Y-%m-%d"),
                    "valor_contratado": valor_contratado,
                    "taxa_juros_mensal": round(random.uniform(1.2, 3.5), 2),
                    "prazo_meses": random.choice([12, 24, 36, 48, 60]),
                })

            tables_data = {
                "empresas": empresas,
                "propostas": propostas,
                "garantias": garantias,
                "operacoes": operacoes,
            }

        # Normalize formats
        norm_formats = set()
        for f in formats:
            f_clean = f.strip().lower()
            if f_clean == "all":
                norm_formats.update(["csv", "json", "parquet"])
            elif "," in f_clean:
                norm_formats.update(x.strip().lower() for x in f_clean.split(","))
            else:
                norm_formats.add(f_clean)

        for table_name, records in tables_data.items():
            df = pd.DataFrame(records)
            for fmt in norm_formats:
                fmt_dir = out_path / "datasets" / fmt
                fmt_dir.mkdir(parents=True, exist_ok=True)
                dest = fmt_dir / f"{table_name}.{fmt}"
                if fmt == "csv":
                    df.to_csv(dest, index=False)
                elif fmt == "json":
                    df.to_json(dest, orient="records", indent=2)
                elif fmt == "parquet":
                    df.to_parquet(dest, index=False)
                results["datasets"].append(dest)

    return results
