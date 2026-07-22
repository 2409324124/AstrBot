from astrbot.core.tools.knowledge_base_tools import (
    resolve_kb_final_top_k,
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
