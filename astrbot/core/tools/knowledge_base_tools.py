import re
import time
from pathlib import Path

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api import logger, sp
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.selector import (
    KnowledgeBaseCandidate,
    select_knowledge_bases,
)
from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.core.star.context import Context
from astrbot.core.tools.registry import builtin_tool

_KNOWLEDGE_BASE_TOOL_CONFIG = {
    "kb_agentic_mode": True,
}
_KB_SELECTOR_PROVIDER_ID = "local_bge_m3"
_KB_SELECTOR_MIN_SIMILARITY = 0.52
_KB_SELECTOR_MAX_BASES = 2
_KB_SELECTOR_MAX_DOCUMENT_TITLES = 500
_HISTORY_CPU_KB_NAME = "历史 CPU 型号与平台资料库"
_HISTORY_CPU_DETAIL_MARKERS = (
    "详细",
    "完整介绍",
    "完整报告",
    "全部细节",
    "深入介绍",
    "detailed",
    "full report",
)
_HISTORY_CPU_EXAMPLE_MARKERS = (
    "例子",
    "实例",
    "实测",
    "测试报告",
    "benchmark",
    "case study",
)


def resolve_kb_final_top_k(
    query: str,
    kb_names: list[str],
    configured_top_k: int,
) -> int:
    """Expand only the historical CPU corpus for example/detail questions."""
    if _HISTORY_CPU_KB_NAME not in kb_names:
        return configured_top_k
    normalized_query = query.casefold()
    if any(marker in normalized_query for marker in _HISTORY_CPU_DETAIL_MARKERS):
        return max(configured_top_k, 15)
    if any(marker in normalized_query for marker in _HISTORY_CPU_EXAMPLE_MARKERS):
        return max(configured_top_k, 8)
    return configured_top_k


def check_all_kb(kb_list: list[KBHelper | None]) -> bool:
    """检查是否所有的知识库都为空"""
    return not any(
        kb and (kb.kb.doc_count != 0 or kb.kb.chunk_count != 0) for kb in kb_list
    )


def _normalize_document_title(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[\s_.-]+", " ", stem).strip()


async def _resolve_authorized_kb_helpers(
    umo: str,
    context: Context,
) -> list[KBHelper]:
    kb_mgr = context.kb_manager
    session_config = await sp.session_get(umo, "kb_config", default={})
    if session_config and "kb_ids" in session_config:
        helpers = [await kb_mgr.get_kb(kb_id) for kb_id in session_config["kb_ids"]]
        return [helper for helper in helpers if helper is not None]

    config = context.get_config(umo=umo)
    helpers = [await kb_mgr.get_kb_by_name(name) for name in config.get("kb_names", [])]
    return [helper for helper in helpers if helper is not None]


async def select_authorized_knowledge_bases(
    query: str,
    umo: str,
    context: Context,
) -> list[str]:
    """Select relevant KB names strictly within the session-authorized scope."""
    started_at = time.monotonic()
    try:
        provider = context.get_provider_by_id(_KB_SELECTOR_PROVIDER_ID)
        if not isinstance(provider, EmbeddingProvider):
            logger.warning(
                "[知识库路由] 本地 embedding provider 不可用，跳过知识库检索"
            )
            return []

        helpers = await _resolve_authorized_kb_helpers(umo, context)
        candidates: list[KnowledgeBaseCandidate] = []
        for helper in helpers:
            docs = await helper.list_documents(limit=_KB_SELECTOR_MAX_DOCUMENT_TITLES)
            prototypes = [helper.kb.kb_name]
            if helper.kb.description:
                prototypes.append(helper.kb.description.strip())
            prototypes.extend(
                title
                for doc in docs
                if (title := _normalize_document_title(doc.doc_name))
            )
            candidates.append(
                KnowledgeBaseCandidate(
                    kb_id=helper.kb.kb_id,
                    kb_name=helper.kb.kb_name,
                    prototypes=tuple(dict.fromkeys(prototypes)),
                )
            )

        selected = await select_knowledge_bases(
            query,
            candidates,
            provider,
            min_similarity=_KB_SELECTOR_MIN_SIMILARITY,
            max_bases=_KB_SELECTOR_MAX_BASES,
        )
        names = [item.candidate.kb_name for item in selected]
        logger.info(
            "[知识库路由] authorized=%d selected=%d elapsed_ms=%.1f",
            len(candidates),
            len(names),
            (time.monotonic() - started_at) * 1000,
        )
        return names
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[知识库路由] 选择失败，跳过知识库检索: %s",
            type(exc).__name__,
        )
        return []


async def retrieve_knowledge_base(
    query: str,
    umo: str,
    context: Context,
    *,
    kb_names: list[str] | None = None,
    max_results: int | None = None,
) -> str | None:
    """Retrieve knowledge base context for the given query."""
    kb_mgr = context.kb_manager
    config = context.get_config(umo=umo)

    session_config = await sp.session_get(umo, "kb_config", default={})
    if kb_names is not None:
        if not kb_names:
            return None
        top_k = session_config.get("top_k", config.get("kb_final_top_k", 5))
        logger.debug(f"[知识库] 使用语义路由结果，知识库数量: {len(kb_names)}")
    elif session_config and "kb_ids" in session_config:
        kb_ids = session_config.get("kb_ids", [])
        if not kb_ids:
            logger.info(f"[知识库] 会话 {umo} 已被配置为不使用知识库")
            return None

        top_k = session_config.get("top_k", 5)
        kb_names = []
        invalid_kb_ids = []
        for kb_id in kb_ids:
            kb_helper = await kb_mgr.get_kb(kb_id)
            if kb_helper:
                kb_names.append(kb_helper.kb.kb_name)
            else:
                logger.warning(f"[知识库] 知识库不存在或未加载: {kb_id}")
                invalid_kb_ids.append(kb_id)

        if invalid_kb_ids:
            logger.warning(
                f"[知识库] 会话 {umo} 配置的以下知识库无效: {invalid_kb_ids}",
            )
        if not kb_names:
            return None
        logger.debug(f"[知识库] 使用会话级配置，知识库数量: {len(kb_names)}")
    else:
        kb_names = config.get("kb_names", [])
        top_k = config.get("kb_final_top_k", 5)
        logger.debug(f"[知识库] 使用全局配置，知识库数量: {len(kb_names)}")

    top_k_fusion = config.get("kb_fusion_top_k", 20)
    if not kb_names:
        return None

    all_kbs = [await kb_mgr.get_kb_by_name(kb) for kb in kb_names]
    if check_all_kb(all_kbs):
        logger.debug("所配置的所有知识库全为空，跳过检索过程")
        return None

    top_k = resolve_kb_final_top_k(query, kb_names, top_k)
    if max_results is not None:
        top_k = min(top_k, max(0, max_results))
        if top_k == 0:
            return None
    logger.debug(f"[知识库] 开始检索知识库，数量: {len(kb_names)}, top_k={top_k}")
    kb_context = await kb_mgr.retrieve(
        query=query,
        kb_names=kb_names,
        top_k_fusion=top_k_fusion,
        top_m_final=top_k,
    )
    if not kb_context:
        return None

    formatted = kb_context.get("context_text", "")
    if formatted:
        results = kb_context.get("results", [])
        logger.debug(f"[知识库] 为会话 {umo} 注入了 {len(results)} 条相关知识块")
        return formatted
    return None


@builtin_tool(config=_KNOWLEDGE_BASE_TOOL_CONFIG)
@dataclass
class KnowledgeBaseQueryTool(FunctionTool[AstrAgentContext]):
    name: str = "astr_kb_search"
    description: str = (
        "Query the knowledge base for facts or relevant context. "
        "Use this tool when the user's question requires factual information, "
        "definitions, background knowledge, or previously indexed content. "
        "Only send short keywords or a concise question as the query."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise keyword query for the knowledge base.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        query = kwargs.get("query", "")
        if not query:
            return "error: Query parameter is empty."
        selected_names = context.context.event.get_extra("_selected_kb_names")
        retrieve_kwargs = {
            "query": query,
            "umo": context.context.event.unified_msg_origin,
            "context": context.context.context,
        }
        if isinstance(selected_names, list):
            retrieve_kwargs.update(
                kb_names=selected_names,
                max_results=3,
            )
        result = await retrieve_knowledge_base(
            **retrieve_kwargs,
        )
        if not result:
            return "No relevant knowledge found."
        return result


__all__ = [
    "KnowledgeBaseQueryTool",
    "check_all_kb",
    "resolve_kb_final_top_k",
    "retrieve_knowledge_base",
    "select_authorized_knowledge_bases",
]
