# Technical Analysis & Specification: Milestone 1 (Contract Specification & Foundation)

**Author:** Explorer 1 (Milestone 1)  
**Date:** 2026-10-12  
**Target Scope:** `contracts/exemplo_credito_mesh.yaml`, `core/contract_parser.py`, `pyproject.toml`, `requirements.txt`, `.env.example`, `tests/unit/test_contract_parser.py`

---

## 1. Executive Summary

Milestone 1 establishes the foundational data contract layer for Simula-AI: a complete 4-table corporate credit mesh schema, robust Pydantic v2 models supporting dual foreign-key declarations, Kahn's topological DAG dependency resolution with cycle path diagnostics, strict referential validation, and complete packaging configuration. All components have been prototyped and verified with 19/19 passing unit tests (0.48s runtime) under Python 3.14.

---

## 2. Sample Credit Mesh Contract Specification (`contracts/exemplo_credito_mesh.yaml`)

### 2.1 Domain & Relational Topology

The credit mesh models a corporate banking lending lifecycle:

```
[empresas] (PK: empresa_id)
    │
    │ 1:N
    ▼
[propostas] (PK: proposta_id, FK: empresa_id -> empresas.empresa_id)
    │                         │
    │ 1:N                     │ 1:1 (Status == 'APROVADA')
    ▼                         ▼
[garantias]               [operacoes]
(PK: garantia_id,         (PK: operacao_id,
 FK: proposta_id)          FK: proposta_id,
                           FK: empresa_id)
```

### 2.2 Table Schemas & Constraints

1. **`empresas` (Base Entity / Root DAG Node)**:
   - Primary Key: `empresa_id` (string/uuid, not null, unique)
   - Columns:
     - `cnpj`: string, not null, unique, regex: `^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$`, faker: `cnpj`
     - `razao_social`: string, not null, faker: `company`
     - `nome_fantasia`: string, nullable: true, faker: `company_suffix`
     - `data_fundacao`: date, not null, max: `now`, format: `%Y-%m-%d`
     - `faturamento_anual`: decimal, not null, min: 100,000.00, max: 100,000,000.00
     - `setor`: string, not null, enum: `["INDUSTRIA", "COMERCIO", "SERVICOS", "AGRONEGOCIO", "TECNOLOGIA"]`
     - `score_credito`: integer, not null, min: 0, max: 1000
     - `status_cadastral`: string, not null, enum: `["ATIVO", "INATIVO", "RECUPERACAO_JUDICIAL"]`

2. **`propostas` (Loan Applications / Level 1)**:
   - Primary Key: `proposta_id` (string/uuid, not null, unique)
   - Foreign Key: `empresa_id` referencing `empresas.empresa_id` (many_to_one)
   - Columns:
     - `data_solicitacao`: datetime, not null, min: `2024-01-01T00:00:00`, max: `now`
     - `valor_solicitado`: decimal, not null, min: 10,000.00, max: 10,000,000.00
     - `prazo_meses`: integer, not null, min: 6, max: 120
     - `taxa_juros_mensal`: float, not null, min: 0.010, max: 0.060
     - `finalidade`: string, not null, enum: `["CAPITAL_GIRO", "EXPANSAO", "EQUIPAMENTOS", "REFINANCIAMENTO"]`
     - `status`: string, not null, enum: `["EM_ANALISE", "APROVADA", "REJEITADA", "CANCELADA"]`

3. **`garantias` (Collateral Pledges / Level 2)**:
   - Primary Key: `garantia_id` (string/uuid, not null, unique)
   - Foreign Key: `proposta_id` referencing `propostas.proposta_id` (many_to_one)
   - Columns:
     - `tipo_garantia`: string, not null, enum: `["IMOVEL", "VEICULO", "RECEBIVEIS", "AVAL", "FIANCA_BANCARIA"]`
     - `valor_avaliado`: decimal, not null, min: 5,000.00, max: 20,000,000.00
     - `percentual_cobertura`: float, not null, min: 0.20, max: 3.00
     - `descricao`: string, nullable: true
     - `status_avaliacao`: string, not null, enum: `["AVALIADA", "PENDENTE", "REJEITADA"]`

4. **`operacoes` (Disbursed Loan Contracts / Level 2)**:
   - Primary Key: `operacao_id` (string/uuid, not null, unique)
   - Foreign Keys:
     - `proposta_id`: referencing `propostas.proposta_id` (one_to_one, unique, condition: `propostas.status == 'APROVADA'`)
     - `empresa_id`: referencing `empresas.empresa_id` (many_to_one)
   - Columns:
     - `codigo_contrato`: string, not null, unique, regex: `^OP-2026-\d{6}$`
     - `data_contratacao`: datetime, not null, min: `2024-01-01T00:00:00`
     - `valor_contratado`: decimal, not null, min: 10,000.00, max: 10,000,000.00
     - `saldo_devedor`: decimal, not null, min: 0.00
     - `numero_parcelas`: integer, not null, min: 6, max: 120
     - `parcelas_pagas`: integer, not null, min: 0
     - `status_operacao`: string, not null, enum: `["EM_DIA", "ATRASO", "LIQUIDADA", "INADIMPLENTE"]`

### 2.3 Cross-Table Business Rules (`business_rules`)

| Rule ID | Expression | Description |
|---|---|---|
| `BR01_APROVACAO_OBRIGATORIA` | `operacoes.proposta_id IN propostas[propostas.status == 'APROVADA'].proposta_id` | Only approved proposals can originate an operation. |
| `BR02_CRONOLOGIA_CONTRATUAL` | `operacoes.data_contratacao >= propostas.data_solicitacao` | Contract disbursement date must be on or after application date. |
| `BR03_LIMITE_CONTRATADO` | `operacoes.valor_contratado <= propostas.valor_solicitado` | Disbursed principal cannot exceed requested loan amount. |
| `BR04_SALDO_CONSISTENTE` | `operacoes.saldo_devedor <= operacoes.valor_contratado` | Current outstanding balance cannot exceed principal disbursed. |
| `BR05_AMORTIZACAO_LIMITADA` | `operacoes.parcelas_pagas <= operacoes.numero_parcelas` | Amortized installments cannot exceed contracted term. |
| `BR06_CONSISTENCIA_EMPRESA` | `operacoes.empresa_id == propostas[operacoes.proposta_id == propostas.proposta_id].empresa_id` | Operation borrowing company must strictly match the proposal applicant. |

---

## 3. Contract Parser Architecture (`core/contract_parser.py`)

### 3.1 Pydantic v2 Class Hierarchy

```
DataContract
├── mesh_name: str (AliasChoices: mesh_name, dataset_name)
├── version: str (AliasChoices: version, data_contract_version)
├── domain, description, owner, locale, default_sample_size
├── tables: List[TableContract]
│   ├── name: str
│   ├── primary_key: Union[str, List[str]]
│   ├── sample_size: Optional[int]
│   ├── fields: List[FieldContract]
│   │   ├── name: str
│   │   ├── type: str
│   │   ├── nullable, primary_key, unique: bool
│   │   ├── foreign_key: Optional[str]  # "parent_table.parent_field"
│   │   ├── description, format, faker: Optional[str]
│   │   ├── rules: List[str]
│   │   └── constraints: Dict[str, Any]
│   ├── foreign_keys: List[ForeignKeyDefinition]
│   └── business_rules: List[Union[str, BusinessRuleContract, Dict]]
└── business_rules: List[Union[str, BusinessRuleContract, Dict]]
```

### 3.2 Dual Foreign-Key Reconciliation

Contracts in YAML may declare foreign keys in two ways:
1. Inline field attribute / constraint: `fields: [- name: empresa_id, foreign_key: "empresas.empresa_id"]`
2. Table-level block: `foreign_keys: [- field: empresa_id, references_table: empresas, references_field: empresa_id]`

`TableContract` provides bidirectional reconciliation:
- If defined in `table.foreign_keys`, it automatically populates `field.foreign_key = "references_table.references_field"`.
- If defined on `field.foreign_key`, it parses `"target_table.target_field"` and adds a `ForeignKeyDefinition` to `table.foreign_keys`.
- Format validation enforces the strict `table.field` pattern.

### 3.3 Topological DAG Sorting Algorithm (Kahn's Algorithm)

```python
def get_dag_order(self) -> List[str]:
    # 1. Compute in-degree = number of distinct parent tables
    # 2. Exclude self-referencing foreign keys (table referencing itself)
    # 3. Initialize queue with in_degree == 0 (root tables, sorted alphabetically)
    # 4. Process queue, decrement dependent child in-degrees
    # 5. Maintain queue sorting for deterministic execution
    # 6. If len(ordered) != total_tables: trigger cycle tracing DFS and raise CyclicDependencyError
```

#### Self-Referencing Foreign Key Handling
Tables referencing themselves (e.g. `employees.manager_id -> employees.empresa_id`) are excluded from table-level DAG dependencies to prevent false cycles. The self-reference is preserved in `fields` and `foreign_keys` for mock data generation.

#### Cycle Path Diagnostics
When `len(ordered) != total_tables`, Kahn's algorithm detects a cycle. Rather than raising a generic error, the parser executes a depth-first search on the remaining nodes with `in_degree > 0` to reconstruct the exact cycle path (e.g. `table_a -> table_b -> table_c -> table_a`), outputting a clear diagnostic.

### 3.4 Custom Exception Hierarchy

```python
DataContractError (base)
├── ContractParseError                 # YAML malformed syntax
└── DataContractValidationError        # Relational or schema violations
    ├── DuplicateTableError            # Table name collisions
    ├── DuplicateFieldError            # Column name collisions in table
    ├── MissingTableError              # FK references missing table
    ├── MissingFieldError              # FK references missing column
    ├── MissingPrimaryKeyError         # Table has no PK or PK col missing
    ├── InvalidForeignKeyError         # Format not 'table.field'
    └── CyclicDependencyError          # Circular foreign key dependency
```

---

## 4. Packaging & Dependencies

### 4.1 `pyproject.toml`
Configured with PEP 621 metadata, `simula = "cli.main:app"` console entrypoint, and pinned core dependencies compatible with Python 3.11–3.14:
- `pydantic>=2.7.0,<3.0.0`
- `pyyaml>=6.0.1`
- `pandas>=2.2.0`
- `pyarrow>=16.0.0`
- `fastparquet>=2024.5.0`
- `faker>=25.0.0`
- `pytest>=8.2.0`
- `typer>=0.12.0`
- `rich>=13.7.0`
- `streamlit>=1.35.0`
- `langgraph>=0.2.20,<0.3.0`
- `langchain-core>=0.3.0,<0.4.0`
- `httpx>=0.27.0`
- `openai>=1.40.0`
- `python-dotenv>=1.0.1`

### 4.2 `requirements.txt`
Mirrors `pyproject.toml` dependencies organized by architectural subsystems (Cognitive Loop, Synthetic Mocking, Export, UI, Dev/Testing).

### 4.3 `.env.example`
Provides documented keys:
- `OPENROUTER_API_KEY`: API key for live generation.
- `OPENROUTER_BASE_URL`: `https://openrouter.ai/api/v1`.
- `OPENROUTER_MODEL`: `deepseek/deepseek-r1`.
- `OPENROUTER_FALLBACK_MODEL`: `deepseek/deepseek-chat`.
- `SIMULA_MAX_ITERATIONS`: `5`.
- `SIMULA_SANDBOX_TIMEOUT_SECONDS`: `30`.
- `STREAMLIT_SERVER_PORT`: `8501`.
- `STREAMLIT_SERVER_ADDRESS`: `0.0.0.0`.
- `SIMULA_MOCK_LLM`: `false` (set to `true` for offline CI testing).

---

## 5. Edge Cases & Validation Matrix

| Edge Case | Test Input / Scenario | Expected Outcome | Status |
|---|---|---|---|
| **Happy Path Ingestion** | Full `contracts/exemplo_credito_mesh.yaml` | Parses 4 tables, 6 rules, PKs/FKs correctly populated | Verified |
| **Topological DAG Ordering** | Multi-level tree (`empresas` -> `propostas` -> `garantias` / `operacoes`) | `empresas` first, `propostas` second, children last | Verified |
| **Deterministic DAG** | Repeated calls to `get_dag_order()` | Stable list ordering across runs | Verified |
| **Direct Cycle (2-table)** | `table_a.fk -> table_b.id` AND `table_b.fk -> table_a.id` | Raises `CyclicDependencyError` with `table_a -> table_b -> table_a` | Verified |
| **Indirect Cycle (3-table)** | `alpha -> beta -> gamma -> alpha` | Raises `CyclicDependencyError` identifying cycle nodes | Verified |
| **Self-Referential FK** | `employees.manager_id -> employees.emp_id` | Permitted; does not block table generation order | Verified |
| **Disconnected Tables** | Isolated tables without FKs alongside connected components | All tables included in deterministic sorted order | Verified |
| **Malformed YAML** | Unbalanced brackets / invalid YAML syntax | Raises `ContractParseError` | Verified |
| **Empty Tables** | `tables: []` | Raises `DataContractValidationError` | Verified |
| **Duplicate Table Names** | Two tables named `users` | Raises `DuplicateTableError` | Verified |
| **Duplicate Field Names** | Two fields named `id` in same table | Raises `DuplicateFieldError` | Verified |
| **Missing Primary Key** | Table specifies PK column that does not exist in `fields` | Raises `MissingPrimaryKeyError` | Verified |
| **Nullable Primary Key** | Table PK field configured with `nullable: true` | Raises `DataContractValidationError` ("cannot have nullable=True") | Verified |
| **Composite Primary Key** | `primary_key: ["order_id", "item_id"]` | Both fields marked `primary_key = True`, verified | Verified |
| **Missing Target Table** | FK targets `unknown_table.id` | Raises `MissingTableError` | Verified |
| **Missing Target Field** | FK targets `users.missing_column` | Raises `MissingFieldError` | Verified |
| **Malformed FK Format** | `foreign_key: "no_dot_separator"` | Raises `InvalidForeignKeyError` | Verified |
| **Roundtrip Serialization** | `contract.to_yaml()` -> `from_yaml()` | Exact schema equality preserved | Verified |

---

## 6. Verification Results

Unit test execution using `pytest`:
```bash
uv run --with "pydantic>=2.7" --with "pyyaml>=6.0" --with "pytest>=8.0" \
  pytest .agents/teamwork/teamwork_preview_explorer_m1_1/proposed_test_contract_parser.py -v
```
**Results:** `19 passed in 0.48s (100% pass rate)`

All proposed code artifacts are saved in `/Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_explorer_m1_1/`:
- `proposed_exemplo_credito_mesh.yaml`
- `proposed_contract_parser.py`
- `proposed_test_contract_parser.py`
- `proposed_pyproject.toml`
- `proposed_requirements.txt`
- `proposed_env.example`
