# AMD Ryzen 3 与 Ryzen 5：Zen、Zen+、Zen 2 桌面型号

本章首批覆盖消费级桌面 CPU/APU 和公开 OEM 桌面型号，不把 Ryzen PRO 和移动版混入同一张表。最大陷阱是“产品编号不等于 CPU 核心架构”：Ryzen 2000G APU 使用 Zen，Ryzen 3000G APU 使用 Zen+，Ryzen 4000G 才使用 Zen 2。购买二手 AM4 平台时必须同时核对型号、核心代际、主板 BIOS 和 PCIe 版本。

## Zen：Ryzen 1000 CPU 与 Ryzen 2000G APU

| 型号 | 类型 | 核心/线程 | 基础/加速 GHz | Total Cache | TDP | PCIe/内存 |
|---|---|---:|---:|---:|---:|---|
| Ryzen 5 1600X | CPU | 6/12 | 3.6/4.0 | 19MB | 95W | PCIe 3.0，双通道 DDR4 |
| Ryzen 5 1600 | CPU | 6/12 | 3.2/3.6 | 19MB | 65W | PCIe 3.0，双通道 DDR4 |
| Ryzen 5 1500X | CPU | 4/8 | 3.5/3.7 | 18MB | 65W | PCIe 3.0，双通道 DDR4 |
| Ryzen 5 1400 | CPU | 4/8 | 3.2/3.4 | 10MB | 65W | PCIe 3.0，双通道 DDR4 |
| Ryzen 3 1300X | CPU | 4/4 | 3.5/3.7 | 10MB | 65W | PCIe 3.0，双通道 DDR4 |
| Ryzen 3 1200 | CPU | 4/4 | 3.1/3.4 | 10MB | 65W | PCIe 3.0，双通道 DDR4 |
| Ryzen 5 2400G | APU, Vega 11 | 4/8 | 3.6/3.9 | 6MB | 65W | PCIe 3.0，双通道 DDR4 |
| Ryzen 3 2200G | APU, Vega 8 | 4/4 | 3.5/3.7 | 6MB | 65W | PCIe 3.0，双通道 DDR4 |

Ryzen 5 1600 后期存在俗称“1600 AF”的 12nm respin，但 AMD 的公开营销型号仍是 Ryzen 5 1600。知识库不把它伪造为第二个正式 SKU；识别时应查看盒装/托盘 OPN、CPU-Z family/model/stepping 和实际制程，而不是只看 Windows 中的名称。

## Zen+：Ryzen 2000 CPU 与 Ryzen 3000G APU

| 型号 | 类型 | 核心/线程 | 基础/加速 GHz | Total Cache | TDP | 备注 |
|---|---|---:|---:|---:|---:|---|
| Ryzen 5 2600X | CPU | 6/12 | 3.6/4.2 | 19MB | 95W | 12nm，零售 |
| Ryzen 5 2600 | CPU | 6/12 | 3.4/3.9 | 19MB | 65W | 12nm，零售 |
| Ryzen 5 2500X | CPU | 4/8 | 3.6/4.0 | 10MB | 65W | 12nm，主要面向 OEM/SI |
| Ryzen 3 2300X | CPU | 4/4 | 3.5/4.0 | 10MB | 65W | 12nm，主要面向 OEM/SI |
| Ryzen 5 3400G | APU, Vega 11 | 4/8 | 3.7/4.2 | 6MB | 65W | Zen+，不是 Zen 2 |
| Ryzen 3 3200G | APU, Vega 8 | 4/4 | 3.6/4.0 | 6MB | 65W | Zen+，不是 Zen 2 |

2600X/2600 是 2018 年第二代 Ryzen 的公开零售主力。2500X/2300X 多见于 OEM 整机和区域市场，二手平台中确实存在，但零售盒装渠道较少。3400G/3200G 虽然使用 3000 编号，CPU 核心仍为 Zen+，且 APU 的 PCIe lane 配置与无核显 Matisse CPU 不同。

## Zen 2：Ryzen 3000 CPU

| 型号 | 类型 | 核心/线程 | 基础/加速 GHz | Total Cache | TDP | PCIe |
|---|---|---:|---:|---:|---:|---|
| Ryzen 5 3600XT | CPU | 6/12 | 3.8/4.5 | 35MB | 95W | PCIe 4.0 |
| Ryzen 5 3600X | CPU | 6/12 | 3.8/4.4 | 35MB | 95W | PCIe 4.0 |
| Ryzen 5 3600 | CPU | 6/12 | 3.6/4.2 | 35MB | 65W | PCIe 4.0 |
| Ryzen 5 3500X | CPU | 6/6 | 3.6/4.1 | 35MB | 65W | PCIe 4.0，区域/OEM |
| Ryzen 5 3500 | CPU | 6/6 | 3.6/4.1 | 19MB | 65W | PCIe 4.0，区域/OEM |
| Ryzen 3 3300X | CPU | 4/8 | 3.8/4.3 | 18MB | 65W | PCIe 4.0 |
| Ryzen 3 3100 | CPU | 4/8 | 3.6/3.9 | 18MB | 65W | PCIe 4.0 |

Ryzen 3 3100 和 3300X 都是 4 核 8 线程，但 CCD/CCX 布局和频率不同；不能只按核心数推断游戏或延迟表现。3500 与 3500X 关闭 SMT，L3 也不同，型号末尾的 X 不是唯一差异。

## Zen 2：Ryzen 4000G 桌面 APU

| 型号 | 类型 | 核心/线程 | 基础/加速 GHz | Total Cache | TDP | PCIe/渠道 |
|---|---|---:|---:|---:|---:|---|
| Ryzen 5 4600G | APU, Vega 7 | 6/12 | 3.7/4.2 | 11MB | 65W | PCIe 3.0，初期 OEM/SI |
| Ryzen 5 4600GE | APU, Vega 7 | 6/12 | 3.3/4.2 | 11MB | 35W | PCIe 3.0，OEM/SI |
| Ryzen 3 4300G | APU, Vega 6 | 4/8 | 3.8/4.0 | 6MB | 65W | PCIe 3.0，OEM/SI |
| Ryzen 3 4300GE | APU, Vega 6 | 4/8 | 3.5/4.0 | 6MB | 35W | PCIe 3.0，OEM/SI |

4000G 是 Zen 2，但其单片 Renoir 设计、较小 L3 和 PCIe 3.0 与 Ryzen 3000 Matisse 不同。对于带独立 GPU 的本地 AI 主机，4600G 的 6 核 12 线程可承担轻量预处理，但 PCIe 代际、可用 lanes 和主板槽位拓扑仍应单独确认。

## AM4 兼容性与识别规则

- AM4 只描述机械/电气平台家族，不能保证任意主板 BIOS 支持任意 Ryzen。先查主板厂商 CPU support list 和最低 BIOS 版本。
- B350/X370 等早期主板是否支持 Zen 2 取决于厂商 BIOS；升级前保存旧 BIOS，并确认升级路径是否要求桥接版本。
- APU 型号带核显，但会使用一部分封装 I/O 资源；无核显 CPU 通常需要独立显卡才能输出画面。
- 内存超频标称与 CPU 官方内存规格不是同一概念。四 DIMM、双 Rank 和老 BIOS 可能降低可稳定频率。
- 采购时记录完整 OPN，可区分同名 respin、PRO/OEM 与区域型号。

## 官方来源

- [AMD Processor Specifications](https://www.amd.com/en/products/specifications/processors.html)
- [AMD Zen architecture history](https://www.amd.com/en/technologies/zen-core.html)
- [AMD 2017 Ryzen 5 lineup](https://www.amd.com/en/newsroom/press-releases/2017-3-15-amd-ryzen-5-cpus-to-power-performance-desktop-pcs-.html)
- [AMD 2017 Ryzen 3 lineup](https://www.amd.com/en/newsroom/press-releases/2017-7-27-amd-completes-ryzen-mainstream-desktop-lineup-wit.html)
- [AMD 2018 Ryzen desktop APU launch](https://www.amd.com/en/newsroom/press-releases/2018-2-12-first-amd-ryzen-desktop-apus-featuring-world-s-mo.html)
- [AMD 2018 second-generation Ryzen lineup](https://www.amd.com/en/newsroom/press-releases/2018-4-13-2nd-generation-amd-ryzen-processors-ultimate-des.html)
- [AMD 2019 Ryzen 3000 Computex announcement](https://www.amd.com/en/newsroom/press-releases/2019-5-26-amd-announces-next-generation-leadership-products.html)
- [AMD 2019 Ryzen 3000 and 3000G availability](https://www.amd.com/en/newsroom/press-releases/2019-7-7-amd-unleashes-ultimate-pc-gaming-platform-with-wor.html)
- [AMD 2020 Ryzen 3 3100/3300X announcement](https://www.amd.com/en/newsroom/press-releases/2020-4-21-amd-expands-3rd-gen-amd-ryzen-desktop-processor-fa.html)
- [AMD 2020 Ryzen 3000XT announcement](https://www.amd.com/en/newsroom/press-releases/2020-6-16-amd-offers-enthusiasts-more-choice-than-ever-befor.html)
- [AMD 2020 Ryzen 4000G desktop lineup](https://www.amd.com/en/newsroom/press-releases/2020-7-21-amd-ryzen-4000-series-desktop-processors-with-amd-.html)
