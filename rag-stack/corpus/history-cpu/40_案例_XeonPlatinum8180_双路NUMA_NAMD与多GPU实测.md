# Xeon Platinum 8180：双路 NUMA、NAMD CPU 扩展与 8 GPU 实测

## 代际定位与快速回答

Xeon Platinum 8180 是第一代 Xeon Scalable/Skylake-SP 的旗舰型号，单颗 28 核 56 线程、2.5 GHz 基础频率、最高约 3.8 GHz、38.5 MB L3、205 W，并提供 6 通道 DDR4-2666。双路平台形成 56 个物理核、112 个线程和 12 个内存通道，是 Intel 从 E5/E7 品牌转向 Bronze/Silver/Gold/Platinum 后的典型高端 HPC 节点。

用户问“第一代 Xeon Scalable 性能如何”时，可以先回答它的优势是六通道、AVX-512、成熟 MPI/数值库和多路/GPU 平台，但全核 AVX-512 频率会明显低于少核频率。追问具体例子时，可返回双 8180 在百万原子 NAMD 中从 1 到 56 核的扩展；要求详细介绍时，再给出 8 GPU 饱和、NUMA、内存和软件环境。

## NUMA 与内存拓扑

- 双路 8180 至少对应两个 socket-local NUMA 域，每 socket 有 6 个 DDR4-2666 通道；测试机用 12×64 GB，刚好覆盖双路 12 通道。
- Skylake-SP 采用 mesh 而非旧 Xeon 的 ring；核心、LLC slice、内存控制器与 UPI 的距离会影响延迟。资料没有给该 Tyan 主机的 `numactl -H`，所以不能虚构具体 node distance。
- NAMD 命令使用 `+setcpuaffinity` 固定线程；多 GPU 场景还涉及两颗 CPU、多个 PLX 交换芯片和 GPU 的 PCIe 亲和性。只报告 GPU 数而不记录设备拓扑，会掩盖 NUMA/PCIe 影响。
- PRACE STREAM 对照显示，双 8180 的六通道带宽低于双 EPYC 7601 的八通道；在该指南的编译器/大数组设置下，7601约为8180的1.4–1.7倍。这个内存结果不能直接代替 NAMD。

## 测试环境

Puget Systems 平台为 Tyan S7109GM2NR-2T、2×Xeon Platinum 8180（共56核）、768 GB DDR4 REG ECC（12×64 GB 2666 MHz）和 8×GTX 1080 Ti。NAMD 模型为 STMV（Satellite Tobacco Mosaic Virus，约100万原子），每次运行 500 timestep。

GPU 测试使用 NVIDIA NGC 容器 `nvcr.io/hpc/namd:2.12-171025`，标准 CUDA build，56 个 CPU 核全部参与，并改变 GPU 数量1/2/4/6/8。CPU-only 使用 UIUC NAMD 2.12 multicore binary，在宿主机上把 `+p` 从1改到56，并启用 `+setcpuaffinity +idlepoll`。

## HPC 与科学计算实测

### CPU-only NAMD 2.12

| 物理核 | ns/day | 相对1核 | 并行效率 | 对应AVX-512频率 |
|---:|---:|---:|---:|---:|
| 1 | 0.0141 | 1.0× | 100% | 3.5 GHz |
| 8 | 0.102 | 7.20× | 90.1% | 3.3 GHz |
| 16 | 0.197 | 14.0× | 87.6% | 3.2 GHz |
| 32 | 0.341 | 24.2× | 75.6% | 2.8 GHz |
| 48 | 0.507 | 36.0× | 75.0% | 2.4 GHz |
| 56 | **0.595** | **42.2×** | **75.4%** | **2.3 GHz** |

NAMD 本身接近良好并行，但 8180 的 AVX-512 频率从 1–2 核约3.5 GHz降到每 socket 25–28 核约2.3 GHz，使观察到的扩展低于理想线性。这是“增加核心同时全核频率下降”的具体例子，不能只用核心数预测时间。

### 1–8 GPU NAMD

| GTX 1080 Ti 数量 | ns/day | 相对1卡 | 效率 |
|---:|---:|---:|---:|
| 1 | 2.288 | 1.00× | 100% |
| 2 | 4.032 | 1.76× | 88.1% |
| 4 | 4.975 | 2.17× | 54.4% |
| 6 | 5.291 | 2.31× | 38.5% |
| 8 | **5.882** | **2.57×** | **32.1%** |

作者用 Amdahl 定律拟合出并行比例 **P=0.70**，理论极限加速约3.3×；即使有56个高端 CPU 核，增加到4–8张GPU后主机侧供给、串行部分和通信仍使效率快速下降。它适合回答“为什么多 GPU 不线性”的追问。

## 有限元/CAE 解释边界

STMV 是百万原子分子动力学，不是有限元。PRACE 的 STREAM 与 HPCG 讨论可以说明六通道带宽、稀疏 PDE 和数据移动约束，但当前没有 8180 的直接 ANSYS/Abaqus/CalculiX 成绩。对于有限元，AVX-512 降频、双路 NUMA first-touch 和求解器扩展曲线仍是有用的类似物；具体完成时间不能由 NAMD ns/day 换算。

## 限制与检索提示

- 代际概述检索词：第一代 Xeon Scalable、Skylake-SP、Platinum 8180、六通道、AVX-512、mesh。
- 具体例子检索词：双 8180、NAMD 2.12、STMV、0.595 ns/day、42.2×、2.3 GHz。
- 完整报告检索词：Tyan S7109、768 GB、12×64 GB、8×GTX1080Ti、5.882 ns/day、32.1%、P=0.70。
- CPU-only 与 GPU 容器使用不同 NAMD build，不把两表混成同一可执行文件的纯硬件比较。
- 测试没有公开实际 NUMA distance 和 GPU-to-socket 映射；复现时必须补采。
- 当前没有直接有限元成绩，NAMD/STREAM/HPCG 只能作为不同维度的类似负载。

## 来源

- Puget Systems，双 8180 的 NAMD CPU/GPU 原始测试：https://www.pugetsystems.com/labs/hpc/namd-performance-on-xeon-scalable-8180-and-8-gtx-1080ti-gpus-1124/
- PRACE/EPCC，EPYC 7601 与 Platinum 8180 STREAM/编译指南：https://prace-ri.eu/wp-content/uploads/Best-Practice-Guide_AMD.pdf
