"""Extended testing for all edge cases."""
import sys
from pathlib import Path

# Add prototype to sys.path
sys.path.insert(0, str(Path(__file__).parent))
from scratch_prototype import (
    DataContract, TableContract, FieldContract,
    DataContractError, ContractParseError, DataContractValidationError,
    DuplicateTableError, DuplicateFieldError, MissingTableError,
    MissingFieldError, MissingPrimaryKeyError, InvalidForeignKeyError,
    CyclicDependencyError
)

def test_3_table_cycle():
    yaml_content = """
mesh_name: "cycle_3"
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
      - name: "id_c"
        type: "string"
        foreign_key: "table_c.id_c"
  - name: "table_c"
    primary_key: "id_c"
    fields:
      - name: "id_c"
        type: "string"
      - name: "id_a"
        type: "string"
        foreign_key: "table_a.id_a"
"""
    try:
        DataContract.from_yaml(yaml_content)
        assert False, "Should have failed on 3-table cycle"
    except CyclicDependencyError as e:
        print("[PASS] 3-table cycle caught:", e)

def test_self_referencing_fk():
    yaml_content = """
mesh_name: "self_ref"
tables:
  - name: "funcionarios"
    primary_key: "func_id"
    fields:
      - name: "func_id"
        type: "string"
      - name: "gerente_id"
        type: "string"
        nullable: true
        foreign_key: "funcionarios.func_id"
"""
    contract = DataContract.from_yaml(yaml_content)
    order = contract.get_dag_order()
    assert order == ["funcionarios"]
    print("[PASS] Self-referencing FK correctly permitted without false cycle. Order:", order)

def test_composite_pk():
    yaml_content = """
mesh_name: "composite_pk"
tables:
  - name: "itens_pedido"
    primary_key: ["pedido_id", "item_id"]
    fields:
      - name: "pedido_id"
        type: "string"
      - name: "item_id"
        type: "integer"
      - name: "quantidade"
        type: "integer"
"""
    contract = DataContract.from_yaml(yaml_content)
    tbl = contract.get_table("itens_pedido")
    assert tbl is not None
    assert tbl.get_primary_keys() == ["pedido_id", "item_id"]
    assert tbl.get_field("pedido_id").primary_key is True
    assert tbl.get_field("item_id").primary_key is True
    print("[PASS] Composite primary key parsed and synced.")

def test_duplicate_fields():
    yaml_content = """
mesh_name: "dup_fields"
tables:
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
      - name: "id"
        type: "integer"
"""
    try:
        DataContract.from_yaml(yaml_content)
        assert False, "Should fail on duplicate fields"
    except DuplicateFieldError as e:
        print("[PASS] Duplicate field detected:", e)

def test_missing_field_fk():
    yaml_content = """
mesh_name: "missing_field"
tables:
  - name: "table_a"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
  - name: "table_b"
    primary_key: "id_b"
    fields:
      - name: "id_b"
        type: "string"
      - name: "fk"
        type: "string"
        foreign_key: "table_a.non_existent_field"
"""
    try:
        DataContract.from_yaml(yaml_content)
        assert False, "Should fail on missing field in target table"
    except MissingFieldError as e:
        print("[PASS] Missing target field caught:", e)

def test_nullable_pk():
    yaml_content = """
mesh_name: "nullable_pk"
tables:
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
        nullable: true
"""
    try:
        DataContract.from_yaml(yaml_content)
        assert False, "Should fail on nullable PK"
    except DataContractValidationError as e:
        print("[PASS] Nullable primary key caught:", e)

def test_disconnected_tables():
    yaml_content = """
mesh_name: "disconnected"
tables:
  - name: "users"
    primary_key: "user_id"
    fields:
      - name: "user_id"
        type: "string"
  - name: "products"
    primary_key: "product_id"
    fields:
      - name: "product_id"
        type: "string"
  - name: "orders"
    primary_key: "order_id"
    fields:
      - name: "order_id"
        type: "string"
      - name: "user_id"
        type: "string"
        foreign_key: "users.user_id"
"""
    contract = DataContract.from_yaml(yaml_content)
    order = contract.get_dag_order()
    # users and products are roots; orders depends on users
    assert "users" in order and "products" in order and "orders" in order
    assert order.index("users") < order.index("orders")
    print("[PASS] Disconnected tables DAG order:", order)

if __name__ == "__main__":
    test_3_table_cycle()
    test_self_referencing_fk()
    test_composite_pk()
    test_duplicate_fields()
    test_missing_field_fk()
    test_nullable_pk()
    test_disconnected_tables()
    print("ALL EDGE CASE TESTS PASSED!")
