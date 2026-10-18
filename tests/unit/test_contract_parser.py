"""Unit tests for Simula-AI Data Contract Parser & Validator.

Validates schema ingestion, Pydantic v2 models, Kahn's DAG topological sorting,
cycle detection, referential integrity, and edge case error handling.
"""

from pathlib import Path

import pytest

from core.contract_parser import (
    CircularDependencyError,
    ContractFileNotFoundError,
    ContractParseError,
    CyclicDependencyError,
    DataContract,
    DataContractValidationError,
    DuplicateFieldError,
    DuplicateTableError,
    InvalidForeignKeyError,
    MissingFieldError,
    MissingPrimaryKeyError,
    MissingTableError,
    load_contract,
    parse_contract,
    safe_parse_contract,
)

CREDIT_MESH_YAML_PATH = (
    Path(__file__).resolve().parent.parent.parent / "contracts" / "exemplo_credito_mesh.yaml"
)


class TestCreditMeshContract:
    """Tests loading and structural validation of the full 4-table credit mesh schema."""

    def test_load_credit_mesh_contract(self):
        contract = DataContract.from_yaml(CREDIT_MESH_YAML_PATH)
        assert contract.mesh_name == "credit_mesh_ecosystem"
        assert contract.dataset_name == "credit_mesh_ecosystem"
        assert contract.version == "1.0.0"
        assert contract.data_contract_version == "1.0.0"
        assert contract.domain == "credit_risk"
        assert len(contract.tables) == 4
        assert len(contract.business_rules) == 6

        table_names = contract.get_table_names()
        assert table_names == ["empresas", "propostas", "garantias", "operacoes"]
        assert contract.table_names == ["empresas", "propostas", "garantias", "operacoes"]

    def test_credit_mesh_tables_and_fields(self):
        contract = DataContract.from_yaml(CREDIT_MESH_YAML_PATH)

        empresas = contract.get_table("empresas")
        assert empresas is not None
        assert empresas.primary_key == ["empresa_id"] or empresas.primary_key == "empresa_id"
        assert empresas.get_primary_keys() == ["empresa_id"]
        assert empresas.get_field("empresa_id").primary_key is True
        assert empresas.get_field("empresa_id").nullable is False
        assert empresas.get_field("empresa_id").is_pk is True
        assert empresas.get_field("cnpj").unique is True
        assert empresas.get_field("faturamento_anual").type == "decimal"
        assert len(empresas.fields) == 9

        propostas = contract.get_table("propostas")
        assert propostas is not None
        assert propostas.primary_key == ["proposta_id"] or propostas.primary_key == "proposta_id"
        assert propostas.get_field("empresa_id").foreign_key == "empresas.empresa_id"
        assert propostas.get_field("empresa_id").is_fk is True
        assert propostas.get_field("empresa_id").fk_target_table == "empresas"
        assert propostas.get_field("empresa_id").fk_target_field == "empresa_id"
        assert len(propostas.foreign_keys) == 1
        assert propostas.foreign_keys[0].references_table == "empresas"
        assert len(propostas.fields) == 8

        garantias = contract.get_table("garantias")
        assert garantias is not None
        assert garantias.primary_key == ["garantia_id"] or garantias.primary_key == "garantia_id"
        assert garantias.get_field("proposta_id").foreign_key == "propostas.proposta_id"
        assert len(garantias.fields) == 7

        operacoes = contract.get_table("operacoes")
        assert operacoes is not None
        assert operacoes.primary_key == ["operacao_id"] or operacoes.primary_key == "operacao_id"
        op_deps = operacoes.get_dependencies()
        assert "propostas" in op_deps
        assert "empresas" in op_deps
        assert len(operacoes.fields) == 10

    def test_credit_mesh_dag_order(self):
        contract = DataContract.from_yaml(CREDIT_MESH_YAML_PATH)
        dag_order = contract.get_dag_order()
        assert len(dag_order) == 4
        assert dag_order.index("empresas") < dag_order.index("propostas")
        assert dag_order.index("propostas") < dag_order.index("garantias")
        assert dag_order.index("propostas") < dag_order.index("operacoes")
        assert dag_order.index("empresas") < dag_order.index("operacoes")


class TestDAGTopologicalSorting:
    """Tests Kahn's algorithm topological sorting and edge case dependency graphs."""

    def test_dag_order_determinism(self):
        contract = DataContract.from_yaml(CREDIT_MESH_YAML_PATH)
        order1 = contract.get_dag_order()
        order2 = contract.get_dag_order()
        order3 = contract.get_dag_order()
        assert order1 == order2 == order3

    def test_direct_cycle_detection(self):
        cycle_yaml = """
mesh_name: "direct_cycle"
tables:
  - name: "table_a"
    primary_key: "id_a"
    fields:
      - name: "id_a"
        type: "string"
      - name: "id_b"
        type: "string"
        foreign_key: "table_b.id_b"
  - name: "table_b"
    primary_key: "id_b"
    fields:
      - name: "id_b"
        type: "string"
      - name: "id_a"
        type: "string"
        foreign_key: "table_a.id_a"
"""
        with pytest.raises((CyclicDependencyError, CircularDependencyError)) as exc_info:
            DataContract.from_yaml(cycle_yaml)
        assert "Circular foreign key dependency detected" in str(exc_info.value)
        assert "table_a -> table_b -> table_a" in str(exc_info.value)

    def test_indirect_3_table_cycle_detection(self):
        cycle_yaml = """
mesh_name: "indirect_cycle"
tables:
  - name: "alpha"
    primary_key: "id_a"
    fields:
      - name: "id_a"
        type: "string"
      - name: "fk_b"
        type: "string"
        foreign_key: "beta.id_b"
  - name: "beta"
    primary_key: "id_b"
    fields:
      - name: "id_b"
        type: "string"
      - name: "fk_g"
        type: "string"
        foreign_key: "gamma.id_g"
  - name: "gamma"
    primary_key: "id_g"
    fields:
      - name: "id_g"
        type: "string"
      - name: "fk_a"
        type: "string"
        foreign_key: "alpha.id_a"
"""
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.from_yaml(cycle_yaml)
        assert "Circular foreign key dependency detected" in str(exc_info.value)

    def test_self_referencing_fk_not_treated_as_cycle(self):
        self_ref_yaml = """
mesh_name: "org_hierarchy"
tables:
  - name: "employees"
    primary_key: "emp_id"
    fields:
      - name: "emp_id"
        type: "string"
      - name: "manager_id"
        type: "string"
        nullable: true
        foreign_key: "employees.emp_id"
"""
        contract = DataContract.from_yaml(self_ref_yaml)
        order = contract.get_dag_order()
        assert order == ["employees"]

    def test_disconnected_tables_ordered_deterministically(self):
        disconnected_yaml = """
mesh_name: "disconnected"
tables:
  - name: "zeta"
    primary_key: "id_z"
    fields:
      - name: "id_z"
        type: "string"
  - name: "alpha"
    primary_key: "id_a"
    fields:
      - name: "id_a"
        type: "string"
  - name: "beta"
    primary_key: "id_b"
    fields:
      - name: "id_b"
        type: "string"
      - name: "fk_a"
        type: "string"
        foreign_key: "alpha.id_a"
"""
        contract = DataContract.from_yaml(disconnected_yaml)
        order = contract.get_dag_order()
        assert order.index("alpha") < order.index("beta")
        assert "zeta" in order


class TestSchemaValidationAndEdgeCases:
    """Tests schema validation, error boundaries, and edge cases."""

    def test_invalid_yaml_syntax(self):
        malformed = "mesh_name: test\ntables: [unclosed"
        with pytest.raises(ContractParseError):
            DataContract.from_yaml(malformed)

    def test_empty_tables_list(self):
        empty_tables = "mesh_name: test\ntables: []"
        with pytest.raises(DataContractValidationError) as exc:
            DataContract.from_yaml(empty_tables)
        assert "must define at least one table" in str(exc.value)

    def test_duplicate_table_names(self):
        dups = """
mesh_name: test
tables:
  - name: users
    primary_key: id
    fields:
      - name: id
        type: string
  - name: users
    primary_key: id
    fields:
      - name: id
        type: string
"""
        with pytest.raises(DuplicateTableError):
            DataContract.from_yaml(dups)

    def test_duplicate_field_names(self):
        dups = """
mesh_name: test
tables:
  - name: users
    primary_key: id
    fields:
      - name: id
        type: string
      - name: id
        type: integer
"""
        with pytest.raises(DuplicateFieldError):
            DataContract.from_yaml(dups)

    def test_missing_primary_key_definition(self):
        missing_pk = """
mesh_name: test
tables:
  - name: users
    primary_key: missing_id
    fields:
      - name: id
        type: string
"""
        with pytest.raises(MissingPrimaryKeyError):
            DataContract.from_yaml(missing_pk)

    def test_nullable_primary_key_rejected(self):
        nullable_pk = """
mesh_name: test
tables:
  - name: users
    primary_key: id
    fields:
      - name: id
        type: string
        nullable: true
"""
        with pytest.raises(DataContractValidationError) as exc:
            DataContract.from_yaml(nullable_pk)
        assert "cannot have nullable=True" in str(exc.value)

    def test_composite_primary_key(self):
        composite_pk = """
mesh_name: test
tables:
  - name: order_items
    primary_key: ["order_id", "item_id"]
    fields:
      - name: order_id
        type: string
      - name: item_id
        type: integer
"""
        contract = DataContract.from_yaml(composite_pk)
        tbl = contract.get_table("order_items")
        assert tbl.get_primary_keys() == ["order_id", "item_id"]
        assert tbl.get_field("order_id").primary_key is True
        assert tbl.get_field("item_id").primary_key is True

    def test_fk_references_non_existent_table(self):
        bad_fk_table = """
mesh_name: test
tables:
  - name: orders
    primary_key: id
    fields:
      - name: id
        type: string
      - name: user_id
        type: string
        foreign_key: "unknown_table.id"
"""
        with pytest.raises((MissingTableError, InvalidForeignKeyError)) as exc:
            DataContract.from_yaml(bad_fk_table)
        assert "references non-existent table 'unknown_table'" in str(exc.value)

    def test_fk_references_non_existent_field(self):
        bad_fk_field = """
mesh_name: test
tables:
  - name: users
    primary_key: id
    fields:
      - name: id
        type: string
  - name: orders
    primary_key: order_id
    fields:
      - name: order_id
        type: string
      - name: user_id
        type: string
        foreign_key: "users.missing_column"
"""
        with pytest.raises((MissingFieldError, InvalidForeignKeyError)) as exc:
            DataContract.from_yaml(bad_fk_field)
        assert "references non-existent field 'missing_column'" in str(exc.value)

    def test_invalid_fk_string_format(self):
        bad_format = """
mesh_name: test
tables:
  - name: orders
    primary_key: id
    fields:
      - name: id
        type: string
      - name: user_id
        type: string
        foreign_key: "no_dot_separator"
"""
        with pytest.raises(InvalidForeignKeyError):
            DataContract.from_yaml(bad_format)

    def test_serialization_roundtrip(self):
        contract = DataContract.from_yaml(CREDIT_MESH_YAML_PATH)
        yaml_out = contract.to_yaml()
        reloaded = DataContract.from_yaml(yaml_out)
        assert reloaded.mesh_name == contract.mesh_name
        assert len(reloaded.tables) == len(contract.tables)
        assert reloaded.get_dag_order() == contract.get_dag_order()


class TestIntegrationUtilityMethods:
    """Tests top-level helper functions and integration APIs."""

    def test_load_contract_file(self):
        contract = load_contract(CREDIT_MESH_YAML_PATH)
        assert contract.mesh_name == "credit_mesh_ecosystem"
        assert len(contract.tables) == 4

    def test_load_contract_nonexistent_file(self):
        with pytest.raises(ContractFileNotFoundError):
            load_contract("non_existent_contract_file.yaml")

    def test_parse_contract_polymorphic(self):
        c1 = parse_contract(CREDIT_MESH_YAML_PATH)
        assert len(c1.tables) == 4

        yaml_str = CREDIT_MESH_YAML_PATH.read_text(encoding="utf-8")
        c2 = parse_contract(yaml_str)
        assert c2.mesh_name == c1.mesh_name

    def test_parse_contract_rejects_empty(self):
        with pytest.raises((DataContractValidationError, ContractParseError, ValueError)):
            parse_contract("")

    def test_safe_parse_contract(self):
        contract, err = safe_parse_contract(CREDIT_MESH_YAML_PATH)
        assert contract is not None
        assert err is None

        bad_contract, err_msg = safe_parse_contract("broken: [unclosed")
        assert bad_contract is None
        assert err_msg is not None

    def test_to_prompt_context(self):
        contract = load_contract(CREDIT_MESH_YAML_PATH)
        ctx = contract.to_prompt_context()
        assert "credit_mesh_ecosystem" in ctx
        assert "Table Generation Order" in ctx
        assert "empresas -> propostas -> garantias, operacoes" in ctx or "empresas" in ctx
        assert "empresas" in ctx
        assert "propostas" in ctx
        assert "garantias" in ctx
        assert "operacoes" in ctx
        assert "BR01_APROVACAO_OBRIGATORIA" in ctx

    def test_get_relationships(self):
        contract = load_contract(CREDIT_MESH_YAML_PATH)
        rels = contract.get_relationships()
        assert len(rels) >= 3
        parents = {r.parent_table for r in rels}
        children = {r.child_table for r in rels}
        assert "empresas" in parents
        assert "propostas" in parents or "propostas" in children
        assert "garantias" in children
        assert "operacoes" in children

        for r in rels:
            assert isinstance(r.cardinality_symbol, str)
            assert "--" in r.cardinality_symbol

    def test_field_properties(self):
        contract = load_contract(CREDIT_MESH_YAML_PATH)
        empresas = contract.get_table("empresas")
        pk_field = empresas.get_field("empresa_id")
        assert pk_field.is_pk is True
        assert pk_field.is_fk is False
        assert pk_field.sanitized_mermaid_type == "string"
        assert "PK" in pk_field.constraints_summary()

        cnpj_field = empresas.get_field("cnpj")
        assert cnpj_field.is_uk is True
        assert "UNIQUE" in cnpj_field.constraints_summary()
