# AMD Threadripper Zen、Zen+ 与 Zen 2 完整型号和平台

本章覆盖首代 Ryzen Threadripper、第二代 Threadripper、第三代 Threadripper，以及首代 Threadripper PRO 3000WX。它们虽然都属于高核心数工作站/HEDT 产品，但横跨 sTR4/X399、sTRX4/TRX40 和 sWRX8/WRX80 三套平台，不能只按插槽外形或型号数字判断兼容性。

## 1000 系列：Zen 与 X399

| 型号 | 架构 | 核心/线程 | 基础/加速 GHz | TDP | PCIe | 内存与插槽 |
|---|---|---:|---:|---:|---:|---|
| 1950X | Zen, 14nm | 16/32 | 3.4/4.0 | 180W | 64 lanes PCIe 3.0 | sTR4/X399，4 通道 DDR4 |
| 1920X | Zen, 14nm | 12/24 | 3.5/4.0 | 180W | 64 lanes PCIe 3.0 | sTR4/X399，4 通道 DDR4 |
| 1900X | Zen, 14nm | 8/16 | 3.8/4.0 | 180W | 64 lanes PCIe 3.0 | sTR4/X399，4 通道 DDR4 |

AMD 2017 年官方发布表给出三款完整阵容。1950X 和 1920X 的上市日为 8 月 10 日，1900X 为 8 月 31 日。官方单品规格进一步给出 DDR4-2667、1950X/1920X 的 32MB L3，以及 1900X 的 16MB L3。

## 2000 系列：Zen+ 与 X399

| 型号 | 架构 | 核心/线程 | 基础/加速 GHz | L3 | TDP | PCIe/平台 |
|---|---|---:|---:|---:|---:|---|
| 2990WX | Zen+, 12nm | 32/64 | 3.0/4.2 | 64MB | 250W | 64 lanes PCIe 3.0，sTR4/X399 |
| 2970WX | Zen+, 12nm | 24/48 | 3.0/4.2 | 64MB | 250W | 64 lanes PCIe 3.0，sTR4/X399 |
| 2950X | Zen+, 12nm | 16/32 | 3.5/4.4 | 32MB | 180W | 64 lanes PCIe 3.0，sTR4/X399 |
| 2920X | Zen+, 12nm | 12/24 | 3.5/4.3 | 32MB | 180W | 64 lanes PCIe 3.0，sTR4/X399 |

四款 2000 系列继续兼容 X399，但 WX 的 24/32 核拓扑可能让部分线程访问远端 die 上的内存或 I/O。旧软件调度器、Windows 版本、NUMA/UMA 模式和 Ryzen Master 的 Legacy Compatibility Mode 都可能影响实际表现。用于虚拟化或编译农场时，应记录 NUMA node 数、内存交错和线程绑定，而不是只看总核心数。

## 3000 系列：Zen 2、sTRX4 与 TRX40

| 型号 | 架构 | 核心/线程 | 基础/加速 GHz | Total Cache | TDP | PCIe/平台 |
|---|---|---:|---:|---:|---:|---|
| 3960X | Zen 2, 7nm | 24/48 | 3.8/4.5 | 140MB | 280W | 88 total/72 usable PCIe 4.0，sTRX4/TRX40 |
| 3970X | Zen 2, 7nm | 32/64 | 3.7/4.5 | 144MB | 280W | 88 total/72 usable PCIe 4.0，sTRX4/TRX40 |
| 3990X | Zen 2, 7nm | 64/128 | 2.9/4.3 | 288MB | 280W | 88 total/72 usable PCIe 4.0，sTRX4/TRX40 |

第三代换到新的 sTRX4/TRX40，不与 X399 主板兼容。官方发布材料把 CPU 加 TRX40 芯片组的 lane 总数写为 88、可用数写为 72；这不是“CPU 直连给扩展卡的 88 lanes”。做 GPU/NVMe 拓扑规划时必须读主板框图，确认哪些槽走 CPU、哪些经过 chipset uplink。

## Threadripper PRO 3000WX：Zen 2、sWRX8 与 WRX80

| 型号 | 架构 | 核心/线程 | 基础/加速 GHz | Total Cache | TDP | 平台能力 |
|---|---|---:|---:|---:|---:|---|
| PRO 3995WX | Zen 2, 7nm | 64/128 | 2.7/4.2 | 288MB | 280W | 128 lanes PCIe 4.0，8 通道 DDR4-3200 |
| PRO 3975WX | Zen 2, 7nm | 32/64 | 3.5/4.2 | 144MB | 280W | 128 lanes PCIe 4.0，8 通道 DDR4-3200 |
| PRO 3955WX | Zen 2, 7nm | 16/32 | 3.9/4.3 | 72MB | 280W | 128 lanes PCIe 4.0，8 通道 DDR4-3200 |
| PRO 3945WX | Zen 2, 7nm | 12/24 | 4.0/4.3 | 70MB | 280W | 128 lanes PCIe 4.0，8 通道 DDR4-3200 |

PRO 3000WX 的关键差异不是单纯多几个核心：官方平台提供 8 通道 ECC UDIMM/RDIMM/LRDIMM、最高 2TB、128 条 PCIe 4.0 和 AMD PRO 管理/安全能力。它使用 sWRX8/WRX80，不能把普通 3990X 的 sTRX4/TRX40 主板当作兼容替代。

## 对本地 AI 和二手采购的意义

- 1000/2000 系列的 PCIe 3.0 x16 对单张 RTX 3090 通常不是推理主瓶颈，但多卡跨 NUMA、CPU offload 和数据预处理更容易暴露旧平台延迟。
- 3000/PRO 3000WX 带来 PCIe 4.0；PRO 的 8 通道内存更适合大规模 CPU offload，但内存访问仍远慢于 GPU 本地显存。
- 3990X 与 3995WX 都是 64 核 Zen 2，后者是 PRO 平台产品。二者 socket、内存通道、PCIe lanes、主板和管理能力不同。
- 二手采购必须同时核对 CPU、主板 BIOS、RDIMM/UDIMM 类型、散热器扣具和电源。sTR4、sTRX4、sWRX8 名称接近但不可互换。

## 官方来源

- [AMD 2017 Threadripper 1000 lineup](https://www.amd.com/en/newsroom/press-releases/2017-7-30-ultimate-boost-for-high-end-desktop-market-with-a.html)
- [AMD 2018 Threadripper 2000 lineup](https://www.amd.com/en/newsroom/press-releases/2018-8-13-amd-launches-world-s-most-powerful-desktop-process.html)
- [AMD 2019 Threadripper 3960X/3970X launch](https://www.amd.com/en/newsroom/press-releases/2019-11-7-amd-introduces-world-s-fastest-high-end-desktop-pr.html)
- [AMD 2020 Threadripper 3990X specification](https://www.amd.com/en/newsroom/press-releases/2020-1-6-amd-announces-world-s-highest-performance-desktop-.html)
- [AMD 2020 Threadripper PRO 3000WX lineup](https://www.amd.com/en/newsroom/press-releases/2020-7-14-amd-announce-world-s-first-64-core-pro-workstation.html)
