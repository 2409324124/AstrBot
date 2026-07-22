#!/usr/bin/env python3
"""Build historical Intel Xeon Markdown tables from saved ARK pages."""

from __future__ import annotations

import argparse
import html
import re
from html.parser import HTMLParser
from pathlib import Path

FAMILIES = {
    "E5": [
        (
            "intel-e5-v1.html",
            "E5 初代（Sandy Bridge-EP/EN）",
            43,
            "https://www.intel.com/content/www/us/en/ark/products/series/59138/intel-xeon-processor-e5-family.html",
        ),
        (
            "intel-e5-v2.html",
            "E5 v2（Ivy Bridge-EP/EN）",
            47,
            "https://www.intel.com/content/www/us/en/ark/products/series/78582/intel-xeon-processor-e5-v2-family.html",
        ),
        (
            "intel-e5-v3.html",
            "E5 v3（Haswell-EP/EN）",
            48,
            "https://www.intel.com/content/www/us/en/ark/products/series/78583/intel-xeon-processor-e5-v3-family.html",
        ),
        (
            "intel-e5-v4.html",
            "E5 v4（Broadwell-EP/EN）",
            44,
            "https://www.intel.com/content/www/us/en/ark/products/series/91287/intel-xeon-processor-e5-v4-family.html",
        ),
    ],
    "E7": [
        (
            "intel-e7-v1.html",
            "E7 初代（Westmere-EX）",
            18,
            "https://www.intel.com/content/www/us/en/ark/products/series/59139/intel-xeon-processor-e7-family.html",
        ),
        (
            "intel-e7-v2.html",
            "E7 v2（Ivy Bridge-EX）",
            20,
            "https://www.intel.com/content/www/us/en/ark/products/series/78584/intel-xeon-processor-e7-v2-family.html",
        ),
        (
            "intel-e7-v3.html",
            "E7 v3（Haswell-EX）",
            12,
            "https://www.intel.com/content/www/us/en/ark/products/series/78585/intel-xeon-processor-e7-v3-family.html",
        ),
        (
            "intel-e7-v4.html",
            "E7 v4（Broadwell-EX）",
            12,
            "https://www.intel.com/content/www/us/en/ark/products/series/93797/intel-xeon-processor-e7-v4-family.html",
        ),
    ],
    "Scalable": [
        (
            "intel-scalable-gen1.html",
            "第一代 Xeon Scalable（Skylake-SP）",
            52,
            "https://www.intel.com/content/www/us/en/ark/products/series/125191/intel-xeon-scalable-processors.html",
        ),
        (
            "intel-scalable-gen2.html",
            "第二代 Xeon Scalable（Cascade Lake）",
            76,
            "https://www.intel.com/content/www/us/en/ark/products/series/192283/2nd-gen-intel-xeon-scalable-processors.html",
        ),
        (
            "intel-scalable-gen3.html",
            "第三代 Xeon Scalable（Cooper Lake / Ice Lake）",
            53,
            "https://www.intel.com/content/www/us/en/ark/products/series/204098/3rd-gen-intel-xeon-scalable-processors.html",
        ),
    ],
}


class ArkTableParser(HTMLParser):
    """Read the public product rows from one Intel ARK collection page."""

    def __init__(self) -> None:
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Start a product row or table cell when ARK emits one."""
        attrs_dict = dict(attrs)
        if tag == "tr" and attrs_dict.get("data-product-id"):
            self.in_row = True
            self.row = []
        elif self.in_row and tag == "td":
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        """Collect visible text from the active table cell."""
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Finalize one table cell or product row."""
        if self.in_row and self.in_cell and tag == "td":
            value = html.unescape(" ".join(self.cell_parts))
            self.row.append(re.sub(r"\s+", " ", value).strip())
            self.in_cell = False
            self.cell_parts = []
        elif self.in_row and tag == "tr":
            if self.row:
                self.rows.append(self.row[:7])
            self.in_row = False
            self.row = []


def render_family(source_dir: Path, family: str) -> str:
    """Render one complete Xeon family from saved official pages.

    Args:
        source_dir: Directory containing the saved Intel ARK HTML pages.
        family: Family key: ``E5``, ``E7`` or ``Scalable``.

    Returns:
        Complete Markdown document text.

    Raises:
        AssertionError: If an ARK page does not contain its expected SKU count.
    """
    if family == "E5":
        lines = [
            "# Intel Xeon E5 初代至 v4：ARK 完整型号目录",
            "",
            "Xeon E5 横跨单路工作站、双路服务器、四路服务器和部分嵌入式/通信型号。"
            "ARK 家族页把 E5-1400、1600、2400、2600、4600 等子系列放在同一代集合中，"
            "所以不能由‘E5 v4’直接推断 socket、最大 CPU 路数、内存通道或主板兼容性。",
            "",
            "E5 初代/v2 主要对应 Sandy Bridge/Ivy Bridge，E5 v3/v4 转入 Haswell/Broadwell。"
            "常见 E5-1600/2600 从 LGA2011 迁移到 v3/v4 的 LGA2011-3，DDR3 也转向 DDR4；"
            "不同 E5-2400/4600 和 OEM 平台仍须逐型号核对 ARK 与整机支持表。",
        ]
    elif family == "E7":
        lines = [
            "# Intel Xeon E7 初代至 v4：ARK 完整型号目录",
            "",
            "Xeon E7 面向大内存、多路关键业务服务器。型号中的 2xxx、4xxx、8xxx 通常对应"
            "不同最大路数和平台定位，但具体 socket、QPI、内存扩展缓冲和最大容量必须读取"
            "单品 ARK 与服务器厂商支持表。E7 v2/v3/v4 不是 Xeon Scalable 的第二至第四代。",
            "",
            "四代依次覆盖 Westmere-EX、Ivy Bridge-EX、Haswell-EX、Broadwell-EX。"
            "二手采购时，CPU 外观接近并不表示能跨代混插；主板、内存 riser、固件、"
            "散热功耗等级和整机 service processor 都属于兼容性的一部分。",
        ]
    else:
        lines = [
            "# Intel Xeon Scalable 第一至三代：ARK 完整型号目录",
            "",
            "Xeon Scalable 以 Bronze、Silver、Gold、Platinum 分层替代了部分旧 E5/E7 命名。"
            "本目录按 Intel ARK 当前家族页保留全部 181 个条目；后缀 M、T、N、P、R、S、U、"
            "Y、H、HL 等是平台、容量、网络、功耗或市场细分标记，不能省略后直接判断兼容性。",
            "",
            "第一代主要是 Skylake-SP，常见平台为六通道 DDR4 与 PCIe 3.0；第二代主要是 "
            "Cascade Lake，并包含 Refresh 与 Platinum 9200 多芯片产品。第三代 ARK 集合同时"
            "包含面向四/八路的 Cooper Lake 和面向一/两路的 Ice Lake-SP：后者常见最高 40 核、"
            "八通道 DDR4-3200 和 PCIe 4.0，但这些属性不能外推到第三代的每一个型号。",
        ]

    for filename, heading, expected, _url in FAMILIES[family]:
        page = (source_dir / filename).read_text(encoding="utf-8")
        first_product = page.index("data-product-id=")
        table_start = page.rfind("<tr", 0, first_product)
        table_end = page.index("</tbody>", first_product) + len("</tbody>")
        parser = ArkTableParser()
        parser.feed(page[table_start:table_end])
        assert len(parser.rows) == expected, (
            f"{filename}: expected {expected} products, found {len(parser.rows)}"
        )
        lines.extend(
            [
                "",
                f"## {heading}：{expected} 款",
                "",
                "| 型号 | 上市 | 核心 | 最高睿频 | 基础频率 | 缓存 | TDP |",
                "|---|---|---:|---:|---:|---:|---:|",
            ],
        )
        for row in parser.rows:
            product = re.sub(r"^Intel® Xeon® Processor\s+", "", row[0])
            product = re.sub(r"^Intel® Xeon®\s+", "", product)
            product = re.sub(r"\s+Processor$", "", product)
            values = [value or "—" for value in row[1:7]]
            lines.append(f"| {product} | {' | '.join(values)} |")

    lines.extend(
        [
            "",
            "## 表格使用限制",
            "",
            "本表只复制 ARK 家族页公开的上市时间、核心、频率、缓存和 TDP。"
            "它不把缺失睿频补成基础频率，也不从系列名推断 socket、内存通道、PCIe lanes。"
            "同名 OEM/R 后缀、L 低功耗和 W 工作站型号均按 ARK 原名保留。",
            "",
            "## 官方来源",
            "",
        ],
    )
    lines.extend(
        f"- [Intel ARK: {heading}]({url})" for _, heading, _, url in FAMILIES[family]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    """Build tracked Markdown documents from ignored local source pages."""
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "10_Intel_Xeon_E5初代至v4完整型号.md").write_text(
        render_family(args.source_dir, "E5"),
        encoding="utf-8",
    )
    (args.output_dir / "11_Intel_Xeon_E7初代至v4完整型号.md").write_text(
        render_family(args.source_dir, "E7"),
        encoding="utf-8",
    )
    (args.output_dir / "12_Intel_Xeon_Scalable第一至三代完整型号.md").write_text(
        render_family(args.source_dir, "Scalable"),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
