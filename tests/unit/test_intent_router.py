from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.intent_router import (
    INTENT_ROUTER_SYSTEM_PROMPT,
    IntentRoute,
    classify_intent,
)
from astrbot.core.local_evidence import (
    LorebookEntry,
    activate_lorebook,
    build_local_evidence_prompt,
    build_runtime_config_evidence,
    load_lorebook,
)
from astrbot.core.provider.entities import LLMResponse


@pytest.mark.asyncio
async def test_llm_router_classifies_local_knowledge_message_without_chat_history():
    """The isolated router must use structured model output, not lexical rules."""
    provider = MagicMock()
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(
            role="assistant",
            completion_text='{"route":"local_knowledge","confidence":0.97}',
        )
    )

    decision = await classify_intent(
        provider,
        "这个知识库是否使用 BM25 的向量检索？",
    )

    assert decision.route is IntentRoute.LOCAL_KNOWLEDGE
    assert decision.confidence == 0.97
    provider.text_chat.assert_awaited_once()
    kwargs = provider.text_chat.await_args.kwargs
    assert kwargs["contexts"] is None
    assert kwargs["func_tool"] is None
    assert kwargs["request_max_retries"] == 1
    assert "JSON" in kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_llm_router_separates_runtime_state_from_local_documents():
    provider = MagicMock()
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(
            role="assistant",
            completion_text='{"route":"local_runtime","confidence":0.98}',
        )
    )

    decision = await classify_intent(provider, "当前 AstrBot 容器是否在线？")

    assert decision.route is IntentRoute.LOCAL_RUNTIME


@pytest.mark.asyncio
async def test_llm_router_falls_back_without_lexical_guess_on_provider_error():
    provider = MagicMock()
    provider.text_chat = AsyncMock(side_effect=RuntimeError("provider unavailable"))

    decision = await classify_intent(provider, "请介绍一下你自己")

    assert decision.route is IntentRoute.EXTERNAL_FACT
    assert decision.confidence == 0.0
    assert decision.is_fallback is True


@pytest.mark.asyncio
async def test_llm_router_rejects_structured_output_with_extra_fields():
    provider = MagicMock()
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(
            role="assistant",
            completion_text=(
                '{"route":"chat_creative","confidence":0.99,"answer":"hi"}'
            ),
        )
    )

    decision = await classify_intent(provider, "你好")

    assert decision.route is IntentRoute.EXTERNAL_FACT
    assert decision.is_fallback is True


@pytest.mark.asyncio
async def test_empty_message_routes_to_chat_without_calling_provider():
    provider = MagicMock()
    provider.text_chat = AsyncMock()

    decision = await classify_intent(provider, "   ")

    assert decision.route is IntentRoute.CHAT_CREATIVE
    assert decision.confidence == 1.0
    assert decision.is_fallback is False
    provider.text_chat.assert_not_awaited()


def test_router_prompt_separates_assistant_identity_from_local_deployment():
    """Identity small-talk must not share the local-deployment evidence route."""
    prompt = INTENT_ROUTER_SYSTEM_PROMPT.lower()

    assert "assistant identity" in prompt
    assert "current deployment" in prompt
    assert "semantic meaning" in prompt
    assert '"你是谁"' in INTENT_ROUTER_SYSTEM_PROMPT


def test_lorebook_activates_only_matching_entries_from_user_messages():
    entries = (
        LorebookEntry(
            entry_id="bm25",
            aliases=("BM25", "倒排索引"),
            source_type="local_rag",
            content="当前知识库检索包含稀疏 BM25、稠密向量检索和 RRF 融合。",
        ),
        LorebookEntry(
            entry_id="deployment",
            aliases=("NapCat", "容器"),
            source_type="local_config",
            content="AstrBot 与 NapCat 通过 Docker 网络通信。",
        ),
    )

    active = activate_lorebook(
        entries,
        ["我想确认这个知识库是否真的使用 BM25？"],
    )

    assert [entry.entry_id for entry in active] == ["bm25"]
    assert active[0].source_type == "local_rag"


def test_lorebook_never_exceeds_content_budget_even_for_first_match():
    entry = LorebookEntry(
        entry_id="oversized",
        aliases=("BM25",),
        source_type="local_rag",
        content="证" * 1001,
    )

    active = activate_lorebook(
        [entry],
        ["BM25"],
        max_content_chars=1000,
    )

    assert active == []


def test_lorebook_enforces_cumulative_budget_and_entry_limit():
    entries = tuple(
        LorebookEntry(
            entry_id=f"entry-{index}",
            aliases=("共同别名",),
            source_type="local_rag",
            content=str(index) * 300,
        )
        for index in range(6)
    )

    active = activate_lorebook(
        entries,
        ["共同别名"],
        max_entries=4,
        max_content_chars=1000,
    )

    assert [entry.entry_id for entry in active] == [
        "entry-0",
        "entry-1",
        "entry-2",
    ]
    assert sum(len(entry.content) for entry in active) == 900


def test_lorebook_does_not_recursively_activate_from_entry_content():
    entries = (
        LorebookEntry(
            entry_id="bm25",
            aliases=("BM25",),
            source_type="local_rag",
            content="BM25 与 NapCat 无关；这里出现 NapCat 不能触发下一条。",
        ),
        LorebookEntry(
            entry_id="deployment",
            aliases=("NapCat",),
            source_type="local_config",
            content="部署证据。",
        ),
    )

    active = activate_lorebook(entries, ["请解释 BM25"])

    assert [entry.entry_id for entry in active] == ["bm25"]


def test_deployment_lorebook_handles_chinese_topology_paraphrase():
    lorebook_path = Path(__file__).parents[2] / "data" / "intent_lorebook.json"
    entries = load_lorebook(lorebook_path)

    active = activate_lorebook(
        entries,
        ["这台机器上实际跑着的问答服务，当前由哪些组件串起来？"],
    )

    assert "deployment" in [entry.entry_id for entry in active]


def test_local_evidence_prompt_contains_content_and_provenance_not_aliases():
    entry = LorebookEntry(
        entry_id="bm25",
        aliases=("hidden-alias",),
        source_type="local_rag",
        content="当前知识库使用 BM25 稀疏检索和稠密向量检索进行融合。",
    )

    prompt = build_local_evidence_prompt([entry])

    assert "local_rag" in prompt
    assert "当前知识库使用 BM25" in prompt
    assert "hidden-alias" not in prompt


def test_runtime_config_evidence_contains_only_safe_current_settings():
    evidence = build_runtime_config_evidence(
        {
            "web_search": True,
            "websearch_provider": "exa",
            "verified_factual_reply_policy": True,
            "intent_router_enabled": True,
            "websearch_exa_key": ["must-not-leak"],
        }
    )

    assert 'source_type="local_config"' in evidence
    assert '"web_search_enabled": true' in evidence
    assert '"web_search_provider": "exa"' in evidence
    assert '"intent_router_enabled": true' in evidence
    assert "must-not-leak" not in evidence
    assert "websearch_exa_key" not in evidence


def test_load_lorebook_skips_invalid_entries(tmp_path):
    path = tmp_path / "intent_lorebook.json"
    path.write_text(
        """{
          "entries": [
            {
              "id": "bm25",
              "aliases": ["BM25"],
              "source_type": "local_rag",
              "content": "本地混合检索证据。"
            },
            {
              "id": "invalid-source",
              "aliases": ["ignored"],
              "source_type": "web_trusted",
              "content": "must not be loaded"
            }
          ]
        }""",
        encoding="utf-8",
    )

    entries = load_lorebook(path)

    assert [entry.entry_id for entry in entries] == ["bm25"]
