"""scripts/generate_diagram_screenshot.py

Renders the Simula-AI Data Mesh architecture diagram with official icons and the Hermes avatar,
and captures a high-resolution screenshot using headless Google Chrome.
"""

import base64
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERMES_PNG = ROOT / "assets" / "hermes.png"
OUTPUT_PNG = ROOT / "docs" / "assets" / "simula_data_mesh_architecture.png"
OUTPUT_HTML = ROOT / "docs" / "assets" / "_diagram_render.html"

# Encode Hermes PNG
hermes_b64 = base64.b64encode(HERMES_PNG.read_bytes()).decode("utf-8")
hermes_src = f"data:image/png;base64,{hermes_b64}"

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Simula-AI Architecture</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #070b14;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: #f1f5f9;
      padding: 30px;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }}
    .diagram-container {{
      width: 1340px;
      background: #0c1222;
      border: 2px solid #892fe8;
      border-radius: 20px;
      padding: 24px 30px;
      position: relative;
      box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.7), 0 0 40px rgba(137, 47, 232, 0.15);
    }}
    .podman-badge {{
      position: absolute;
      top: -14px;
      left: 40px;
      background: linear-gradient(135deg, #892fe8, #4e1b87);
      color: #ffffff;
      padding: 4px 16px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 1px;
      display: flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 4px 12px rgba(137, 47, 232, 0.4);
    }}
    .header-bar {{
      text-align: center;
      margin-bottom: 24px;
    }}
    .header-bar h1 {{
      font-size: 26px;
      font-weight: 800;
      letter-spacing: 0.5px;
      background: linear-gradient(90deg, #00d2ff, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .header-bar p {{
      color: #94a3b8;
      font-size: 13px;
      margin-top: 4px;
    }}
    .main-grid {{
      display: grid;
      grid-template-columns: 280px 1fr 310px;
      gap: 24px;
    }}
    .card {{
      background: #111a2e;
      border: 1px solid #1e293b;
      border-radius: 14px;
      padding: 18px;
    }}
    .card-title {{
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid #1e293b;
    }}
    .list-item {{
      background: #0c1425;
      border: 1px solid #1e2c45;
      padding: 9px 12px;
      border-radius: 8px;
      font-size: 11.5px;
      margin-bottom: 8px;
      color: #cbd5e1;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .list-item strong {{ color: #38bdf8; }}
    
    /* Center Column: CoALA Engine */
    .coala-box {{
      background: #0f172a;
      border: 2px solid #00d2ff;
      border-radius: 16px;
      padding: 18px;
      box-shadow: 0 0 30px rgba(0, 210, 255, 0.1);
    }}
    .hermes-hero {{
      background: linear-gradient(135deg, #162038, #0e1629);
      border: 1.5px solid #f5af19;
      border-radius: 14px;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 16px;
      box-shadow: 0 8px 20px rgba(245, 175, 25, 0.15);
    }}
    .hermes-avatar {{
      width: 72px;
      height: 72px;
      border-radius: 50%;
      border: 3px solid #f5af19;
      box-shadow: 0 0 15px rgba(245, 175, 25, 0.4);
      object-fit: cover;
    }}
    .hermes-info h2 {{
      font-size: 17px;
      font-weight: 800;
      color: #ffffff;
    }}
    .hermes-info .model-tag {{
      display: inline-block;
      background: rgba(245, 175, 25, 0.15);
      color: #fbbf24;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      margin: 4px 0;
      border: 1px solid rgba(245, 175, 25, 0.3);
    }}
    .hermes-info p {{
      font-size: 11px;
      color: #94a3b8;
    }}

    .memory-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      margin-bottom: 16px;
    }}
    .mem-card {{
      background: #131c33;
      border-radius: 10px;
      padding: 12px;
      font-size: 11px;
    }}
    .mem-card.wm {{ border: 1px solid #3b82f6; }}
    .mem-card.em {{ border: 1px solid #ec4899; }}
    .mem-title {{ font-weight: 700; margin-bottom: 6px; font-size: 12px; }}
    .wm .mem-title {{ color: #60a5fa; }}
    .em .mem-title {{ color: #f472b6; }}
    .mem-list {{ list-style: none; color: #94a3b8; line-height: 1.6; }}
    .mem-list li::before {{ content: "• "; color: #64748b; }}

    /* Sandbox */
    .sandbox-box {{
      background: #091120;
      border: 1.5px solid #10b981;
      border-radius: 12px;
      padding: 14px;
      position: relative;
    }}
    .sandbox-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }}
    .sandbox-title {{
      color: #34d399;
      font-weight: 700;
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .badge-green {{
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      font-size: 10.5px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
    }}
    .sandbox-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      font-size: 11px;
      color: #cbd5e1;
    }}
    .sandbox-item {{
      background: #0f192c;
      padding: 8px 10px;
      border-radius: 6px;
      border-left: 3px solid #10b981;
    }}
    .sandbox-item.err {{
      border-left-color: #f43f5e;
    }}

    /* Right column: Deliverables */
    .table-badge {{
      background: #0b1528;
      border: 1px solid #1e3a5f;
      padding: 8px 10px;
      border-radius: 8px;
      margin-bottom: 8px;
      font-size: 11.5px;
    }}
    .table-badge .tname {{ color: #34d399; font-weight: 700; }}
    .table-badge .tfields {{ color: #64748b; font-size: 10px; margin-top: 2px; }}

    .format-pill {{
      display: inline-block;
      background: #1e293b;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      color: #38bdf8;
      margin-right: 4px;
    }}

    /* Bottom Interfaces */
    .bottom-bar {{
      margin-top: 18px;
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 12px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .interface-pill {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .interface-pill .icon-box {{
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
    }}
    .cli-box {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; }}
    .ui-box {{ background: rgba(236, 72, 153, 0.15); color: #ec4899; }}
    .podman-box {{ background: rgba(137, 47, 232, 0.15); color: #a855f7; }}
  </style>
</head>
<body>

  <div class="diagram-container">
    <div class="podman-badge">
      <span>🐳</span> PODMAN ROOTLESS CONTAINER • UID 10001 (simula)
    </div>

    <div class="header-bar">
      <h1>SIMULA-AI : DATA MESH RELATIONAL MOCK ARCHITECTURE</h1>
      <p>CoALA Cognitive Agent Loop • Hermes 3 AI Engine • Subprocess Pytest Sandbox • Topological DAG Ingestion</p>
    </div>

    <div class="main-grid">
      <!-- 1. Left: Data Contract -->
      <div>
        <div class="card" style="border-color: #38bdf8;">
          <div class="card-title" style="color: #38bdf8;">
            <span>📄</span> 1. Data Contract (YAML)
          </div>
          <div class="list-item">
            <span>📐</span> <div><strong>Multi-Table Schemas:</strong> Pydantic v2 validation</div>
          </div>
          <div class="list-item">
            <span>🔑</span> <div><strong>Referential Keys:</strong> PKs, FKs &amp; Unique constraints</div>
          </div>
          <div class="list-item">
            <span>📊</span> <div><strong>Business Rules:</strong> Financial bounds &amp; logic</div>
          </div>
          <div class="list-item">
            <span>🔄</span> <div><strong>Kahn's Sort:</strong> Cycle-free topological DAG</div>
          </div>
        </div>

        <div class="card" style="margin-top: 16px; border-color: #a855f7;">
          <div class="card-title" style="color: #c084fc;">
            <span>📊</span> Hybrid Mermaid ER
          </div>
          <div class="list-item">
            <span>⚡</span> <div><strong>Deterministic:</strong> Table &amp; type sanitization</div>
          </div>
          <div class="list-item">
            <span>🔗</span> <div><strong>Cardinalities:</strong> ||--o{{, ||--|| relations</div>
          </div>
          <div class="list-item">
            <span>📝</span> <div><strong>mesh_er_diagram.mmd:</strong> Direct export</div>
          </div>
        </div>
      </div>

      <!-- 2. Center: CoALA LangGraph Engine -->
      <div class="coala-box">
        <div class="hermes-hero">
          <img src="{hermes_src}" alt="Hermes AI" class="hermes-avatar" />
          <div class="hermes-info">
            <h2>Hermes 3 AI (Nous Research)</h2>
            <div class="model-tag">nousresearch/hermes-3-llama-3.1-405b / 70b</div>
            <p>High-fidelity synthetic data generation with automatic fallback to Qwen 2.5 Coder &amp; DeepSeek.</p>
          </div>
        </div>

        <div class="memory-row">
          <div class="mem-card wm">
            <div class="mem-title">🧠 Working Memory</div>
            <ul class="mem-list">
              <li>Active Contract YAML schema</li>
              <li>Generated candidate Python code</li>
              <li>Active Pytest stdout / stderr</li>
              <li>Iteration Counter: N / Max</li>
            </ul>
          </div>
          <div class="mem-card em">
            <div class="mem-title">📜 Episodic Memory</div>
            <ul class="mem-list">
              <li>Iterative failure traceback cache</li>
              <li>Discrepancy &amp; constraint map</li>
              <li>Regex strip &lt;scratchpad&gt; &amp; &lt;think&gt;</li>
              <li>Self-correction reflection loop</li>
            </ul>
          </div>
        </div>

        <div class="sandbox-box">
          <div class="sandbox-header">
            <div class="sandbox-title">
              <span>🛡️</span> Subprocess Pytest Sandbox (Zero eval)
            </div>
            <div class="badge-green">Strict 30s Timeout</div>
          </div>
          <div class="sandbox-grid">
            <div class="sandbox-item">
              <strong style="color: #34d399;">✓ Exit Code 0:</strong> Complete success! Routes to final deliverables export.
            </div>
            <div class="sandbox-item err">
              <strong style="color: #f43f5e;">✗ Exit Code 1 / 2:</strong> Captures traceback &amp; feeds back to Episodic Memory.
            </div>
          </div>
        </div>
      </div>

      <!-- 3. Right: Data Mesh Deliverables -->
      <div>
        <div class="card" style="border-color: #10b981;">
          <div class="card-title" style="color: #34d399;">
            <span>📦</span> 3. Relational Mesh Tables
          </div>

          <div class="table-badge">
            <div class="tname">1. empresas (Parent)</div>
            <div class="tfields">empresa_id (PK), cnpj (UK), faturamento, score</div>
          </div>
          <div class="table-badge">
            <div class="tname">2. propostas (Child)</div>
            <div class="tfields">proposta_id (PK), empresa_id (FK), valor_solicitado</div>
          </div>
          <div class="table-badge">
            <div class="tname">3. garantias (Child)</div>
            <div class="tfields">garantia_id (PK), proposta_id (FK), valor_estimado</div>
          </div>
          <div class="table-badge">
            <div class="tname">4. operacoes (Child)</div>
            <div class="tfields">operacao_id (PK), proposta_id (FK), valor_contratado</div>
          </div>

          <div style="margin-top: 14px; padding-top: 10px; border-top: 1px solid #1e293b;">
            <div style="font-size: 11px; font-weight: 700; color: #94a3b8; margin-bottom: 6px;">EXPORTED FORMATS:</div>
            <span class="format-pill">CSV</span>
            <span class="format-pill">JSON</span>
            <span class="format-pill">PARQUET</span>
          </div>

          <div style="margin-top: 12px; font-size: 11px; color: #cbd5e1;">
            <div>• <code>generator.py</code> (Standalone Faker)</div>
            <div>• <code>test_mock.py</code> (Pytest Suite)</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Bar: Dual Interface & Container Runtime -->
    <div class="bottom-bar">
      <div class="interface-pill">
        <div class="icon-box cli-box">💻</div>
        <div>
          <div style="font-size: 12px; font-weight: 700; color: #38bdf8;">Rich CLI (Typer)</div>
          <div style="font-size: 10.5px; color: #94a3b8;">simula run | inspect | diagram | test</div>
        </div>
      </div>

      <div class="interface-pill">
        <div class="icon-box ui-box">🌐</div>
        <div>
          <div style="font-size: 12px; font-weight: 700; color: #ec4899;">Streamlit Web UI</div>
          <div style="font-size: 10.5px; color: #94a3b8;">Interactive Mermaid ER &amp; Data Inspector (Port 8501)</div>
        </div>
      </div>

      <div class="interface-pill">
        <div class="icon-box podman-box">🐳</div>
        <div>
          <div style="font-size: 12px; font-weight: 700; color: #a855f7;">Podman Rootless</div>
          <div style="font-size: 10.5px; color: #94a3b8;">Containerfile &amp; entrypoint.sh (No Root Required)</div>
        </div>
      </div>
    </div>
  </div>

</body>
</html>
"""

OUTPUT_HTML.write_text(html_content, encoding="utf-8")
print(f"HTML diagram written to {OUTPUT_HTML}")

# Take screenshot with Chrome
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
cmd = [
    chrome_path,
    "--headless",
    "--disable-gpu",
    "--hide-scrollbars",
    "--window-size=1420,890",
    f"--screenshot={OUTPUT_PNG}",
    str(OUTPUT_HTML),
]

res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print(f"✓ High-resolution screenshot captured to {OUTPUT_PNG}")
else:
    print(f"✗ Failed to capture screenshot: {res.stderr}")
