# ⚡ Simula-AI: Framework Autônomo de Mocking Relacional para Data Mesh

<p align="center">
  <img src="assets/hermes.webp" alt="Hermes AI" width="180" style="border-radius: 50%; border: 3px solid #00d2ff;" />
</p>

<p align="center">
  <b>Simulação de Dados Sintéticos Relacionais com Integridade Estrita para Ecossistemas de Data Mesh</b><br>
  <i>Powered by <b>Hermes 3 AI</b> (Nous Research) • Arquitetura Cognitiva CoALA • LangGraph • Sandbox Pytest • Podman Rootless</i>
</p>

<p align="center">
  <a href="#-visão-geral"><img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg" alt="Python Version"></a>
  <a href="#-conteinerização-com-podman"><img src="https://img.shields.io/badge/Podman-Rootless%20Ready-purple.svg" alt="Podman"></a>
  <a href="#-hermes-3-ai--fallback"><img src="https://img.shields.io/badge/LLM-Hermes%203%20(405B%2F70B)-orange.svg" alt="Hermes 3"></a>
  <a href="#-testes-e-garantia-de-qualidade"><img src="https://img.shields.io/badge/Tests-97%2F97%20Passed-brightgreen.svg" alt="Tests"></a>
  <a href="#-licença"><img src="https://img.shields.io/badge/License-Apache%202.0-lightgrey.svg" alt="License"></a>
</p>

---

## 📖 Visão Geral

Em ecossistemas de **Data Mesh**, a simulação de dados produtivos para homologação, testes de carga e validação de contratos de dados esbarra em um desafio crítico: **manter a integridade referencial e coerência de negócio através de múltiplas tabelas correlacionadas sem expor PII (dados sensíveis reais)**.

O **Simula-AI** soluciona essa dor através de um **ciclo cognitivo autônomo fechado**:
1. **Ingestão de Contratos de Dados (YAML):** Validação estrita via Pydantic v2 e ordenação topológica do DAG de dependências entre tabelas.
2. **Cognição via Hermes 3 AI (Nous Research):** Especializado em raciocínio estruturado e dados sintéticos coerentes, com fallback automático no OpenRouter para **Qwen 2.5 Coder** e **DeepSeek** em caso de rate limit (HTTP 429).
3. **Sandbox Isolado Pytest (Sem `eval()`):** Executa o gerador e os testes em subprocesso com timeout estrito de sistema operacional. Se falhar, o *traceback* é injetado na **Memória Episódica** da IA, forçando a autocorreção até atingir 100% de sucesso.
4. **Entregáveis Autônomos:** Produz o script independente `generator.py`, a suíte `test_mock.py`, o diagrama Mermaid ER e os datasets prontos em **CSV**, **JSON** e **Parquet**.

---

## 🏛️ Arquitetura de Dados (Draw.io & Visão Geral)

<p align="center">
  <img src="docs/assets/simula_data_mesh_architecture.png" alt="Simula-AI Data Mesh Architecture with Draw.io & Hermes AI" width="100%" style="border-radius: 12px; border: 1px solid #1e293b; box-shadow: 0 10px 30px rgba(0,0,0,0.5);" />
</p>

> 💡 **Arquivo Editável:** O diagrama oficial com ícones e fluxo completo está disponível em [`docs/simula_data_mesh_architecture.drawio`](docs/simula_data_mesh_architecture.drawio) (compatível com [diagrams.net](https://app.diagrams.net) e a extensão Draw.io do VS Code).

---

## 🔄 Fluxo Cognitivo CoALA (Mermaid Diagram)

A arquitetura do agente segue o padrão formal **CoALA (Cognitive Architectures for Language Agents)** estruturado em **LangGraph**:

```mermaid
flowchart TD
    subgraph INTAKE ["1. Intake & Ingestão"]
        YAML["Contrato de Dados (YAML)"] --> PARSER["Parser de Esquema & DAG Relacional"]
        PARSER --> INIT["node_initialize: Carga da Memória Procedimental"]
    end

    subgraph COGNITION ["2. Cognição & Memória CoALA"]
        INIT --> WM["Working Memory: Esquema + Contexto"]
        EM["Episodic Memory: Histórico de Falhas & Tracebacks"] -.-> GEN
        WM --> GEN["node_internal_action_generate<br/>Hermes 3 AI (OpenRouter)<br/>Parser Regex & AST Validator"]
    end

    subgraph EXECUTION ["3. Sandbox de Execução & Avaliação"]
        GEN --> SAN["node_external_action_execute<br/>Subprocess Pytest Sandbox<br/>Timeout Estrito (30s) • Sem eval()"]
        SAN --> EVAL{"route_decision<br/>Pytest Exit Code == 0?"}
    end

    subgraph RECOVERY ["4. Autocorreção ou Entrega"]
        EVAL -- "Falha (Exit 1/2) e Iterações < Max" --> FAIL["Captura de Traceback & Injeção em Memória Episódica"]
        FAIL --> GEN
        EVAL -- "Sucesso (Exit 0)" --> OUT["Exportação de Entregáveis<br/>generator.py • test_mock.py • datasets/"]
        EVAL -- "Iterações >= Max" --> ABORT["Encerramento por Limite de Retentativas"]
    end

    style GEN fill:#1e293b,stroke:#f5af19,stroke-width:2px,color:#fff
    style SAN fill:#0f172a,stroke:#10b981,stroke-width:2px,color:#fff
    style FAIL fill:#450a0a,stroke:#f43f5e,stroke-width:1.5px,color:#fca5a5
    style OUT fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#ecfdf5
```

---

## 📊 Diagrama Entidade-Relacionamento do Mesh (Mermaid ER)

Diagrama gerado automaticamente pelo Simula-AI a partir do contrato [`contracts/exemplo_credito_mesh.yaml`](contracts/exemplo_credito_mesh.yaml):

```mermaid
erDiagram
    EMPRESAS {
        string empresa_id PK "Identificador global da empresa"
        string cnpj UK "Cadastro Nacional da Pessoa Jurídica"
        string razao_social "Razão social oficial"
        string nome_fantasia "Nome comercial / fantasia"
        date data_fundacao "Data de constituição"
        decimal faturamento_anual "Faturamento bruto em BRL"
        string setor "Setor de atividade econômica"
        integer score_credito "Score de crédito (0 a 1000)"
        string status_cadastral "Situação cadastral ativa/inativa"
    }

    PROPOSTAS {
        string proposta_id PK "Identificador da proposta de crédito"
        string empresa_id FK "Referência à empresa solicitante"
        datetime data_solicitacao "Data e hora do pedido"
        decimal valor_solicitado "Valor solicitado em BRL"
        integer prazo_meses "Prazo de amortização"
        float taxa_juros_mensal "Taxa de juros proposta ao mês"
        string finalidade "Destinação dos recursos"
        string status "APROVADA | ANALISE | RECUSADA"
    }

    GARANTIAS {
        string garantia_id PK "Identificador único da garantia"
        string proposta_id FK "Referência à proposta vinculada"
        string tipo_garantia "IMOVEL | VEICULO | AVAL | RECEBIVEIS"
        decimal valor_avaliado "Valor de laudo pericial"
        float percentual_cobertura "Cobertura percentual do empréstimo"
        string status_avaliacao "Situação do laudo"
    }

    OPERACOES {
        string operacao_id PK "Identificador único do contrato/CCB"
        string proposta_id FK,UK "Referência à proposta aprovada"
        string empresa_id FK "Referência à empresa contratante"
        string codigo_contrato UK "Código externo do contrato bancário"
        datetime data_contratacao "Data formal de emissão da cédula"
        decimal valor_contratado "Valor efetivamente liberado"
        decimal saldo_devedor "Saldo devedor atualizado em BRL"
        integer numero_parcelas "Total de parcelas"
        integer parcelas_pagas "Parcelas amortizadas"
        string status_operacao "Adimplente | Em Atraso | Liquidado"
    }

    EMPRESAS ||--o{ PROPOSTAS : "solicita"
    PROPOSTAS ||--o{ GARANTIAS : "vincula"
    PROPOSTAS ||--|| OPERACOES : "formaliza"
    EMPRESAS ||--o{ OPERACOES : "contrata"
```

---

## 🚀 Como Rodar o Simula-AI

### 1. Pré-Requisitos e Instalação Local

Certifique-se de ter Python 3.11+ e `uv` (ou `pip` padrão) instalados:

```bash
# 1. Clonar o repositório
git clone https://github.com/your-org/simula-ai.git
cd simula-ai

# 2. Criar ambiente virtual com uv
uv venv
source .venv/bin/activate

# 3. Instalar dependências completas
uv pip install -r requirements.txt
```

### 2. Configuração de Variáveis de Ambiente

Copie o template `.env.example` para `.env` e adicione sua chave do OpenRouter:

```bash
cp .env.example .env
```

Edite o `.env`:
```ini
# Chave da API OpenRouter (https://openrouter.ai/keys)
OPENROUTER_API_KEY=sk-or-v1-sua-chave-aqui

# Modelo Primário Hermes 3
OPENROUTER_MODEL=nousresearch/hermes-3-llama-3.1-405b

# Fallbacks automáticos em caso de HTTP 429 (Rate Limit)
OPENROUTER_FALLBACK_MODELS=nousresearch/hermes-3-llama-3.1-70b,qwen/qwen-2.5-coder-32b-instruct,deepseek/deepseek-chat

# Modo Offline / Test Double (true para testes locais sem gastar tokens)
SIMULA_MOCK_LLM=false
```

---

## 💻 Uso via CLI (Linha de Comando)

A interface de linha de comando (`cli/main.py`) fornece controle total do ciclo:

```bash
# Inspecionar esquema, tabelas e ordem topológica DAG:
python -m cli.main inspect contracts/exemplo_credito_mesh.yaml

# Gerar diagrama Mermaid ER e salvar em arquivo:
python -m cli.main diagram contracts/exemplo_credito_mesh.yaml -o output/mesh_er_diagram.mmd

# Executar o loop cognitivo com Hermes 3:
python -m cli.main run contracts/exemplo_credito_mesh.yaml --rows 50 --output-dir output

# Executar em modo offline (Mock rápido sem consumo de tokens):
python -m cli.main run contracts/exemplo_credito_mesh.yaml --mock --rows 20 --output-dir output

# Executar a suíte de validação gerada:
python -m cli.main test output/test_mock.py

# Exportar gerador e dados sintéticos diretamente:
python -m cli.main export contracts/exemplo_credito_mesh.yaml --rows 100 --format all
```

---

## 🌐 Uso via Web UI (Streamlit Dashboard)

O Simula-AI possui uma interface web moderna completa com abas para:
1. **Contrato de Dados:** Upload e edição de YAML com validação de regras em tempo real.
2. **Diagrama Mermaid ER:** Renderização interativa do grafo relacional via Mermaid.js CDN.
3. **Loop CoALA:** Execução ao vivo com inspeção da Memória Episódica (tracebacks de erros).
4. **Código & Testes:** Visualização do código `generator.py` e da suíte `test_mock.py`.
5. **Inspeção de Dados:** Tabelas paginadas para consulta dos dados gerados (CSV, JSON, Parquet).

Para iniciar:
```bash
python -m cli.main ui --port 8501
# Ou diretamente:
streamlit run ui/app.py
```
Acesse no navegador: **`http://localhost:8501`**.

---

## 🐳 Conteinerização com Podman

O Simula-AI foi projetado especificamente para execução segura e **rootless** via Podman (usuário não-root `simula` UID 10001).

### 1. Construir a Imagem Podman

```bash
podman build -t simula-ai -f Containerfile .
```

### 2. Rodar a Web UI no Podman

```bash
podman run --rm -it \
  -p 8501:8501 \
  --env-file .env \
  simula-ai ui
```
Acesse em: `http://localhost:8501`.

### 3. Rodar a CLI dentro do Container Podman

```bash
# Inspeção de contrato:
podman run --rm -it \
  --env-file .env \
  simula-ai cli inspect contracts/exemplo_credito_mesh.yaml

# Execução do loop com volume montado para persistir dados:
podman run --rm -it \
  -v $(pwd)/output:/app/output:Z \
  --env-file .env \
  simula-ai cli run contracts/exemplo_credito_mesh.yaml --mock --rows 50
```

---

## 🧪 Testes e Garantia de Qualidade

O framework possui cobertura completa de testes automatizados com **97 testes aprovados**:
- **57 Testes Unitários:** Estrutura CoALA, parser de contrato, validação de DAG (Kahn), detecção de ciclos, AST validator, regex de `<scratchpad>` / `<think>`, sandbox de subprocesso.
- **40 Testes End-to-End (Tiers 1 a 4):**
  - *Tier 1:* Verificação de esquemas, CLI Typer e Web UI.
  - *Tier 2:* Casos de borda (tags unclosed, timeout, zero rows, contratos malformados).
  - *Tier 3:* Integração por pares (CLI -> CoALA -> Exporter, Streamlit State Bridge).
  - *Tier 4:* Simulação de carga real do mesh de crédito brasileiro (unicidade de chaves primárias, 100% de integridade referencial de chaves estrangeiras, validação de formato de CNPJ e regras financeiras).

```bash
# Executar todos os testes:
uv run pytest tests/ -v

# Executar testes unitários:
uv run pytest tests/unit/ -v

# Executar testes E2E:
uv run pytest tests/e2e/ -v
```

---

## 🌳 Pipeline de CI em Árvore Granular (GitHub Actions)

O pipeline de Integração Contínua (`.github/workflows/ci.yml`) é estruturado em formato de **Árvore DAG Granular** com 10 etapas distribuídas em estágios interdependentes:

```mermaid
flowchart TD
    S0["00 • Lint, Sintaxe & Higiene<br/>compileall • ruff • yamllint"]

    S1A["01A • Unit: Contract Parser & DAG<br/>Kahn Sort • Pydantic v2"]
    S1B["01B • Unit: CoALA Loop & Sandbox<br/>State • Memória • Regex Hermes"]

    S2["02 • E2E: Tier 1 Features & Esquemas<br/>CLI App • Streamlit Layout • Exporter"]

    S3A["03A • E2E: Tier 2 Boundary Conditions<br/>Unclosed Tags • Timeout 30s • Malformed YAML"]
    S3B["03B • E2E: Tier 3 Pairwise Integration<br/>CLI ➔ CoALA ➔ Artifacts • State Bridge"]

    S4["04 • E2E: Tier 4 Workloads & Integridade<br/>Credit Mesh Simulation • Unicidade PK • 100% FK"]

    S5A["05A • CLI Smoke & Artifact Lifecycle<br/>inspect • diagram • run --mock • test"]
    S5B["05B • Container Build & Rootless<br/>Podman / Docker Build • Entrypoint Verification"]

    S6["06 • Quality Gate Certified<br/>Certificação e Liberação de Build"]

    S0 --> S1A
    S0 --> S1B

    S1A --> S2
    S1B --> S2

    S2 --> S3A
    S2 --> S3B

    S3A --> S4
    S3B --> S4

    S4 --> S5A
    S4 --> S5B

    S5A --> S6
    S5B --> S6

    style S0 fill:#1e293b,stroke:#94a3b8,color:#fff
    style S1A fill:#0f172a,stroke:#38bdf8,color:#fff
    style S1B fill:#0f172a,stroke:#f5af19,color:#fff
    style S2 fill:#161e31,stroke:#a855f7,color:#fff
    style S3A fill:#0f172a,stroke:#ec4899,color:#fff
    style S3B fill:#0f172a,stroke:#3b82f6,color:#fff
    style S4 fill:#064e3b,stroke:#10b981,color:#fff
    style S5A fill:#1e293b,stroke:#00d2ff,color:#fff
    style S5B fill:#1e293b,stroke:#892fe8,color:#fff
    style S6 fill:#047857,stroke:#34d399,stroke-width:2px,color:#fff
```

---

## 📁 Estrutura do Repositório

```
simula-ai/
├── assets/
│   └── hermes.webp                        # Imagem oficial do Hermes AI
├── docs/
│   ├── assets/
│   │   ├── hermes.webp
│   │   └── simula_data_mesh_architecture.svg # Diagrama vetorial oficial
│   └── simula_data_mesh_architecture.drawio   # Diagrama editável Draw.io
├── contracts/
│   └── exemplo_credito_mesh.yaml          # Contrato de crédito corporativo (4 tabelas)
├── core/
│   ├── __init__.py
│   ├── contract_parser.py                 # Validador Pydantic v2 & DAG de dependências
│   ├── state.py                           # Estado CoALA (SimulaState)
│   ├── memory.py                          # Memória procedimental, de trabalho e episódica
│   ├── llm_client.py                      # Cliente OpenRouter Hermes 3 com fallback resiliente
│   ├── code_parser.py                     # Extrator regex para <scratchpad>, <think> e AST
│   ├── sandbox.py                         # Sandbox seguro de execução Pytest com timeout
│   ├── graph.py                           # Orquestração do StateGraph no LangGraph
│   ├── diagram.py                         # Gerador híbrido de diagramas Mermaid ER
│   └── exporter.py                        # Exportador de generator.py, test_mock.py e datasets
├── cli/
│   ├── __init__.py
│   └── main.py                            # CLI interativa Typer / Rich
├── ui/
│   ├── __init__.py
│   ├── app.py                             # Interface Web Streamlit (5 abas)
│   └── bridge.py                          # Ponte reativa de estados para UI
├── tests/
│   ├── conftest.py
│   ├── unit/                              # 57 testes unitários
│   └── e2e/                               # 40 testes E2E (Tiers 1 a 4)
├── Containerfile                          # Especificação Podman Rootless
├── entrypoint.sh                          # Script de inicialização (UI/CLI)
├── pyproject.toml                         # Metadados do pacote Python
├── requirements.txt                       # Dependências do projeto
├── .env.example                           # Configurações de ambiente
└── README.md                              # Documentação oficial
```

---

## 📄 Licença

Distribuído sob a licença **Apache 2.0**.
