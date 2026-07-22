#!/usr/bin/env python3
"""Validate the historical CPU Markdown corpus and import manifest."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "history-cpu"
REQUIRED_FAMILIES = {
    "intel_xeon_e5_e7_v1_v4",
    "intel_xeon_scalable_gen1_gen3",
    "amd_ryzen_3_5_zen_zenplus_zen2",
    "amd_threadripper_1000_2000_3000",
    "amd_threadripper_pro_3000wx",
    "amd_epyc_7001_7002",
}
REQUIRED_REPRESENTATIVE_GENERATIONS = {
    "intel_xeon_e5_v1",
    "intel_xeon_e5_v2",
    "intel_xeon_e5_v3",
    "intel_xeon_e5_v4",
    "intel_xeon_e7_v1",
    "intel_xeon_e7_v2",
    "intel_xeon_e7_v3",
    "intel_xeon_e7_v4",
    "intel_xeon_scalable_gen1",
    "intel_xeon_scalable_gen2",
    "intel_xeon_scalable_gen3",
    "amd_ryzen_zen",
    "amd_ryzen_zenplus",
    "amd_ryzen_zen2",
    "amd_threadripper_1000",
    "amd_threadripper_2000",
    "amd_threadripper_3000",
    "amd_threadripper_pro_3000wx",
    "amd_epyc_7001",
    "amd_epyc_7002",
}


def main() -> None:
    """Validate manifest coverage and every tracked Markdown document."""
    manifest_path = CORPUS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["source_policy"] == "vendor-primary"
    assert set(manifest["planned_families"]) == REQUIRED_FAMILIES

    entries = manifest["documents"]
    declared = {entry["path"] for entry in entries}
    actual = {path.name for path in CORPUS.glob("*.md")}
    assert declared == actual, (
        f"manifest/document mismatch: missing={sorted(declared - actual)}, "
        f"extra={sorted(actual - declared)}"
    )

    forbidden = re.compile(
        r"TODO|FIXME|待补|placeholder|(?<![A-Za-z0-9])sk-[a-z0-9]",
        re.I,
    )
    for entry in entries:
        path = CORPUS / entry["path"]
        text = path.read_text(encoding="utf-8")
        assert text.startswith("# "), f"missing H1: {path.name}"
        assert len(text) >= 1000, f"document too small: {path.name}"
        assert re.search(r"^## .*来源|^## 来源", text, re.MULTILINE), (
            f"missing source heading: {path.name}"
        )
        assert not forbidden.search(text), (
            f"unfinished or sensitive marker: {path.name}"
        )
        urls = entry["source_urls"]
        assert urls, f"missing source URLs: {path.name}"
        assert all(url.startswith("https://") for url in urls), (
            f"non-HTTPS source: {path.name}"
        )
        assert all(url in text for url in urls), f"manifest URL absent: {path.name}"

    cases_path = CORPUS / manifest["retrieval_cases"]
    retrieval_config = json.loads(cases_path.read_text(encoding="utf-8"))
    top_k_by_layer = retrieval_config["retrieval_top_k_by_layer"]
    assert top_k_by_layer == {"overview": 5, "example": 8, "detail": 15}, (
        f"retrieval top-k mismatch: {top_k_by_layer}"
    )
    cases = retrieval_config["cases"]
    assert len(cases) == 31, f"retrieval case count mismatch: {len(cases)}"
    assert len({case["id"] for case in cases}) == len(cases), (
        "duplicate retrieval case IDs"
    )
    layer_counts = Counter(case.get("layer") for case in cases)
    assert layer_counts == {"overview": 3, "example": 13, "detail": 15}, (
        f"retrieval layer mismatch: {dict(layer_counts)}"
    )
    for case in cases:
        assert case["query"].strip(), f"empty retrieval query: {case['id']}"
        retrieval_top_k = case.get(
            "retrieval_top_k",
            top_k_by_layer[case["layer"]],
        )
        assert isinstance(retrieval_top_k, int) and retrieval_top_k > 0, (
            f"invalid retrieval top-k: {case['id']}"
        )
        expected_documents = case.get("expected_documents")
        assert expected_documents, f"missing expected documents: {case['id']}"
        assert set(expected_documents) <= declared, (
            f"unknown expected document: {case['id']}"
        )
        groups = case["required_term_groups"]
        assert groups and all(group for group in groups), (
            f"empty retrieval term group: {case['id']}"
        )
        expected_text = "\n".join(
            (CORPUS / path).read_text(encoding="utf-8") for path in expected_documents
        )
        assert all(any(term in expected_text for term in group) for group in groups), (
            f"retrieval terms absent from expected documents: {case['id']}"
        )

    case_entries = [
        entry
        for entry in entries
        if entry.get("document_type") == "representative_case"
    ]
    assert len(case_entries) == 13, (
        f"representative case study count mismatch: {len(case_entries)}"
    )
    engineering_context_count = 0
    for entry in case_entries:
        text = (CORPUS / entry["path"]).read_text(encoding="utf-8")
        for heading in ("## 测试环境", "## 限制与检索提示"):
            assert heading in text, f"missing {heading}: {entry['path']}"
        assert "NUMA" in text and "HPC" in text, (
            f"case study lacks NUMA/HPC detail: {entry['path']}"
        )
        assert re.search(r"有限元|CAE", text, re.I), (
            f"case study lacks finite-element/CAE context: {entry['path']}"
        )
        engineering_context_count += 1
    representative_generations = {
        generation
        for entry in case_entries
        for generation in entry.get("representative_generations", [])
    }
    assert representative_generations == REQUIRED_REPRESENTATIVE_GENERATIONS, (
        "representative generation mismatch: "
        f"missing={sorted(REQUIRED_REPRESENTATIVE_GENERATIONS - representative_generations)}, "
        f"extra={sorted(representative_generations - REQUIRED_REPRESENTATIVE_GENERATIONS)}"
    )

    threadripper_text = (CORPUS / "20_AMD_Threadripper_Zen到Zen2完整型号.md").read_text(
        encoding="utf-8"
    )
    threadripper_models = set(
        re.findall(
            r"^\|\s*((?:PRO\s+)?(?:19|29|39)\d{2}(?:WX|X))\s*\|",
            threadripper_text,
            re.MULTILINE,
        ),
    )
    assert len(threadripper_models) == 14, (
        f"Threadripper SKU count mismatch: {len(threadripper_models)}"
    )

    epyc_text = (CORPUS / "21_AMD_EPYC_7001与7002完整型号.md").read_text(
        encoding="utf-8",
    )
    epyc_models = set(
        re.findall(
            r"^\|\s*(7(?:H12|F(?:32|52|72)|\d{3}P?))\s*\|",
            epyc_text,
            re.MULTILINE,
        ),
    )
    assert len(epyc_models) == 39, f"EPYC SKU count mismatch: {len(epyc_models)}"

    ryzen_text = (CORPUS / "22_AMD_Ryzen3与Ryzen5_Zen到Zen2桌面型号.md").read_text(
        encoding="utf-8"
    )
    ryzen_models = set(
        re.findall(
            r"^\|\s*(Ryzen\s+[35]\s+\d{4}(?:X|XT|G|GE)?)\s*\|",
            ryzen_text,
            re.MULTILINE,
        ),
    )
    assert len(ryzen_models) == 25, (
        f"Ryzen 3/5 desktop SKU count mismatch: {len(ryzen_models)}"
    )

    xeon_text = "\n".join(
        (CORPUS / filename).read_text(encoding="utf-8")
        for filename in (
            "10_Intel_Xeon_E5初代至v4完整型号.md",
            "11_Intel_Xeon_E7初代至v4完整型号.md",
        )
    )
    xeon_models = set(
        re.findall(
            r"^\|\s*(E[57]-[^|]+?)\s*\|",
            xeon_text,
            re.MULTILINE,
        ),
    )
    assert len(xeon_models) == 244, f"Xeon E5/E7 SKU count mismatch: {len(xeon_models)}"

    scalable_text = (CORPUS / "12_Intel_Xeon_Scalable第一至三代完整型号.md").read_text(
        encoding="utf-8"
    )
    scalable_models = set(
        re.findall(
            r"^\|\s*((?:Bronze|Silver|Gold|Platinum)\s+[^|]+?)\s*\|",
            scalable_text,
            re.MULTILINE,
        ),
    )
    assert len(scalable_models) == 181, (
        f"Xeon Scalable gen1-gen3 SKU count mismatch: {len(scalable_models)}"
    )

    print(
        "PASS: historical CPU corpus "
        f"({len(entries)} documents, {len(REQUIRED_FAMILIES)} planned families)",
    )
    print(f"PASS: Threadripper SKUs={len(threadripper_models)}")
    print(f"PASS: EPYC 7001/7002 SKUs={len(epyc_models)}")
    print(f"PASS: Ryzen 3/5 desktop SKUs={len(ryzen_models)}")
    print(f"PASS: Xeon E5/E7 SKUs={len(xeon_models)}")
    print(f"PASS: Xeon Scalable gen1-gen3 SKUs={len(scalable_models)}")
    print(f"PASS: retrieval cases={len(cases)}")
    print("PASS: retrieval layers=overview:3,example:13,detail:15")
    print("PASS: retrieval top-k=overview:5,example:8,detail:15")
    print(f"PASS: representative case studies={len(case_entries)}")
    print(f"PASS: representative generations={len(representative_generations)}")
    print(f"PASS: engineering-context case studies={engineering_context_count}")


if __name__ == "__main__":
    main()
