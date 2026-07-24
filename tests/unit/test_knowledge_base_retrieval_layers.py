from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.core.tools.knowledge_base_tools import (
    resolve_kb_final_top_k,
    retrieve_knowledge_base,
    select_authorized_knowledge_bases,
)

HISTORY_CPU_KB = "历史 CPU 型号与平台资料库"


def test_history_cpu_retrieval_depth_tracks_the_requested_layer() -> None:
    assert resolve_kb_final_top_k("罗马架构性能如何？", [HISTORY_CPU_KB], 5) == 5
    assert (
        resolve_kb_final_top_k(
            "能给一个 EPYC 7002 的具体实测例子吗？",
            [HISTORY_CPU_KB],
            5,
        )
        == 8
    )
    assert (
        resolve_kb_final_top_k(
            "详细介绍 3970X 的 NUMA 和完整测试报告。",
            [HISTORY_CPU_KB],
            5,
        )
        == 15
    )


def test_history_cpu_retrieval_depth_preserves_explicitly_larger_limits() -> None:
    assert (
        resolve_kb_final_top_k(
            "给一个具体例子",
            [HISTORY_CPU_KB],
            12,
        )
        == 12
    )
    assert (
        resolve_kb_final_top_k(
            "详细介绍",
            [HISTORY_CPU_KB],
            20,
        )
        == 20
    )


def test_other_knowledge_bases_keep_their_configured_limit() -> None:
    assert resolve_kb_final_top_k("详细介绍", ["项目文档"], 5) == 5


@pytest.mark.asyncio
async def test_semantic_selector_only_receives_session_authorized_knowledge_bases():
    first = MagicMock()
    first.kb = SimpleNamespace(
        kb_id="allowed",
        kb_name="AI Infra",
        description="CPU and accelerator deployment notes",
    )
    first.list_documents = AsyncMock(
        return_value=[SimpleNamespace(doc_name="Xeon Max 9470C.md")]
    )
    kb_mgr = MagicMock()
    kb_mgr.get_kb = AsyncMock(return_value=first)
    context = MagicMock()
    context.kb_manager = kb_mgr
    provider = MagicMock(spec=EmbeddingProvider)
    context.get_provider_by_id.return_value = provider
    selected = SimpleNamespace(candidate=SimpleNamespace(kb_name="AI Infra"))

    with (
        patch(
            "astrbot.core.tools.knowledge_base_tools.sp.session_get",
            AsyncMock(return_value={"kb_ids": ["allowed"], "top_k": 5}),
        ),
        patch(
            "astrbot.core.tools.knowledge_base_tools.select_knowledge_bases",
            AsyncMock(return_value=[selected]),
        ) as select,
    ):
        names = await select_authorized_knowledge_bases(
            query="9470C 的 HBM 有多大？",
            umo="qq:group:1",
            context=context,
        )

    assert names == ["AI Infra"]
    candidates = select.await_args.args[1]
    assert [item.kb_id for item in candidates] == ["allowed"]
    assert "Xeon Max 9470C" in candidates[0].prototypes
    assert select.await_args.kwargs == {"min_similarity": 0.52, "max_bases": 2}


@pytest.mark.asyncio
async def test_semantic_selector_failure_returns_empty_without_widening_scope():
    helper = MagicMock()
    helper.kb = SimpleNamespace(
        kb_id="allowed",
        kb_name="Docs",
        description=None,
    )
    helper.list_documents = AsyncMock(return_value=[])
    context = MagicMock()
    context.kb_manager.get_kb = AsyncMock(return_value=helper)
    context.get_provider_by_id.return_value = MagicMock(spec=EmbeddingProvider)

    with (
        patch(
            "astrbot.core.tools.knowledge_base_tools.sp.session_get",
            AsyncMock(return_value={"kb_ids": ["allowed"]}),
        ),
        patch(
            "astrbot.core.tools.knowledge_base_tools.select_knowledge_bases",
            AsyncMock(side_effect=RuntimeError("embedding offline")),
        ),
    ):
        names = await select_authorized_knowledge_bases(
            query="question",
            umo="qq:group:1",
            context=context,
        )

    assert names == []


@pytest.mark.asyncio
async def test_explicit_semantic_selection_caps_final_chunks_at_three():
    helper = MagicMock()
    helper.kb = SimpleNamespace(doc_count=1, chunk_count=4)
    context = MagicMock()
    context.get_config.return_value = {
        "kb_final_top_k": 8,
        "kb_fusion_top_k": 20,
    }
    context.kb_manager.get_kb_by_name = AsyncMock(return_value=helper)
    context.kb_manager.retrieve = AsyncMock(
        return_value={"context_text": "selected evidence", "results": [1, 2, 3]}
    )

    with patch(
        "astrbot.core.tools.knowledge_base_tools.sp.session_get",
        AsyncMock(return_value={}),
    ):
        result = await retrieve_knowledge_base(
            query="question",
            umo="qq:group:1",
            context=context,
            kb_names=["AI Infra"],
            max_results=3,
        )

    assert result == "selected evidence"
    context.kb_manager.retrieve.assert_awaited_once_with(
        query="question",
        kb_names=["AI Infra"],
        top_k_fusion=20,
        top_m_final=3,
    )
