import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

RAG_SCRIPTS = Path(__file__).parents[2] / "rag-stack" / "scripts"


def load_script(name: str):
    """Load one deployment script as a module for behavior testing."""
    path = RAG_SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_reads_chunks_without_changing_source(tmp_path) -> None:
    """Migration reads all stored text and metadata in stable row order."""
    db_path = tmp_path / "doc.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE documents "
        "(id INTEGER PRIMARY KEY, doc_id TEXT, text TEXT, metadata TEXT)",
    )
    connection.executemany(
        "INSERT INTO documents(doc_id, text, metadata) VALUES (?, ?, ?)",
        [
            ("chunk-1", "alpha", '{"kb_id":"kb-1","chunk_index":0}'),
            ("chunk-2", "beta", '{"kb_id":"kb-1","chunk_index":1}'),
        ],
    )
    connection.commit()
    connection.close()
    before = db_path.read_bytes()

    chunks = load_script("migrate_kb.py").read_chunks(db_path)

    assert [chunk[0] for chunk in chunks] == ["chunk-1", "chunk-2"]
    assert chunks[1][2]["chunk_index"] == 1
    assert db_path.read_bytes() == before


def test_backend_switch_is_atomic_and_keeps_backup(tmp_path) -> None:
    """Cutover updates only the backend setting and preserves the old env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "QDRANT_API_KEY=secret\nASTRBOT_VECTOR_DB=faiss\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(RAG_SCRIPTS / "set_backend.py"),
            str(env_file),
            "qdrant",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "ASTRBOT_VECTOR_DB=qdrant" in env_file.read_text(encoding="utf-8")
    backups = list(tmp_path.glob(".env.bak.*"))
    assert len(backups) == 1
    assert "ASTRBOT_VECTOR_DB=faiss" in backups[0].read_text(encoding="utf-8")


def test_cutover_health_probe_uses_public_dashboard_root() -> None:
    """Restart waits must not probe a protected endpoint that always returns 401."""
    for script_name in ("cutover.sh", "rollback.sh"):
        script = (RAG_SCRIPTS / script_name).read_text(encoding="utf-8")
        assert "http://127.0.0.1:6185/" in script
        assert "/api/stat/version" not in script
        assert "AstrBot did not become ready" in script


def test_model_download_bootstrap_can_reach_host_loopback_proxy() -> None:
    """The one-time downloader must share the host network with the proxy."""
    script = (RAG_SCRIPTS / "download-model.sh").read_text(encoding="utf-8")
    assert "--network host" in script
    assert "HTTPS_PROXY" in script
    assert "astrbot-embedding-download" in script
    assert "rag_compose up -d embedding-server" in script


def test_embedding_uses_registered_nvidia_runtime_instead_of_cdi_hook() -> None:
    """Snap Docker CDI mode requires the registered NVIDIA OCI runtime."""
    script = (RAG_SCRIPTS / "download-model.sh").read_text(encoding="utf-8")
    compose = (RAG_SCRIPTS.parent / "docker-compose.yml").read_text(
        encoding="utf-8",
    )
    assert "--runtime=nvidia" in script
    assert "--gpus all" not in script
    assert "runtime: nvidia" in compose
    assert "NVIDIA_VISIBLE_DEVICES: all" in compose
    assert "gpus: all" not in compose


def test_astrbot_override_mounts_host_worktree_for_local_code_changes() -> None:
    override = (RAG_SCRIPTS.parent / "astrbot.override.yml").read_text(
        encoding="utf-8",
    )

    assert (
        "${ASTRBOT_SOURCE_ROOT:-/home/miku/astrbot-deploy/AstrBot}:/AstrBot" in override
    )


def test_astrbot_override_resets_incompatible_no_new_privileges_setting() -> None:
    override = (RAG_SCRIPTS.parent / "astrbot.override.yml").read_text(
        encoding="utf-8",
    )

    assert "security_opt: !reset []" in override


def test_group_persona_prompt_is_additive_and_idempotent() -> None:
    module = load_script("configure_group_behavior.py")

    updated = module.compose_group_persona_prompt("原有人格")

    assert updated.startswith("原有人格")
    assert module.GROUP_RESEARCH_PROMPT_MARKER in updated
    assert "技术问题" in updated
    assert "检索" in updated
    assert module.compose_group_persona_prompt(updated) == updated


def test_exa_web_search_config_preserves_a_minimal_reversible_state() -> None:
    module = load_script("configure_exa_web_search.py")
    config = {
        "provider_settings": {
            "web_search": False,
            "websearch_provider": "tavily",
            "web_search_link": False,
            "verified_factual_reply_policy": False,
            "websearch_exa_key": [],
        },
    }

    state = module.enable_exa_web_search(config)

    assert config["provider_settings"] == {
        "web_search": True,
        "websearch_provider": "exa",
        "web_search_link": True,
        "verified_factual_reply_policy": True,
        "websearch_exa_key": [],
    }
    assert state == {
        "web_search": {"present": True, "value": False},
        "websearch_provider": {"present": True, "value": "tavily"},
        "web_search_link": {"present": True, "value": False},
        "verified_factual_reply_policy": {"present": True, "value": False},
    }

    module.restore_web_search_settings(config, state)

    assert config["provider_settings"]["web_search"] is False
    assert config["provider_settings"]["websearch_provider"] == "tavily"
    assert config["provider_settings"]["web_search_link"] is False
    assert config["provider_settings"]["verified_factual_reply_policy"] is False


def test_napcat_self_messages_are_enabled_only_on_the_active_astrbot_client() -> None:
    module = load_script("configure_napcat_self_messages.py")
    config = {
        "reportSelfMessage": True,
        "network": {
            "websocketClients": [
                {
                    "name": "astrbot",
                    "enable": True,
                    "reportSelfMessage": False,
                },
                {
                    "name": "other",
                    "enable": True,
                    "reportSelfMessage": False,
                },
            ],
        },
    }

    changed = module.enable_self_messages(config, adapter_name="astrbot")

    assert changed is True
    assert "reportSelfMessage" not in config
    assert config["network"]["websocketClients"][0]["reportSelfMessage"] is True
    assert config["network"]["websocketClients"][1]["reportSelfMessage"] is False
    assert module.enable_self_messages(config, adapter_name="astrbot") is False


def test_napcat_self_message_config_fails_closed_without_one_active_client() -> None:
    module = load_script("configure_napcat_self_messages.py")

    with pytest.raises(RuntimeError, match="exactly one enabled"):
        module.enable_self_messages(
            {"network": {"websocketClients": []}},
            adapter_name="astrbot",
        )


def test_wake_prefix_aliases_are_additive_idempotent_and_reversible() -> None:
    module = load_script("configure_wake_prefixes.py")
    config = {"wake_prefix": ["/", "小董"]}

    state = module.add_wake_prefixes(
        config,
        ["东云bot", "东云Bot", "东云BOT"],
    )

    assert config["wake_prefix"] == ["/", "小董", "东云bot", "东云Bot", "东云BOT"]
    assert state == {"present": True, "value": ["/", "小董"]}
    module.restore_wake_prefixes(config, state)
    assert config["wake_prefix"] == ["/", "小董"]


def test_history_cpu_corpus_has_a_reproducible_quality_gate() -> None:
    """The historical CPU corpus must validate through its public CLI."""
    result = subprocess.run(
        [
            sys.executable,
            str(RAG_SCRIPTS / "validate_history_cpu_corpus.py"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS: historical CPU corpus" in result.stdout
    assert "Threadripper SKUs=14" in result.stdout
    assert "EPYC 7001/7002 SKUs=39" in result.stdout
    assert "Ryzen 3/5 desktop SKUs=25" in result.stdout
    assert "Xeon E5/E7 SKUs=244" in result.stdout
    assert "Xeon Scalable gen1-gen3 SKUs=181" in result.stdout
    assert "retrieval cases=31" in result.stdout
    assert "retrieval layers=overview:3,example:13,detail:15" in result.stdout
    assert "retrieval top-k=overview:5,example:8,detail:15" in result.stdout
    assert "representative case studies=13" in result.stdout
    assert "representative generations=20" in result.stdout
    assert "engineering-context case studies=13" in result.stdout


def test_history_cpu_import_plan_is_additive_and_resumable() -> None:
    """Corpus import may create/upload/skip, but never overwrite unknown data."""
    module = load_script("import_history_cpu.py")
    local = {
        "knowledge_base_name": "历史 CPU 型号与平台资料库",
        "corpus_sha256": "corpus-v1",
        "documents": {"a.md": "hash-a", "b.md": "hash-b"},
    }

    fresh = module.plan_import([], [], None, local)
    assert fresh == {"create": True, "kb_id": None, "upload": ["a.md", "b.md"]}

    state = {**local, "kb_id": "kb-history"}
    resumed = module.plan_import(
        [{"kb_id": "kb-history", "kb_name": local["knowledge_base_name"]}],
        ["a.md"],
        state,
        local,
    )
    assert resumed == {
        "create": False,
        "kb_id": "kb-history",
        "upload": ["b.md"],
    }

    with pytest.raises(RuntimeError, match="unmanaged documents"):
        module.plan_import(
            [{"kb_id": "kb-history", "kb_name": local["knowledge_base_name"]}],
            ["someone-elses-document.md"],
            state,
            local,
        )

    expanded = {
        **local,
        "corpus_sha256": "corpus-v2",
        "documents": {**local["documents"], "c.md": "hash-c"},
    }
    additive = module.plan_import(
        [{"kb_id": "kb-history", "kb_name": local["knowledge_base_name"]}],
        ["a.md", "b.md"],
        {**state, "status": "completed"},
        expanded,
    )
    assert additive == {
        "create": False,
        "kb_id": "kb-history",
        "upload": ["c.md"],
    }

    modified = {**expanded, "documents": {**expanded["documents"], "a.md": "new"}}
    with pytest.raises(RuntimeError, match="previously imported document changed"):
        module.plan_import(
            [{"kb_id": "kb-history", "kb_name": local["knowledge_base_name"]}],
            ["a.md", "b.md"],
            {**state, "status": "completed"},
            modified,
        )


def test_history_cpu_upload_plan_is_split_into_server_sized_batches() -> None:
    """An expanded corpus must preserve order and respect the 10-file API cap."""
    module = load_script("import_history_cpu.py")
    names = [f"case-{index:02}.md" for index in range(23)]

    batches = module.build_upload_batches(names)

    assert [len(batch) for batch in batches] == [10, 10, 3]
    assert [name for batch in batches for name in batch] == names
    assert module.build_upload_batches([]) == []


def test_history_cpu_retrieval_requires_the_expected_case_document(
    tmp_path,
) -> None:
    """Correct-looking terms from the wrong document must not pass retrieval."""
    module = load_script("import_history_cpu.py")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "threadripper_example",
                        "layer": "example",
                        "query": "给一个具体例子",
                        "expected_documents": ["34_threadripper.md"],
                        "required_term_groups": [["596.5 GFLOP/s"]],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "ok",
                "data": {
                    "results": [
                        {
                            "doc_name": "wrong.md",
                            "content": "596.5 GFLOP/s",
                        },
                    ],
                },
            }

    class Client:
        def post(self, *_args, **_kwargs):
            return Response()

    with pytest.raises(RuntimeError, match="expected document"):
        module.verify_retrieval(
            Client(),
            "http://astrbot/api/v1",
            "kb-history",
            "历史 CPU 型号与平台资料库",
            cases_path,
        )


def test_history_cpu_retrieval_uses_the_declared_layer_depth(tmp_path) -> None:
    """Runtime verification must exercise the same top-k as the bot layer."""
    module = load_script("import_history_cpu.py")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "detailed_report",
                        "layer": "detail",
                        "retrieval_top_k": 15,
                        "query": "详细介绍",
                        "expected_documents": ["report.md"],
                        "required_term_groups": [["NUMA"]],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    posted_top_k = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "ok",
                "data": {
                    "results": [
                        {"doc_name": "report.md", "content": "NUMA"},
                    ],
                },
            }

    class Client:
        def post(self, *_args, **kwargs):
            posted_top_k.append(kwargs["json"]["top_k"])
            return Response()

    module.verify_retrieval(
        Client(),
        "http://astrbot/api/v1",
        "kb-history",
        "历史 CPU 型号与平台资料库",
        cases_path,
    )

    assert posted_top_k == [15]


def test_history_cpu_import_requires_a_complete_backup(tmp_path) -> None:
    """An apply run must point at a completed backup manifest."""
    module = load_script("import_history_cpu.py")
    backup = tmp_path / "astrbot-rag-backup"
    backup.mkdir()
    (backup / "manifest.json").write_text(
        '{"created_at":"20260714T082441Z","files":[{"path":"kb.db"}],'
        '"qdrant_snapshots":[{"collection":"astrbot_kb_existing"}]}',
        encoding="utf-8",
    )

    manifest = module.validate_backup_dir(backup)

    assert manifest["created_at"] == "20260714T082441Z"
    with pytest.raises(RuntimeError, match="backup manifest"):
        module.validate_backup_dir(tmp_path / "missing")
