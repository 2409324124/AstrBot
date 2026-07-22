# 代表案例：AMD EPYC 7742 Rome 的 NUMA、内存、HPC 与 CFD 实测

## 适合回答什么

这是一篇“第二代 EPYC 7002 / Rome 性能如何”的具体实例。简短回答可以先说：Rome 用中心 I/O die、8 个 CCD、8 通道 DDR4-3200 和 PCIe 4.0，把单颗核心数提高到 64；它的节点吞吐和总内存带宽很强，但每核心带宽较低，内存受限程序不一定适合把全部核心都占满。用户要求例子或详细报告时，再引用下面 NASA Aitken、MPDATA 与 HLRS OpenFOAM 的测试环境和数字。

## 型号与微架构

EPYC 7742 是 Rome 顶级通用型号之一：64 核 128 线程、2.25GHz 基础/3.40GHz 加速、256MB L3、225W，支持单路或双路。单颗由 8 个 CCD 和一个中心 I/O die 组成；每个 CCD 有两个 4 核 CCX，每个 CCX 共享 16MB L3，因此它是统一内存控制器下的分片末级缓存结构，不应把“一个 NUMA node”理解成“所有核心访问所有 L3 延迟相同”。

## NUMA、NPS 与内存拓扑

每颗 7742 有 8 个 DDR4-3200 内存通道和四个逻辑象限，每个象限包含两个 CCD、两个内存通道和 32 条 I/O lanes。BIOS 可以配置：

- NPS1：每 socket 一个 NUMA domain，内存在八通道间交错；调度简单。
- NPS2：每 socket 两个 NUMA domains。
- NPS4：每 socket 四个 NUMA domains，每个域对应一个逻辑象限和两个内存通道；适合显式绑核、绑内存的 MPI/NUMA-aware 程序。
- L3 cache as NUMA：还可把每个 CCX 的 L3 slice 暴露成域；双路 7742 最多可能显示 32 个 NUMA domains，但会显著增加调度与内存放置复杂度。

NPS2/NPS4 在部分带宽测试中可略优于 NPS1，但不是无条件更快。程序若跨域频繁访问、MPI rank 和内存页放置不匹配，更多 NUMA domains 反而会增加远端访问。

## 测试环境：NASA Aitken

NASA NAS-2022-01 的主案例使用 HPE Apollo 9000 Rome 节点：

| 项目 | Rome 节点 | 对照 Cascade Lake 节点 |
|---|---|---|
| CPU | 2×EPYC 7742，128物理核 | 2×Xeon Gold 6248，40物理核 |
| 内存 | 512GB，DDR4-3200，8通道/socket | 192GB，DDR4-2933，6通道/socket |
| NUMA | NPS4，4域/socket | 1域/socket |
| 网络 | 双端口 HDR，200Gbit/s | 双端口 EDR，100Gbit/s |
| OS | SLES 15 SP2 | SLES 12 SP5 |
| 编译/MPI | GCC 8.2/10.2、Intel 2018/2020、HPE MPT 2.23 | 同报告所列工具链 |

这不是只换 CPU 的严格平台 A/B：内存容量、网络、OS 和节点核心数同时变化。因此它适合回答“整节点能力”，不适合把全部差异归因于 7742 单颗 CPU。

## 结果一：STREAM 与内存饱和

STREAM 使用 non-temporal stores，并把线程均匀铺到 NUMA domains。Rome 从单核约 35GB/s，上升到 8、16、32 核时约 275、348、346GB/s；128 核全部使用时约 320GB/s。NPS4 下，8 的倍数通常形成峰值，说明线程是否均匀覆盖内存控制器非常重要。

对照 Cascade 节点 40 核约 212GB/s；全节点 Rome 为约 1.50 倍。但是每核心 EP-STREAM 是 Rome 2.5GB/s、Cascade 5.3GB/s。Rome 约 16 个线程就能接近带宽饱和，Cascade 需要约 22–24 个线程。这给出一个实用结论：对于稀疏矩阵、有限元装配/求解等带宽受限阶段，7742 上保留部分核心空闲或每节点并行运行多个任务，可能比单任务占满 128 核更有效。

## 结果二：HPL、HPCG 与科学应用

- HPL：Rome 使用每个 MPI rank 4 个 OpenMP threads 的混合配置，相对纯 MPI 性能提高 6.5%，内存用量减少 3.5%。报告使用 MKL 2018.3.222 和 `MKL_DEBUG_CPU_TYPE=5` 打开 AMD AVX2 路径；该技巧对较新 MKL 不再成立，复现时应改用 AOCL/BLIS 或当前支持 AMD 的数学库。
- 参考 HPCG：1–8 节点范围内，Rome 比 Cascade 高 54–57%，与节点 STREAM 带宽优势接近。HPCG 只达到约 0.9% 理论峰值，说明稀疏共轭梯度/多重网格的瓶颈与 HPL 稠密矩阵完全不同。
- HPCC：Rome 的 G-FFT 为 68Mflop/s、Cascade 为 33Mflop/s；PTRANS 为 21GB/s 对 14GB/s。相反，按核心计算的 EP-STREAM 与 DGEMM 更偏向 Cascade。
- 9 个单节点生产应用的 Rome/Cascade 加速范围为 1.37–3.08 倍，几何平均约 2.23 倍；固定核心数比较时，Cascade 单核通常是 Rome 的 1.08–1.39 倍。LAMMPS LJ melt 的节点增益约 2.90 倍，接近核心数比例。

因此“Rome 很快”应明确口径：每节点吞吐通常很强，每核心性能与每核心带宽未必强；工作负载、并行粒度和许可证按核计费方式会改变采购结论。

## CFD/OpenFOAM 例子

HLRS Hawk 使用每节点 2×EPYC 7742、256GB 和 HDR200，OpenFOAM v2112/v2212 由 GCC 10.2 与 HPE MPT 2.26 构建。研究发现，不同网格每 MPI rank 的元素数会造成显著的缓存甜点：多数平台约在每 rank 10k 元素附近达到峰值；Hawk 的一个案例约在 15k elements/rank 附近表现最好，甜点相对最大网格的节点性能差达到 438%。

这不是“加节点凭空多出算力”，而是问题切分后工作集更适合 16MB CCX L3 slice，主存访问减少。对 OpenFOAM、有限体积 CFD 和类似 stencil 求解器，应该同时扫描 MPI ranks、每 rank 网格量和 NUMA 绑定，而不能只画核心数强扩展曲线。

## 对有限元与 CAE 的可迁移结论

NASA 报告的 HPCG 是稀疏 CG/多重网格代理，OpenFOAM 是有限体积 CFD，不是 ANSYS/Abaqus 的直接有限元成绩。可迁移的是瓶颈判断：

- 稠密直接求解、向量化良好的计算阶段更接近 HPL，能利用更多核心。
- 稀疏迭代求解、装配和大网格访存更接近 HPCG/STREAM，常受内存通道和 NUMA 放置限制。
- 模型能否落入每 CCX 16MB L3、每 rank 元素量和跨 socket 通信会显著改变扩展曲线。

若用户问某个具体有限元软件，应继续匹配相同求解器、模型规模、版本和许可证设置的报告，而不是把这里的 HPCG 数字当作 ANSYS/Abaqus 分数。

## 限制与检索提示

检索别名：EPYC Rome、EPYC 7002、7742、第二代 EPYC、NPS4、Aitken、NASA Rome、HPCG、STREAM、OpenFOAM、CFD、有限元类似负载、稀疏求解器。

所有绝对数字只对应上述节点和软件栈。NASA 的 Rome/Cascade 对照同时改变核心数、网络、内存和 OS；HLRS 的 438% 是网格甜点相对特定大网格，不是 7742 对任意 CPU 的通用加速比。

## 官方与原始来源

- [AMD EPYC 7002 official datasheet](https://www.amd.com/content/dam/amd/en/documents/products/epyc/amd-epyc-7002-series-datasheet.pdf)
- [NASA NAS Technical Report NAS-2022-01](https://www.nas.nasa.gov/assets/nas/pdf/papers/NAS_Technical_Report_NAS-2022_01.pdf)
- [IPDPSW 2022 paper DOI](https://doi.org/10.1109/IPDPSW55747.2022.00141)
- [TPDS: Architectural Adaptation and Performance-Energy Optimization for CFD Application on AMD EPYC Rome](https://doi.org/10.1109/TPDS.2021.3078153)
- [Understanding Superlinear Speedup in Current HPC Architectures](https://doi.org/10.20944/preprints202404.0219.v1)
