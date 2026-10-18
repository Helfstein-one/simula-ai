"""Adversarial stress test suite for core/contract_parser.py.

Designed by Empirical Challenger 1 for Milestone 1.
Challenges:
1. Deep and wide DAG topological sorting (20+ tables, diamonds, lattices, massive DAGs).
2. Cycle detection across 2-node, 3-node, and 5-node cycles (assert CyclicDependencyError + cycle path).
3. Extreme inputs: unicode tables/columns (Portuguese, CJK, Cyrillic), self-referential keys, isolated disconnected subgraphs.
4. Complex edge cases: multi-edge dependencies, composite PKs, case sensitivity, large schemas.
"""

from __future__ import annotations

import time
import pytest
import yaml

from core.contract_parser import (
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
    TableContract,
    load_contract,
    parse_contract,
    safe_parse_contract,
)


# ==============================================================================
# Helper Functions to Programmatically Build Contracts
# ==============================================================================

def make_table_dict(
    name: str,
    pk: str = "id",
    fks: list[tuple[str, str, str]] | None = None,
    extra_fields: list[dict] | None = None,
) -> dict:
    """Helper to generate a table contract dictionary.
    
    fks: list of (col_name, target_table, target_pk)
    """
    fields = [
        {"name": pk, "type": "string", "primary_key": True, "nullable": False}
    ]
    fks = fks or []
    for fk_col, target_table, target_pk in fks:
        if fk_col != pk:
            fields.append({
                "name": fk_col,
                "type": "string",
                "foreign_key": f"{target_table}.{target_pk}",
                "nullable": True,
            })
    if extra_fields:
        fields.extend(extra_fields)

    return {
        "name": name,
        "primary_key": pk,
        "fields": fields,
    }


def make_contract_dict(mesh_name: str, tables: list[dict]) -> dict:
    """Helper to wrap tables in a DataContract dict."""
    return {
        "mesh_name": mesh_name,
        "version": "1.0.0",
        "domain": "stress_testing",
        "tables": tables,
    }


def assert_dag_satisfies_dependencies(contract: DataContract, order: list[str]) -> None:
    """Verifies that in the generated DAG order, all parent tables appear BEFORE their children."""
    table_index = {name: idx for idx, name in enumerate(order)}
    assert len(order) == len(contract.tables), f"DAG order size {len(order)} != table count {len(contract.tables)}"
    assert set(order) == {t.name for t in contract.tables}, "Mismatch between DAG tables and contract tables"

    for table in contract.tables:
        child_idx = table_index[table.name]
        for fk in table.foreign_keys:
            if fk.references_table != table.name:  # Exclude self-references
                parent_idx = table_index[fk.references_table]
                assert parent_idx < child_idx, (
                    f"Dependency violation: Parent table '{fk.references_table}' (idx {parent_idx}) "
                    f"must appear before child table '{table.name}' (idx {child_idx})"
                )


# ==============================================================================
# Test Suite 1: Deep & Wide DAG Topological Sorting
# ==============================================================================

class TestDeepAndWideDAGSorting:
    """Adversarial challenge for topological sort scalability, correctness, and determinism."""

    def test_linear_chain_20_tables(self):
        """20 tables in a strict linear chain: T0 -> T1 -> ... -> T19."""
        num_tables = 20
        tables = []
        for i in range(num_tables):
            name = f"chain_table_{i:02d}"
            fks = [(f"fk_prev", f"chain_table_{i-1:02d}", "id")] if i > 0 else []
            tables.append(make_table_dict(name, pk="id", fks=fks))

        contract = DataContract.model_validate(make_contract_dict("deep_chain_20", tables))
        order = contract.get_dag_order()

        expected_order = [f"chain_table_{i:02d}" for i in range(num_tables)]
        assert order == expected_order, f"Linear chain order mismatch: got {order}"
        assert_dag_satisfies_dependencies(contract, order)

    def test_wide_star_fanout_fanin_20_tables(self):
        """1 root table, 18 intermediate tables depending on root, 1 sink depending on all 18 intermediates."""
        tables = [make_table_dict("root_table", pk="id")]
        intermediates = [f"worker_{i:02d}" for i in range(18)]

        for worker in intermediates:
            tables.append(make_table_dict(worker, pk="id", fks=[("fk_root", "root_table", "id")]))

        # Sink table depends on all 18 workers
        sink_fks = [(f"fk_{w}", w, "id") for w in intermediates]
        tables.append(make_table_dict("sink_table", pk="id", fks=sink_fks))

        assert len(tables) == 20
        contract = DataContract.model_validate(make_contract_dict("wide_star_20", tables))
        order = contract.get_dag_order()

        assert order[0] == "root_table", "Root table must be the very first in order"
        assert order[-1] == "sink_table", "Sink table must be the very last in order"
        assert set(order[1:-1]) == set(intermediates), "Intermediate tables must occupy middle slots"
        assert_dag_satisfies_dependencies(contract, order)

    def test_diamond_lattice_22_tables(self):
        """Multi-layer diamond lattice with 22 tables.
        
        Layer 0: 1 root
        Layer 1: 4 tables (depend on root)
        Layer 2: 4 tables (cross dependencies on Layer 1)
        Layer 3: 4 tables (cross dependencies on Layer 2)
        Layer 4: 4 tables (cross dependencies on Layer 3)
        Layer 5: 4 tables (cross dependencies on Layer 4)
        Layer 6: 1 sink (depends on all Layer 5)
        Total: 1 + 4*5 + 1 = 22 tables.
        """
        tables = [make_table_dict("layer0_root", pk="id")]
        prev_layer = ["layer0_root"]

        for layer_num in range(1, 6):
            current_layer = [f"layer{layer_num}_node_{j}" for j in range(4)]
            for j, node in enumerate(current_layer):
                # Each node in current layer depends on two distinct nodes from previous layer
                parent1 = prev_layer[j % len(prev_layer)]
                parent2 = prev_layer[(j + 1) % len(prev_layer)]
                fks = [("fk_p1", parent1, "id")]
                if parent1 != parent2:
                    fks.append(("fk_p2", parent2, "id"))
                tables.append(make_table_dict(node, pk="id", fks=fks))
            prev_layer = current_layer

        # Final sink table
        sink_fks = [(f"fk_s_{p}", p, "id") for p in prev_layer]
        tables.append(make_table_dict("layer6_sink", pk="id", fks=sink_fks))

        assert len(tables) == 22
        contract = DataContract.model_validate(make_contract_dict("diamond_lattice_22", tables))
        order = contract.get_dag_order()

        assert len(order) == 22
        assert order[0] == "layer0_root"
        assert order[-1] == "layer6_sink"
        assert_dag_satisfies_dependencies(contract, order)

    def test_dag_order_stability_and_determinism_50_iterations(self):
        """Topological order must be 100% deterministic and reproducible across multiple invocations."""
        tables = [
            make_table_dict("t_gamma", pk="id"),
            make_table_dict("t_alpha", pk="id"),
            make_table_dict("t_beta", pk="id"),
            make_table_dict("t_delta", pk="id", fks=[("fk_a", "t_alpha", "id"), ("fk_b", "t_beta", "id")]),
            make_table_dict("t_epsilon", pk="id", fks=[("fk_g", "t_gamma", "id")]),
            make_table_dict("t_omega", pk="id", fks=[("fk_d", "t_delta", "id"), ("fk_e", "t_epsilon", "id")]),
        ]
        contract = DataContract.model_validate(make_contract_dict("determinism_test", tables))
        first_order = contract.get_dag_order()

        for _ in range(50):
            assert contract.get_dag_order() == first_order

    def test_massive_scale_dag_100_tables(self):
        """Stress tests scalability on 100 tables arranged in a multi-tier DAG.
        Verifies performance (< 100ms) and strict dependency satisfaction.
        """
        tables = []
        num_layers = 10
        nodes_per_layer = 10
        total_tables = num_layers * nodes_per_layer  # 100 tables

        for layer in range(num_layers):
            for node in range(nodes_per_layer):
                name = f"L{layer:02d}_N{node:02d}"
                fks = []
                if layer > 0:
                    # Depend on nodes in previous layer
                    parent1 = f"L{layer-1:02d}_N{node:02d}"
                    parent2 = f"L{layer-1:02d}_N{(node+1)%nodes_per_layer:02d}"
                    fks.append(("fk_1", parent1, "id"))
                    fks.append(("fk_2", parent2, "id"))
                tables.append(make_table_dict(name, pk="id", fks=fks))

        assert len(tables) == 100
        start_time = time.perf_counter()
        contract = DataContract.model_validate(make_contract_dict("scale_100_tables", tables))
        order = contract.get_dag_order()
        duration = time.perf_counter() - start_time

        assert len(order) == 100
        assert duration < 0.1, f"Topological sort took {duration:.3f}s, exceeded 100ms threshold"
        assert_dag_satisfies_dependencies(contract, order)


# ==============================================================================
# Test Suite 2: Cycle Detection (2-node, 3-node, 5-node, embedded cycles)
# ==============================================================================

class TestCycleDetectionAdversarial:
    """Stress tests cycle detection algorithms and cycle path error reporting."""

    def test_2_node_direct_cycle(self):
        """Table A -> Table B -> Table A with strict cycle loop verification."""
        tables = [
            make_table_dict("tbl_ping", pk="id", fks=[("fk_pong", "tbl_pong", "id")]),
            make_table_dict("tbl_pong", pk="id", fks=[("fk_ping", "tbl_ping", "id")]),
        ]
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.model_validate(make_contract_dict("cycle_2_nodes", tables))

        err_msg = str(exc_info.value)
        assert "Circular foreign key dependency detected" in err_msg
        assert "Cycle path:" in err_msg
        
        # Verify strict closed loop structure
        path_str = err_msg.split("Cycle path:")[1].strip()
        nodes = [n.strip() for n in path_str.split("->")]
        assert len(nodes) == 3, f"Expected 3 elements (A -> B -> A), got {nodes}"
        assert nodes[0] == nodes[-1], f"Cycle path must close: {nodes}"
        assert set(nodes) == {"tbl_ping", "tbl_pong"}

    def test_3_node_cycle(self):
        """Triangular cycle: C1 -> C2 -> C3 -> C1 with strict cycle loop verification."""
        tables = [
            make_table_dict("tri_1", pk="id", fks=[("fk_2", "tri_2", "id")]),
            make_table_dict("tri_2", pk="id", fks=[("fk_3", "tri_3", "id")]),
            make_table_dict("tri_3", pk="id", fks=[("fk_1", "tri_1", "id")]),
        ]
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.model_validate(make_contract_dict("cycle_3_nodes", tables))

        err_msg = str(exc_info.value)
        assert "Circular foreign key dependency detected" in err_msg
        path_str = err_msg.split("Cycle path:")[1].strip()
        nodes = [n.strip() for n in path_str.split("->")]
        assert len(nodes) == 4, f"Expected 4 elements (C1 -> C2 -> C3 -> C1), got {nodes}"
        assert nodes[0] == nodes[-1], f"Cycle path must close: {nodes}"
        assert set(nodes) == {"tri_1", "tri_2", "tri_3"}

    def test_5_node_cycle(self):
        """Pentagonal cycle: P1 -> P2 -> P3 -> P4 -> P5 -> P1 with strict cycle loop verification."""
        tables = [
            make_table_dict("penta_1", pk="id", fks=[("fk_2", "penta_2", "id")]),
            make_table_dict("penta_2", pk="id", fks=[("fk_3", "penta_3", "id")]),
            make_table_dict("penta_3", pk="id", fks=[("fk_4", "penta_4", "id")]),
            make_table_dict("penta_4", pk="id", fks=[("fk_5", "penta_5", "id")]),
            make_table_dict("penta_5", pk="id", fks=[("fk_1", "penta_1", "id")]),
        ]
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.model_validate(make_contract_dict("cycle_5_nodes", tables))

        err_msg = str(exc_info.value)
        assert "Circular foreign key dependency detected" in err_msg
        path_str = err_msg.split("Cycle path:")[1].strip()
        nodes = [n.strip() for n in path_str.split("->")]
        assert len(nodes) == 6, f"Expected 6 elements (5 edges closing loop), got {nodes}"
        assert nodes[0] == nodes[-1], f"Cycle path must close: {nodes}"
        assert set(nodes) == {f"penta_{i}" for i in range(1, 6)}

    def test_embedded_cycle_within_20_table_dag(self):
        """10 valid upstream nodes feed into a 3-node cycle, which feeds into 7 downstream nodes."""
        tables = []
        # Upstream valid chain: u0 -> u1 -> ... -> u9
        for i in range(10):
            fks = [(f"fk_prev", f"u_{i-1}", "id")] if i > 0 else []
            tables.append(make_table_dict(f"u_{i}", pk="id", fks=fks))

        # 3-node cycle: cyc_a -> cyc_b -> cyc_c -> cyc_a
        # cyc_a also depends on u_9
        tables.append(make_table_dict("cyc_a", pk="id", fks=[("fk_u", "u_9", "id"), ("fk_b", "cyc_b", "id")]))
        tables.append(make_table_dict("cyc_b", pk="id", fks=[("fk_c", "cyc_c", "id")]))
        tables.append(make_table_dict("cyc_c", pk="id", fks=[("fk_a", "cyc_a", "id")]))

        # Downstream valid tail depending on cyc_c: d0 -> d1 -> ... -> d6
        tables.append(make_table_dict("d_0", pk="id", fks=[("fk_c", "cyc_c", "id")]))
        for i in range(1, 7):
            tables.append(make_table_dict(f"d_{i}", pk="id", fks=[(f"fk_prev", f"d_{i-1}", "id")]))

        assert len(tables) == 20
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.model_validate(make_contract_dict("embedded_cycle_20", tables))

        err_msg = str(exc_info.value)
        assert "Circular foreign key dependency detected" in err_msg
        assert "cyc_a" in err_msg
        assert "cyc_b" in err_msg
        assert "cyc_c" in err_msg

    def test_disjoint_parallel_cycles(self):
        """Two separate independent cycles in the same contract."""
        tables = [
            # Cycle 1: c1_a <-> c1_b
            make_table_dict("c1_a", pk="id", fks=[("fk_b", "c1_b", "id")]),
            make_table_dict("c1_b", pk="id", fks=[("fk_a", "c1_a", "id")]),
            # Cycle 2: c2_x -> c2_y -> c2_z -> c2_x
            make_table_dict("c2_x", pk="id", fks=[("fk_y", "c2_y", "id")]),
            make_table_dict("c2_y", pk="id", fks=[("fk_z", "c2_z", "id")]),
            make_table_dict("c2_z", pk="id", fks=[("fk_x", "c2_x", "id")]),
            # Independent valid table
            make_table_dict("clean_table", pk="id"),
        ]
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.model_validate(make_contract_dict("disjoint_cycles", tables))

        err_msg = str(exc_info.value)
        assert "Circular foreign key dependency detected" in err_msg


# ==============================================================================
# Test Suite 3: Extreme Inputs (Unicode, Self-References, Disconnected Subgraphs)
# ==============================================================================

class TestExtremeInputs:
    """Stress tests unicode character handling, self-references, and disconnected graphs."""

    def test_unicode_portuguese_accents(self):
        """Table names and column names with Portuguese accents: ç, ã, é, ó, ú."""
        tables = [
            make_table_dict(
                name="instituição_financeira",
                pk="código_identificador",
                extra_fields=[
                    {"name": "razão_social", "type": "string", "unique": True},
                    {"name": "situação_cadastral", "type": "string"},
                ]
            ),
            make_table_dict(
                name="operações_crédito",
                pk="id_operação",
                fks=[("id_instituição", "instituição_financeira", "código_identificador")],
                extra_fields=[
                    {"name": "valor_contratação", "type": "decimal"},
                    {"name": "data_emissão", "type": "date"},
                ]
            ),
        ]
        contract = DataContract.model_validate(make_contract_dict("contrato_crédito_pt", tables))
        order = contract.get_dag_order()

        assert order == ["instituição_financeira", "operações_crédito"]
        assert_dag_satisfies_dependencies(contract, order)

        # Verify YAML roundtrip with unicode
        yaml_str = contract.to_yaml()
        assert "instituição_financeira" in yaml_str
        assert "situação_cadastral" in yaml_str
        reloaded = DataContract.from_yaml(yaml_str)
        assert reloaded.get_dag_order() == order

        # Verify prompt context rendering
        ctx = contract.to_prompt_context()
        assert "instituição_financeira" in ctx
        assert "operações_crédito" in ctx

    def test_unicode_cjk_japanese(self):
        """Full CJK table and field contracts (Japanese Kanji / Hiragana)."""
        tables = [
            make_table_dict(
                name="顧客テーブル",  # Customer table
                pk="顧客ID",
                extra_fields=[
                    {"name": "氏名", "type": "string"},
                    {"name": "作成日時", "type": "datetime"},
                ]
            ),
            make_table_dict(
                name="注文テーブル",  # Order table
                pk="注文ID",
                fks=[("購入者ID", "顧客テーブル", "顧客ID")],
                extra_fields=[
                    {"name": "合計金額", "type": "decimal"},
                ]
            ),
        ]
        contract = DataContract.model_validate(make_contract_dict("cjk_mesh", tables))
        order = contract.get_dag_order()

        assert order == ["顧客テーブル", "注文テーブル"]
        assert_dag_satisfies_dependencies(contract, order)

    def test_unicode_cyrillic(self):
        """Full Cyrillic Russian schema."""
        tables = [
            make_table_dict(
                name="клиенты",  # Clients
                pk="ид_клиента",
                extra_fields=[{"name": "имя", "type": "string"}]
            ),
            make_table_dict(
                name="счета",  # Accounts
                pk="ид_счета",
                fks=[("ид_клиента", "клиенты", "ид_клиента")],
                extra_fields=[{"name": "баланс", "type": "decimal"}]
            ),
        ]
        contract = DataContract.model_validate(make_contract_dict("cyrillic_mesh", tables))
        order = contract.get_dag_order()
        assert order == ["клиенты", "счета"]
        assert_dag_satisfies_dependencies(contract, order)

    def test_self_referential_keys_hierarchical(self):
        """Organizational hierarchy with self-referencing foreign keys.
        Should NOT be treated as a cycle.
        """
        tables = [
            {
                "name": "departments",
                "primary_key": "dept_id",
                "fields": [
                    {"name": "dept_id", "type": "string", "primary_key": True},
                    {"name": "name", "type": "string"},
                ]
            },
            {
                "name": "employees",
                "primary_key": "emp_id",
                "fields": [
                    {"name": "emp_id", "type": "string", "primary_key": True},
                    {"name": "name", "type": "string"},
                    {"name": "dept_id", "type": "string", "foreign_key": "departments.dept_id"},
                    # Self-references:
                    {"name": "manager_id", "type": "string", "nullable": True, "foreign_key": "employees.emp_id"},
                    {"name": "mentor_id", "type": "string", "nullable": True, "foreign_key": "employees.emp_id"},
                ]
            },
            {
                "name": "tasks",
                "primary_key": "task_id",
                "fields": [
                    {"name": "task_id", "type": "string", "primary_key": True},
                    {"name": "assigned_to", "type": "string", "foreign_key": "employees.emp_id"},
                ]
            }
        ]
        contract = DataContract.model_validate(make_contract_dict("org_hierarchy_mesh", tables))
        order = contract.get_dag_order()

        assert order == ["departments", "employees", "tasks"]
        assert_dag_satisfies_dependencies(contract, order)

        emp = contract.get_table("employees")
        assert len(emp.foreign_keys) == 3
        # In get_dependencies(), self-reference must be excluded
        assert emp.get_dependencies() == ["departments"]

    def test_self_reference_to_missing_field_fails(self):
        """Self-referential FK targeting a non-existent field in itself must raise MissingFieldError."""
        tables = [
            {
                "name": "employees",
                "primary_key": "emp_id",
                "fields": [
                    {"name": "emp_id", "type": "string", "primary_key": True},
                    {"name": "manager_id", "type": "string", "foreign_key": "employees.non_existent_column"},
                ]
            }
        ]
        with pytest.raises(MissingFieldError) as exc:
            DataContract.model_validate(make_contract_dict("bad_self_ref", tables))
        assert "references non-existent field 'non_existent_column'" in str(exc.value)

    def test_multiple_disconnected_subgraphs(self):
        """5 completely isolated subgraphs in the same contract:
        - Subgraph 1: isolated single node iso_1
        - Subgraph 2: chain c2_a -> c2_b -> c2_c
        - Subgraph 3: isolated single node iso_2
        - Subgraph 4: diamond c4_root -> (c4_left, c4_right) -> c4_sink
        - Subgraph 5: isolated single node iso_3
        """
        tables = [
            make_table_dict("iso_1", pk="id"),
            make_table_dict("c2_a", pk="id"),
            make_table_dict("c2_b", pk="id", fks=[("fk_a", "c2_a", "id")]),
            make_table_dict("c2_c", pk="id", fks=[("fk_b", "c2_b", "id")]),
            make_table_dict("iso_2", pk="id"),
            make_table_dict("c4_root", pk="id"),
            make_table_dict("c4_left", pk="id", fks=[("fk_r", "c4_root", "id")]),
            make_table_dict("c4_right", pk="id", fks=[("fk_r", "c4_root", "id")]),
            make_table_dict("c4_sink", pk="id", fks=[("fk_l", "c4_left", "id"), ("fk_r", "c4_right", "id")]),
            make_table_dict("iso_3", pk="id"),
        ]
        contract = DataContract.model_validate(make_contract_dict("disconnected_mesh", tables))
        order = contract.get_dag_order()

        assert len(order) == 10
        assert_dag_satisfies_dependencies(contract, order)

        # Isolated nodes must be included
        assert "iso_1" in order
        assert "iso_2" in order
        assert "iso_3" in order

        # Component 2 dependencies
        assert order.index("c2_a") < order.index("c2_b") < order.index("c2_c")

        # Component 4 dependencies
        assert order.index("c4_root") < order.index("c4_left")
        assert order.index("c4_root") < order.index("c4_right")
        assert order.index("c4_left") < order.index("c4_sink")
        assert order.index("c4_right") < order.index("c4_sink")


# ==============================================================================
# Test Suite 4: Complex Edge Cases & Relational Integrity
# ==============================================================================

class TestComplexEdgeCases:
    """Stress tests multi-foreign keys, composite keys, case normalization, and error boundaries."""

    def test_multi_foreign_keys_to_same_parent(self):
        """Child table has multiple foreign keys pointing to the same parent table
        (e.g. transfers with source_account_id and destination_account_id).
        Must NOT artificially inflate in_degree or cause topological ordering failures.
        """
        tables = [
            make_table_dict("accounts", pk="account_id"),
            make_table_dict(
                "transfers",
                pk="transfer_id",
                fks=[
                    ("source_account_id", "accounts", "account_id"),
                    ("destination_account_id", "accounts", "account_id"),
                ]
            )
        ]
        contract = DataContract.model_validate(make_contract_dict("transfers_mesh", tables))
        order = contract.get_dag_order()

        assert order == ["accounts", "transfers"]
        tbl_transfers = contract.get_table("transfers")
        assert tbl_transfers.get_dependencies() == ["accounts"]
        assert len(tbl_transfers.foreign_keys) == 2

    def test_composite_primary_key_with_dependencies(self):
        """Table with composite PK referencing external parent tables."""
        tables = [
            make_table_dict("students", pk="student_id"),
            make_table_dict("courses", pk="course_id"),
            {
                "name": "enrollments",
                "primary_key": ["student_id", "course_id"],
                "fields": [
                    {"name": "student_id", "type": "string", "foreign_key": "students.student_id"},
                    {"name": "course_id", "type": "string", "foreign_key": "courses.course_id"},
                    {"name": "enrollment_date", "type": "date"},
                ]
            }
        ]
        contract = DataContract.model_validate(make_contract_dict("school_mesh", tables))
        order = contract.get_dag_order()

        assert order.index("students") < order.index("enrollments")
        assert order.index("courses") < order.index("enrollments")

        enroll = contract.get_table("enrollments")
        assert enroll.get_primary_keys() == ["student_id", "course_id"]
        assert enroll.get_field("student_id").primary_key is True
        assert enroll.get_field("course_id").primary_key is True

    def test_case_insensitive_table_lookup(self):
        """get_table should find table regardless of uppercase/lowercase."""
        tables = [make_table_dict("UserProfiles", pk="id")]
        contract = DataContract.model_validate(make_contract_dict("case_test", tables))

        assert contract.get_table("UserProfiles") is not None
        assert contract.get_table("userprofiles") is not None
        assert contract.get_table("USERPROFILES") is not None
        assert contract.get_table("NonExistent") is None

    def test_case_insensitive_field_lookup(self):
        """get_field should find field regardless of uppercase/lowercase."""
        table = TableContract.model_validate(make_table_dict("users", pk="UserId"))
        assert table.get_field("UserId") is not None
        assert table.get_field("userid") is not None
        assert table.get_field("USERID") is not None
        assert table.get_field("missing") is None

    def test_transitive_dense_dag_k5(self):
        """Complete transitive DAG with 5 nodes where every node i depends on all j < i."""
        nodes = [f"t_{i}" for i in range(5)]
        tables = []
        for i, node in enumerate(nodes):
            fks = [(f"fk_{j}", nodes[j], "id") for j in range(i)]
            tables.append(make_table_dict(node, pk="id", fks=fks))

        contract = DataContract.model_validate(make_contract_dict("dense_k5", tables))
        order = contract.get_dag_order()

        assert order == nodes
        assert_dag_satisfies_dependencies(contract, order)

    def test_table_with_50_columns_performance(self):
        """Large schema: single table with 50 diverse fields, constraints, enums, regexes."""
        fields = [
            {"name": "id", "type": "string", "primary_key": True, "nullable": False}
        ]
        for col_idx in range(1, 50):
            fields.append({
                "name": f"column_{col_idx:02d}",
                "type": "string" if col_idx % 2 == 0 else "integer",
                "nullable": col_idx % 3 == 0,
                "unique": col_idx % 7 == 0,
                "regex": r"^\d{4}$" if col_idx % 5 == 0 else None,
                "min_value": 0 if col_idx % 4 == 0 else None,
                "max_value": 1000 if col_idx % 4 == 0 else None,
                "enum_values": ["A", "B", "C"] if col_idx % 6 == 0 else [],
                "description": f"Field specification {col_idx}",
            })

        table_dict = {
            "name": "wide_entity",
            "primary_key": "id",
            "sample_size": 500,
            "fields": fields,
        }
        contract = DataContract.model_validate(make_contract_dict("wide_schema_mesh", [table_dict]))
        assert len(contract.tables[0].fields) == 50
        assert contract.get_dag_order() == ["wide_entity"]
        prompt_ctx = contract.to_prompt_context()
        assert "wide_entity" in prompt_ctx
        assert "column_49" in prompt_ctx

    def test_cycle_with_interleaved_self_references(self):
        """Cycle where nodes also contain self-referential keys."""
        tables = [
            {
                "name": "node_x",
                "primary_key": "id",
                "fields": [
                    {"name": "id", "type": "string", "primary_key": True},
                    {"name": "self_parent", "type": "string", "foreign_key": "node_x.id"},
                    {"name": "fk_y", "type": "string", "foreign_key": "node_y.id"},
                ]
            },
            {
                "name": "node_y",
                "primary_key": "id",
                "fields": [
                    {"name": "id", "type": "string", "primary_key": True},
                    {"name": "self_mentor", "type": "string", "foreign_key": "node_y.id"},
                    {"name": "fk_x", "type": "string", "foreign_key": "node_x.id"},
                ]
            }
        ]
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.model_validate(make_contract_dict("cycle_with_self_refs", tables))

        err_msg = str(exc_info.value)
        assert "Circular foreign key dependency detected" in err_msg
        assert "node_x" in err_msg and "node_y" in err_msg

    def test_unicode_emojis_and_symbols(self):
        """Table names and fields with emojis and special symbols."""
        tables = [
            make_table_dict("t_🚀_rocket", pk="pk_🔥"),
            make_table_dict("t_🛰️_satellite", pk="pk_📡", fks=[("fk_rocket", "t_🚀_rocket", "pk_🔥")]),
        ]
        contract = DataContract.model_validate(make_contract_dict("emoji_mesh", tables))
        order = contract.get_dag_order()
        assert order == ["t_🚀_rocket", "t_🛰️_satellite"]
        assert_dag_satisfies_dependencies(contract, order)

    def test_multi_root_multi_sink_diamond_forest(self):
        """Forest of 3 roots merging into 4 intermediate diamonds and 2 separate sinks."""
        tables = [
            make_table_dict("root_1", pk="id"),
            make_table_dict("root_2", pk="id"),
            make_table_dict("root_3", pk="id"),
            make_table_dict("mid_1", pk="id", fks=[("fk_r1", "root_1", "id"), ("fk_r2", "root_2", "id")]),
            make_table_dict("mid_2", pk="id", fks=[("fk_r2", "root_2", "id"), ("fk_r3", "root_3", "id")]),
            make_table_dict("mid_3", pk="id", fks=[("fk_m1", "mid_1", "id"), ("fk_m2", "mid_2", "id")]),
            make_table_dict("sink_1", pk="id", fks=[("fk_m3", "mid_3", "id")]),
            make_table_dict("sink_2", pk="id", fks=[("fk_m1", "mid_1", "id"), ("fk_m3", "mid_3", "id")]),
        ]
        contract = DataContract.model_validate(make_contract_dict("diamond_forest", tables))
        order = contract.get_dag_order()
        assert len(order) == 8
        assert_dag_satisfies_dependencies(contract, order)

    def test_polymorphic_parse_invalid_inputs(self):
        """safe_parse_contract should gracefully handle arbitrary bad inputs without unhandled crash."""
        bad_inputs = [
            "",
            "   \n  \t ",
            "12345",
            "- item1\n- item2",
            "{unclosed: yaml",
            None,
        ]
        for bad in bad_inputs:
            contract, err = safe_parse_contract(bad)
            assert contract is None
            assert err is not None
            assert len(err) > 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
