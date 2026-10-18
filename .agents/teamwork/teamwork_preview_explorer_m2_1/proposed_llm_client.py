"""core/llm_client.py - OpenRouter LLM Client with 429 Fallback & Mock Provider.

Implements:
1. OpenRouterClient: Connects to https://openrouter.ai/api/v1/chat/completions,
   implements exponential backoff with full jitter on HTTP 429 and transient 5xx errors,
   respects Retry-After headers, and cascades through fallback models:
   deepseek/deepseek-r1 -> deepseek/deepseek-chat -> deepseek/deepseek-r1-distill-llama-70b.
2. MockLLMClient: Deterministic offline test double activated by SIMULA_MOCK_LLM=true
   or mock_mode=True, supporting iterative retry testing (failing on iteration 1,
   fixing on iteration 2).
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Union

import httpx

try:
    from core.memory import format_episodic_feedback
    from core.state import EpisodicMemoryRecord, ProceduralMemory, WorkingMemory
except ImportError:
    from proposed_memory import format_episodic_feedback
    from proposed_state import EpisodicMemoryRecord, ProceduralMemory, WorkingMemory

logger = logging.getLogger("simula.llm_client")


class OpenRouterError(Exception):
    """Base exception for OpenRouter API interactions."""


class OpenRouterAuthError(OpenRouterError):
    """Authentication or authorization failure (HTTP 401/403). Non-retryable."""


class OpenRouterRateLimitError(OpenRouterError):
    """Rate limit exceeded across all models and retries (HTTP 429)."""


class OpenRouterAPIError(OpenRouterError):
    """General OpenRouter API error."""


DEFAULT_PRIMARY_MODEL = "deepseek/deepseek-r1"
DEFAULT_FALLBACK_MODELS = [
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1-distill-llama-70b",
]


class MockLLMClient:
    """Deterministic offline LLM test double for testing and CI/CD pipelines.

    Generates valid Python mock generators and Pytest test suites without network
    requests. Supports iterative failure simulation (failing on iteration 1, fixing
    on iteration 2) to test CoALA reflection and error recovery loops.
    """

    def __init__(
        self,
        fail_first_iteration: bool = False,
    ) -> None:
        env_fail = os.environ.get("SIMULA_MOCK_FAIL_FIRST", "").lower() in ("true", "1", "yes")
        self.fail_first_iteration = fail_first_iteration or env_fail
        self.call_count = 0

    def generate_candidate(
        self,
        procedural_memory: Optional[Union[ProceduralMemory, Dict[str, Any]]] = None,
        working_memory: Optional[Union[WorkingMemory, Dict[str, Any]]] = None,
        episodic_memory: Optional[List[EpisodicMemoryRecord]] = None,
        iteration: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generates deterministic Python candidate code enclosed in markdown fence."""
        self.call_count += 1
        episodic = episodic_memory or []

        # Check if we should simulate a failure on the first iteration
        should_fail = self.fail_first_iteration and (iteration == 1 or len(episodic) == 0)

        contract_yaml = ""
        if working_memory and isinstance(working_memory, dict):
            contract_yaml = working_memory.get("contract_yaml", "")

        is_credit_mesh = "empresas" in contract_yaml or "propostas" in contract_yaml

        if should_fail:
            return self._build_failing_code(is_credit_mesh=is_credit_mesh)
        return self._build_passing_code(is_credit_mesh=is_credit_mesh)

    def _build_failing_code(self, is_credit_mesh: bool = True) -> str:
        """Returns syntactically valid code with an intentional failing assertion."""
        return """```python
import random
import uuid
import pytest
from faker import Faker

fake = Faker(['pt_BR'])
Faker.seed(42)
random.seed(42)

def generate_mock_data(rows: int = 10):
    empresas = [
        {
            "empresa_id": str(uuid.uuid4()),
            "cnpj": fake.cnpj(),
            "razao_social": fake.company(),
            "faturamento_anual": round(random.uniform(500000.0, 5000000.0), 2),
            "status_cadastral": "ATIVO",
        }
        for _ in range(rows)
    ]
    propostas = [
        {
            "proposta_id": str(uuid.uuid4()),
            "empresa_id": random.choice(empresas)["empresa_id"],
            "valor_solicitado": round(random.uniform(10000.0, 100000.0), 2),
            "status_proposta": "ANALISE",
        }
        for _ in range(rows)
    ]
    return {"empresas": empresas, "propostas": propostas}

def test_empresas_count():
    data = generate_mock_data(5)
    assert len(data["empresas"]) == 5

def test_intentional_mock_failure():
    # Intentional failure for CoALA retry loop validation
    assert 1 == 2, "Intentional mock validation failure: proposals value check failed"
```"""

    def _build_passing_code(self, is_credit_mesh: bool = True) -> str:
        """Returns syntactically valid code with passing assertions."""
        return """```python
import random
import uuid
import re
from datetime import datetime, timedelta
import pytest
from faker import Faker

fake = Faker(['pt_BR'])
Faker.seed(42)
random.seed(42)

def generate_mock_data(rows: int = 20):
    # 1. Topological order: empresas (parent)
    empresas = []
    for _ in range(rows):
        empresas.append({
            "empresa_id": str(uuid.uuid4()),
            "cnpj": fake.cnpj(),
            "razao_social": fake.company(),
            "faturamento_anual": round(random.uniform(100000.0, 10000000.0), 2),
            "status_cadastral": random.choice(["ATIVO", "INATIVO", "SUSPENSO"]),
        })

    # 2. propostas (child of empresas)
    propostas = []
    base_date = datetime.now() - timedelta(days=60)
    for _ in range(rows):
        empresa = random.choice(empresas)
        dt_solicitacao = base_date + timedelta(days=random.randint(1, 30))
        propostas.append({
            "proposta_id": str(uuid.uuid4()),
            "empresa_id": empresa["empresa_id"],
            "data_solicitacao": dt_solicitacao.isoformat(),
            "valor_solicitado": round(random.uniform(20000.0, 250000.0), 2),
            "status_proposta": random.choice(["APROVADA", "ANALISE", "RECUSADA"]),
        })

    # 3. garantias (child of propostas)
    garantias = []
    for _ in range(rows):
        prop = random.choice(propostas)
        garantias.append({
            "garantia_id": str(uuid.uuid4()),
            "proposta_id": prop["proposta_id"],
            "tipo_garantia": random.choice(["IMOVEL", "VEICULO", "AVAL", "RECEBIVEIS"]),
            "valor_avaliado": round(random.uniform(30000.0, 500000.0), 2),
        })

    # 4. operacoes (child of propostas, approved only)
    operacoes = []
    aprovadas = [p for p in propostas if p["status_proposta"] == "APROVADA"]
    if not aprovadas:
        aprovadas = propostas[:max(1, len(propostas) // 2)]
        for p in aprovadas:
            p["status_proposta"] = "APROVADA"

    for prop in aprovadas:
        dt_sol = datetime.fromisoformat(prop["data_solicitacao"])
        dt_contratacao = dt_sol + timedelta(days=random.randint(1, 10))
        val_contratado = round(prop["valor_solicitado"] * random.uniform(0.5, 1.0), 2)
        operacoes.append({
            "operacao_id": str(uuid.uuid4()),
            "proposta_id": prop["proposta_id"],
            "data_contratacao": dt_contratacao.isoformat(),
            "valor_contratado": val_contratado,
        })

    return {
        "empresas": empresas,
        "propostas": propostas,
        "garantias": garantias,
        "operacoes": operacoes,
    }

# ==================== PYTEST VALIDATION SUITE ====================

def test_empresas_primary_key_uniqueness():
    data = generate_mock_data(10)
    pks = [e["empresa_id"] for e in data["empresas"]]
    assert len(pks) == len(set(pks)), "Empresas PK must be strictly unique"
    assert not any(x is None for x in pks), "Empresas PK cannot be None"

def test_empresas_cnpj_regex():
    data = generate_mock_data(10)
    cnpj_pattern = re.compile(r"^\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}$")
    for emp in data["empresas"]:
        assert cnpj_pattern.match(emp["cnpj"]), f"Invalid CNPJ: {emp['cnpj']}"

def test_propostas_fk_referential_integrity():
    data = generate_mock_data(10)
    empresa_pks = {e["empresa_id"] for e in data["empresas"]}
    for prop in data["propostas"]:
        assert prop["empresa_id"] in empresa_pks, "Proposta FK must exist in empresas"

def test_garantias_fk_referential_integrity():
    data = generate_mock_data(10)
    proposta_pks = {p["proposta_id"] for p in data["propostas"]}
    for gar in data["garantias"]:
        assert gar["proposta_id"] in proposta_pks, "Garantia FK must exist in propostas"

def test_operacoes_business_rules():
    data = generate_mock_data(10)
    prop_map = {p["proposta_id"]: p for p in data["propostas"]}
    for op in data["operacoes"]:
        assert op["proposta_id"] in prop_map
        parent_prop = prop_map[op["proposta_id"]]
        assert parent_prop["status_proposta"] == "APROVADA"
        assert op["valor_contratado"] <= parent_prop["valor_solicitado"]
```"""


class OpenRouterClient:
    """Client for querying OpenRouter chat completions with full 429 jitter & model fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        timeout: float = 120.0,
        max_retries_per_model: int = 3,
        base_delay: float = 2.0,
        max_backoff: float = 30.0,
        backoff_factor: float = 2.0,
        mock_mode: Optional[bool] = None,
        fail_first_iteration: bool = False,
    ) -> None:
        # Determine mock mode from parameter or environment
        if mock_mode is not None:
            self.mock_mode = mock_mode
        else:
            env_mock = os.environ.get("SIMULA_MOCK_LLM", "").lower()
            self.mock_mode = env_mock in ("true", "1", "yes")

        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        
        # Primary and fallback models
        self.primary_model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_PRIMARY_MODEL
        self.model = self.primary_model  # alias for test compatibility

        if fallback_models is not None:
            self.fallback_models = list(fallback_models)
        elif "OPENROUTER_FALLBACK_MODELS" in os.environ:
            self.fallback_models = [
                m.strip() for m in os.environ["OPENROUTER_FALLBACK_MODELS"].split(",") if m.strip()
            ]
        else:
            self.fallback_models = list(DEFAULT_FALLBACK_MODELS)

        self.timeout = float(os.environ.get("OPENROUTER_TIMEOUT", str(timeout)))
        self.max_retries_per_model = int(os.environ.get("OPENROUTER_MAX_RETRIES", str(max_retries_per_model)))
        self.base_delay = base_delay
        self.max_backoff = max_backoff
        self.backoff_factor = backoff_factor
        self.fail_first_iteration = fail_first_iteration

        self._mock_client = MockLLMClient(fail_first_iteration=self.fail_first_iteration)

    def generate_candidate(
        self,
        procedural_memory: Optional[Union[ProceduralMemory, Dict[str, Any]]] = None,
        working_memory: Optional[Union[WorkingMemory, Dict[str, Any]]] = None,
        episodic_memory: Optional[List[EpisodicMemoryRecord]] = None,
        iteration: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generates candidate Python code via Mock LLM or OpenRouter API."""
        if self.mock_mode:
            return self._mock_client.generate_candidate(
                procedural_memory=procedural_memory,
                working_memory=working_memory,
                episodic_memory=episodic_memory,
                iteration=iteration,
                **kwargs,
            )

        if not self.api_key:
            raise OpenRouterAuthError(
                "OPENROUTER_API_KEY is not set. Please export OPENROUTER_API_KEY or use SIMULA_MOCK_LLM=true."
            )

        messages = self._build_messages(
            procedural_memory=procedural_memory,
            working_memory=working_memory,
            episodic_memory=episodic_memory,
            iteration=iteration,
        )

        return self._call_openrouter_with_fallback(messages, **kwargs)

    def _build_messages(
        self,
        procedural_memory: Optional[Union[ProceduralMemory, Dict[str, Any]]],
        working_memory: Optional[Union[WorkingMemory, Dict[str, Any]]],
        episodic_memory: Optional[List[EpisodicMemoryRecord]],
        iteration: int,
    ) -> List[Dict[str, str]]:
        """Constructs system and user messages for chat completion."""
        system_prompt = ""
        if procedural_memory and isinstance(procedural_memory, dict):
            system_prompt = procedural_memory.get("system_prompt", "")
        if not system_prompt:
            from core.memory import SYSTEM_PROMPT
            system_prompt = SYSTEM_PROMPT

        messages = [{"role": "system", "content": system_prompt}]

        contract_yaml = ""
        if working_memory and isinstance(working_memory, dict):
            contract_yaml = working_memory.get("contract_yaml", "")

        user_content_parts = [
            f"# TASK SPECIFICATION: ITERATION {iteration}",
            "Generate a complete Python script implementing `generate_mock_data(rows=50)` and Pytest tests for the following Data Mesh contract:\n",
            "```yaml",
            contract_yaml,
            "```\n",
        ]

        if episodic_memory:
            feedback = format_episodic_feedback(episodic_memory)
            if feedback:
                user_content_parts.append(feedback)

        user_content_parts.append(
            "\nOutput ONLY the complete Python script enclosed in a single ```python ... ``` markdown code block."
        )

        messages.append({"role": "user", "content": "\n".join(user_content_parts)})
        return messages

    def _calculate_jitter_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """Calculates exponential backoff delay with full jitter and respects Retry-After."""
        computed_delay = min(self.max_backoff, self.base_delay * (self.backoff_factor ** attempt))
        # Full jitter: random uniform between 0.5 and computed_delay
        delay = random.uniform(0.5, max(0.5, computed_delay))
        if retry_after is not None and retry_after > 0:
            delay = max(delay, retry_after)
        return delay

    def _call_openrouter_with_fallback(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Executes API request with HTTP 429 jitter backoff and model fallback cascade."""
        models_to_try = [self.primary_model] + [
            m for m in self.fallback_models if m != self.primary_model
        ]

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://simula.ai",
            "X-Title": "Simula-AI Data Mocking Framework",
        }

        last_exception: Optional[Exception] = None

        with httpx.Client(timeout=self.timeout) as client:
            for model_name in models_to_try:
                logger.info(f"Attempting completion with model '{model_name}'...")

                for attempt in range(self.max_retries_per_model):
                    payload = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        **kwargs,
                    }

                    try:
                        resp = client.post(endpoint, headers=headers, json=payload)

                        if resp.status_code == 200:
                            data = resp.json()
                            choices = data.get("choices", [])
                            if not choices:
                                raise OpenRouterAPIError(f"OpenRouter response missing choices: {data}")
                            content = choices[0].get("message", {}).get("content", "")
                            if not content:
                                raise OpenRouterAPIError("OpenRouter choice contained empty message content")
                            return content

                        # Non-retryable auth errors
                        if resp.status_code in (401, 403):
                            err_msg = f"OpenRouter authentication failure ({resp.status_code}): {resp.text}"
                            logger.error(err_msg)
                            raise OpenRouterAuthError(err_msg)

                        # Retryable rate limits (429) and transient errors (502, 503, 504)
                        if resp.status_code in (429, 502, 503, 504):
                            retry_after: Optional[float] = None
                            if "retry-after" in resp.headers:
                                try:
                                    retry_after = float(resp.headers["retry-after"])
                                except (ValueError, TypeError):
                                    retry_after = None

                            delay = self._calculate_jitter_delay(attempt, retry_after)
                            logger.warning(
                                f"Model '{model_name}' returned HTTP {resp.status_code}. "
                                f"Backing off with full jitter for {delay:.2f}s (attempt {attempt + 1}/{self.max_retries_per_model})."
                            )
                            time.sleep(delay)
                            continue

                        # Other 4xx client errors
                        if 400 <= resp.status_code < 500:
                            err_msg = f"OpenRouter client error ({resp.status_code}): {resp.text}"
                            logger.error(err_msg)
                            raise OpenRouterAPIError(err_msg)

                        # Unhandled 5xx
                        delay = self._calculate_jitter_delay(attempt)
                        logger.warning(
                            f"Model '{model_name}' returned unexpected HTTP {resp.status_code}. Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)

                    except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                        delay = self._calculate_jitter_delay(attempt)
                        logger.warning(
                            f"Network error on model '{model_name}': {net_err}. Retrying in {delay:.2f}s..."
                        )
                        last_exception = net_err
                        time.sleep(delay)
                    except (OpenRouterAuthError, OpenRouterAPIError):
                        raise
                    except Exception as exc:
                        last_exception = exc
                        logger.warning(f"Unexpected error querying '{model_name}': {exc}")

                logger.warning(
                    f"Exhausted all {self.max_retries_per_model} retries for model '{model_name}'. "
                    "Cascading to next fallback model..."
                )

        error_detail = f" Last error: {last_exception}" if last_exception else ""
        raise OpenRouterRateLimitError(
            f"All models in fallback cascade ({models_to_try}) were exhausted without success.{error_detail}"
        )
