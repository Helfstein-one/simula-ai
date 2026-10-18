"""ui/app.py - Interactive Streamlit Web UI for Simula-AI."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.contract_parser import parse_contract
from core.diagram import generate_mermaid_er
from core.exporter import export_deliverables
from core.graph import run_simula_loop
from core.llm_client import DEFAULT_PRIMARY_MODEL, OpenRouterClient
from core.sandbox import PytestSandbox

st.set_page_config(
    page_title="Simula-AI | Relational Data Mocking",
    page_icon="⚡",
    layout="wide",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #00d2ff; margin-bottom: 0px; }
    .sub-header { font-size: 1.05rem; color: #8892b0; margin-bottom: 25px; }
    .status-badge { padding: 4px 12px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-header">⚡ Simula-AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Framework Autônomo de Mocking Relacional para Data Mesh | Padrão CoALA & Hermes AI</div>',
    unsafe_allow_html=True,
)

# Session state initialization
if "contract_yaml" not in st.session_state:
    sample_file = Path("contracts/exemplo_credito_mesh.yaml")
    if sample_file.exists():
        st.session_state.contract_yaml = sample_file.read_text(encoding="utf-8")
    else:
        st.session_state.contract_yaml = ""

if "final_state" not in st.session_state:
    st.session_state.final_state = None

if "artifacts" not in st.session_state:
    st.session_state.artifacts = None

# Sidebar Controls
with st.sidebar:
    st.header("⚙️ Configurações do Agente")
    model_choice = st.selectbox(
        "Modelo OpenRouter",
        options=[
            "nousresearch/hermes-3-llama-3.1-405b",
            "nousresearch/hermes-3-llama-3.1-70b",
            "qwen/qwen-2.5-coder-32b-instruct",
            "deepseek/deepseek-chat",
            "deepseek/deepseek-r1",
        ],
        index=0,
        help="Hermes 3 como primário com fallback automático.",
    )

    mock_mode = st.checkbox("Modo Offline / Test Double (Mock)", value=False)
    max_iterations = st.slider("Máximo de Iterações (CoALA Loop)", min_value=1, max_value=8, value=3)
    row_count = st.slider("Linhas por Tabela", min_value=5, max_value=500, value=25)

    st.divider()
    st.caption("Podman Container Ready | LangGraph + Streamlit")

# Tabs
tab_contract, tab_diagram, tab_loop, tab_code, tab_data = st.tabs([
    "📄 Contrato de Dados",
    "📊 Diagrama Mermaid ER",
    "🧠 Loop CoALA",
    "💻 Código & Testes",
    "🔍 Datasets Gerados",
])

# Tab 1: Contract
with tab_contract:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Editor de Contrato YAML")
        uploaded_file = st.file_uploader("Carregar Contrato YAML", type=["yaml", "yml"])
        if uploaded_file is not None:
            st.session_state.contract_yaml = uploaded_file.read().decode("utf-8")

        contract_text = st.text_area(
            "Conteúdo YAML",
            value=st.session_state.contract_yaml,
            height=450,
        )
        st.session_state.contract_yaml = contract_text

    with col2:
        st.subheader("Validação de Esquema & DAG Relacional")
        if st.session_state.contract_yaml.strip():
            try:
                contract = parse_contract(st.session_state.contract_yaml)
                st.success(f"✓ Contrato válido: **{contract.name}** (v{contract.version})")
                dag_order = contract.topological_sort()
                st.info(f"**Ordem Topológica (DAG):** {' ➔ '.join(dag_order)}")

                summary_data = []
                for t in contract.tables:
                    fks = [f"{fk.field} -> {fk.references_table}.{fk.references_field}" for fk in getattr(t, "foreign_keys", [])]
                    summary_data.append({
                        "Tabela": t.name,
                        "Colunas": len(t.fields),
                        "PK": t.primary_key or "N/A",
                        "FKs": ", ".join(fks) or "Nenhuma",
                    })
                st.dataframe(pd.DataFrame(summary_data), use_container_width=True)
            except Exception as e:
                st.error(f"Erro ao validar contrato: {e}")

# Tab 2: Diagram
with tab_diagram:
    st.subheader("Diagrama Entidade-Relacionamento (Mermaid ER)")
    if st.session_state.contract_yaml.strip():
        try:
            contract = parse_contract(st.session_state.contract_yaml)
            mmd = generate_mermaid_er(contract)

            # Render Mermaid using HTML/JS
            html_code = f"""
            <div class="mermaid" style="background-color: #0e1117; padding: 20px; border-radius: 8px;">
            {mmd}
            </div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
            </script>
            """
            components.html(html_code, height=500, scrolling=True)

            with st.expander("Ver Código Mermaid (.mmd)"):
                st.code(mmd, language="mermaid")
        except Exception as e:
            st.error(f"Falha ao gerar diagrama: {e}")

# Tab 3: CoALA Loop
with tab_loop:
    st.subheader("Execução da Arquitetura Cognitiva CoALA")
    start_btn = st.button("🚀 Iniciar Ciclo de Síntese e Validação", type="primary")

    if start_btn:
        if not st.session_state.contract_yaml.strip():
            st.warning("Insira um contrato de dados válido antes de iniciar.")
        else:
            with st.spinner("Agente executando loop cognitivo CoALA..."):
                try:
                    parsed_contract = parse_contract(st.session_state.contract_yaml)
                    client = OpenRouterClient(
                        model=model_choice,
                        mock_mode=mock_mode,
                    )
                    sandbox = PytestSandbox(timeout_seconds=30)

                    final_state = run_simula_loop(
                        contract_path=st.session_state.contract_yaml,
                        client=client,
                        sandbox=sandbox,
                        max_iterations=max_iterations,
                    )
                    st.session_state.final_state = final_state

                    if final_state.get("status") == "SUCCESS":
                        out_dir = Path("output")
                        out_dir.mkdir(parents=True, exist_ok=True)
                        artifacts = export_deliverables(
                            generated_code=final_state.get("working_memory", {}).get("generated_code", ""),
                            output_dir=out_dir,
                            contract=parsed_contract,
                            generate_datasets=True,
                            rows=row_count,
                            formats=["csv", "json", "parquet"],
                        )
                        st.session_state.artifacts = artifacts
                        st.success("✓ Loop concluído com sucesso!")
                    else:
                        st.error(f"Loop finalizado com status: {final_state.get('status')}")
                except Exception as e:
                    st.error(f"Erro na execução: {e}")

    if st.session_state.final_state:
        state = st.session_state.final_state
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Status Final", state.get("status", "N/A"))
        m_col2.metric("Iterações Executadas", state.get("iterations", 0))
        m_col3.metric("Falhas em Memória Episódica", len(state.get("episodic_memory", [])))

        st.markdown("#### Memória Episódica (Histórico de Correções e Tracebacks)")
        episodic = state.get("episodic_memory", [])
        if episodic:
            for idx, item in enumerate(episodic):
                with st.expander(f"Iteração #{item.get('iteration', idx + 1)} - Erro Detectado"):
                    st.text(item.get("error_summary", ""))
                    st.code(item.get("traceback", "") or item.get("stdout", ""), language="text")
        else:
            st.info("Nenhuma falha registrada. Código aprovado na primeira iteração.")

# Tab 4: Code & Tests
with tab_code:
    st.subheader("Artefatos de Código Gerados")
    gen_file = Path("output/generator.py")
    test_file = Path("output/test_mock.py")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**output/generator.py (Gerador Autônomo Faker)**")
        if gen_file.exists():
            st.code(gen_file.read_text(encoding="utf-8"), language="python")
        else:
            st.info("Execute o loop para visualizar o gerador.")
    with c2:
        st.markdown("**output/test_mock.py (Suíte de Validação Pytest)**")
        if test_file.exists():
            st.code(test_file.read_text(encoding="utf-8"), language="python")
        else:
            st.info("Execute o loop para visualizar os testes.")

# Tab 5: Data Inspection
with tab_data:
    st.subheader("Inspeção dos Datasets Sintéticos Gerados")
    csv_dir = Path("output/datasets/csv")
    if csv_dir.exists():
        csv_files = list(csv_dir.glob("*.csv"))
        if csv_files:
            table_select = st.selectbox("Selecione a Tabela do Mesh", [f.stem for f in csv_files])
            selected_csv = csv_dir / f"{table_select}.csv"
            df = pd.read_csv(selected_csv)
            st.dataframe(df, use_container_width=True)
            st.caption(f"Exibindo {len(df)} registros gerados para {table_select}")
        else:
            st.info("Nenhum arquivo CSV gerado ainda.")
    else:
        st.info("Nenhum dataset gerado. Execute o loop na aba 'Loop CoALA'.")
