from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.response_policy import (
    FACTUAL_GUARD_REQUIRED_EXTRA_KEY,
    RESPONSE_MARKER,
    apply_response_policy_to_chain,
    build_factual_evidence_prompt,
    prepare_reply_policy_event,
    select_trusted_sources,
)


class _Event:
    def __init__(self, extras=None):
        self.extras = extras or {}
        self.message_str = ""

    def get_extra(self, key, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key, value):
        self.extras[key] = value

    def get_platform_name(self):
        return "aiocqhttp"


def test_select_trusted_sources_rejects_social_only_and_keeps_established_source():
    sources = select_trusted_sources(
        [
            {
                "title": "Post on X",
                "url": "https://x.com/example/status/1",
                "snippet": "unverified",
            },
            {
                "title": "Reuters report",
                "url": "https://www.reuters.com/world/example",
                "snippet": "reported facts",
            },
            {
                "title": "Random blog",
                "url": "https://example.invalid/post",
                "snippet": "opinion",
            },
        ]
    )

    assert sources == [
        {
            "title": "Reuters report",
            "url": "https://www.reuters.com/world/example",
            "snippet": "reported facts",
        }
    ]


def test_select_trusted_sources_accepts_official_intel_primary_source():
    sources = select_trusted_sources(
        [
            {
                "title": "Intel Xeon CPU Max Series",
                "url": "https://www.intel.com/content/www/us/en/products/details/processors/xeon/max-series.html",
                "snippet": "Official product information",
            }
        ]
    )

    assert [source["url"] for source in sources] == [
        "https://www.intel.com/content/www/us/en/products/details/processors/xeon/max-series.html"
    ]


def test_build_factual_evidence_prompt_marks_only_returned_sources_as_trusted():
    prompt = build_factual_evidence_prompt(
        [
            {
                "title": "Official source",
                "url": "https://www.who.int/news/example",
                "snippet": "verified excerpt",
            }
        ]
    )

    assert "https://www.who.int/news/example" in prompt
    assert "Do not use previous assistant messages as evidence" in prompt
    assert 'source_type="web_trusted"' in prompt


def test_response_policy_appends_marker_for_non_factual_reply():
    result = apply_response_policy_to_chain(
        MessageChain([Plain("喵，收到")]),
        _Event(),
    )

    assert result.get_plain_text() == f"喵，收到\n{RESPONSE_MARKER}"


def test_response_policy_keeps_exactly_one_marker():
    result = apply_response_policy_to_chain(
        MessageChain([Plain(f"喵，收到\n{RESPONSE_MARKER}")]),
        _Event(),
    )

    assert result.get_plain_text().count(RESPONSE_MARKER) == 1


def test_response_policy_normalises_inline_uppercase_ai_marker():
    result = apply_response_policy_to_chain(
        MessageChain([Plain("回答正文。（AI生成内容）")]),
        _Event(),
    )

    assert result.get_plain_text() == f"回答正文。\n{RESPONSE_MARKER}"
    assert "（AI生成内容）" not in result.get_plain_text()


def test_response_policy_collapses_multiple_plain_parts_without_duplication():
    result = apply_response_policy_to_chain(
        MessageChain([Plain("第一段。"), Plain("第二段。")]),
        _Event(),
    )

    text = result.get_plain_text()
    assert text == f"第一段。 第二段。\n{RESPONSE_MARKER}"
    assert text.count("第一段。") == 1
    assert text.count("第二段。") == 1
    assert text.count(RESPONSE_MARKER) == 1
    assert sum(isinstance(part, Plain) for part in result.chain) == 1


def test_response_policy_suppresses_factual_reply_without_trusted_source():
    result = apply_response_policy_to_chain(
        MessageChain([Plain("这是模型自行编出的具体说法")]),
        _Event({FACTUAL_GUARD_REQUIRED_EXTRA_KEY: True}),
    )

    assert result.chain == []


def test_global_reply_policy_does_not_reclassify_message_text():
    event = _Event()

    assert prepare_reply_policy_event(
        event,
        enabled=True,
        prompt="2026年某人在什么地方发表了什么讲话？",
    )
    result = apply_response_policy_to_chain(
        MessageChain([Plain("未经来源核验的回答")]),
        event,
    )

    assert event.get_extra(FACTUAL_GUARD_REQUIRED_EXTRA_KEY) is None
    assert result.get_plain_text() == f"未经来源核验的回答\n{RESPONSE_MARKER}"


def test_result_decorate_final_boundary_suppresses_external_route_without_evidence():
    event = _Event({FACTUAL_GUARD_REQUIRED_EXTRA_KEY: True})
    event.message_str = "2026年这件事发生在什么地方？"
    stage = ResultDecorateStage.__new__(ResultDecorateStage)
    stage.verified_factual_reply_policy = True
    result = MessageEventResult().message("这是一条未经过 Agent 边界的私聊事实回答")

    stage._apply_final_reply_policy(event, result)

    assert result.chain == []


def test_result_decorate_keeps_local_bm25_technical_answer_without_web_source():
    event = _Event()
    event.message_str = "这个知识库是否使用BM25的向量检索？"
    stage = ResultDecorateStage.__new__(ResultDecorateStage)
    stage.verified_factual_reply_policy = True
    result = MessageEventResult().message("当前知识库使用向量检索。")

    stage._apply_final_reply_policy(event, result)

    assert result.get_plain_text() == f"当前知识库使用向量检索。\n{RESPONSE_MARKER}"


def test_result_decorate_does_not_turn_empty_intermediate_result_into_reply():
    event = _Event()
    event.message_str = "第四代至强 Max 有哪些型号？"
    stage = ResultDecorateStage.__new__(ResultDecorateStage)
    stage.verified_factual_reply_policy = True
    result = MessageEventResult()

    stage._apply_final_reply_policy(event, result)

    assert result.chain == []


@pytest.mark.asyncio
async def test_respond_stage_does_not_send_an_empty_suppressed_result():
    event = MagicMock()
    event.get_result.return_value = MessageEventResult()
    event.get_extra.side_effect = lambda key, default=None: default

    await RespondStage().process(event)

    event.send.assert_not_called()


def test_response_policy_attaches_controlled_trusted_source_footer():
    source = {
        "title": "Reuters report",
        "url": "https://www.reuters.com/world/example",
        "snippet": "reported facts",
    }
    result = apply_response_policy_to_chain(
        MessageChain([Plain("检索到的结论。来源：https://evil.example/fake")]),
        _Event(
            {
                FACTUAL_GUARD_REQUIRED_EXTRA_KEY: True,
                "_factual_trusted_sources": [source],
            }
        ),
    )

    text = result.get_plain_text()
    assert "https://evil.example/fake" not in text
    assert "可信来源：Reuters report — https://www.reuters.com/world/example" in text
    assert text.endswith(RESPONSE_MARKER)


def test_response_policy_is_idempotent_when_global_stage_runs_after_agent_stage():
    source = {
        "title": "Reuters report",
        "url": "https://www.reuters.com/world/example",
        "snippet": "reported facts",
    }
    event = _Event(
        {
            FACTUAL_GUARD_REQUIRED_EXTRA_KEY: True,
            "_factual_trusted_sources": [source],
        }
    )

    once = apply_response_policy_to_chain(
        MessageChain([Plain("检索到的结论。")]),
        event,
    )
    twice = apply_response_policy_to_chain(once, event)

    assert twice.get_plain_text().count("可信来源：Reuters report") == 1
    assert twice.get_plain_text().count(RESPONSE_MARKER) == 1


@pytest.mark.asyncio
async def test_agent_runner_suppresses_unverified_factual_llm_result():
    event = _Event(
        {
            "_verified_reply_policy_enabled": True,
            FACTUAL_GUARD_REQUIRED_EXTRA_KEY: True,
        }
    )
    event.is_stopped = lambda: False
    event.trace = MagicMock()
    event.set_result = MagicMock()
    event.clear_result = MagicMock()

    class _Runner:
        streaming = False
        req = None
        run_context = SimpleNamespace(
            context=SimpleNamespace(event=event),
            messages=[],
        )

        def done(self):
            return True

        def request_stop(self):
            raise AssertionError("the runner should not be stopped")

        async def step(self):
            yield SimpleNamespace(
                type="llm_result",
                data={"chain": MessageChain([Plain("未经核验的断言")])},
            )

    delivered = [
        chain
        async for chain in run_agent(
            _Runner(),
            show_tool_use=False,
        )
    ]

    assert len(delivered) == 1
    assert delivered[0].chain == []
