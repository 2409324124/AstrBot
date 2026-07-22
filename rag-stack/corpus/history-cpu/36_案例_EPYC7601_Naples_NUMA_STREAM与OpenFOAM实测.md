# EPYC 7601：Naples NUMA、STREAM 与 OpenFOAM 实测案例

## 代际定位与快速回答

EPYC 7601 是第一代 EPYC/Naples 的旗舰代表，规格为 32 核 64 线程、2.2 GHz 基础频率、最高 3.2 GHz、64 MB L3、180 W，支持单路和双路。Naples 的关键不是简单的“32 核”，而是每颗处理器由 4 个 8 核 die 组成，每个 die 对应本地内存和 I/O 路径；双路系统通常形成更深的 NUMA 局部性。

如果用户只问“第一代 EPYC 性能如何”，应先回答它用 8 通道内存和大量 PCIe 资源换取很强的带宽与吞吐，但线程放置、内存 first-touch 和跨 socket 访问十分重要。追问例子时，可给出 7601 的 STREAM 约 149 GB/s 单路、290 GB/s 双路以及 OpenFOAM 1906 的双路测试；要求详细介绍时再展开距离矩阵、编译器和模型规模。

## NUMA 与内存拓扑

PRACE/EPCC 的双路 7601 实机示例通过 `numactl --hardware` 暴露 **8 个 NUMA node**，即每 socket 4 个。其距离矩阵中，本地距离为 **10**，同 socket 的其他 die 为 **16**，跨 socket 为 **32**。这使 Naples 成为典型的“层次化 NUMA”平台：同一插槽内的远程内存已经有额外代价，跨插槽代价更高。

指南建议 MPI rank 尽量放在能使用本地 NUMA bank 的核心上。OpenMP 更棘手，因为同一进程内的线程共享地址空间，一个线程可能遍历其他节点 first-touch 的内存页。适合该平台的验证包括 `numactl -H`、按 NUMA node 绑核、并行初始化数组，以及比较 local/remote bandwidth。

注意：8 个节点是该双路测试机的实例，不保证所有 BIOS/操作系统配置都完全相同。PRACE 文中还把启用 SMT 后的 128 个逻辑线程写成“128 cores”，本文按硬件规格纠正为双路 64 物理核/128 线程。

## 测试环境

### AMD STREAM 报告

AMD Ethanol reference system 使用 Ubuntu 16.04、Open64 4.5.2.1。单路配置为 1×7601、256 GB（8×32 GB dual-rank DDR4-2666）；双路配置为 2×7601、512 GB（16×32 GB）。对照为双 E5-2690 v4、256 GB，但使用 GCC 6.3 且 DDR4-2666 实跑 2400，因此该对比同时包含处理器、内存容量/频率和编译器差异。

### OpenFOAM 报告

双路 7601 节点为 64 物理核、256 GB（16×16 GB dual-rank DDR4-2666）、Mellanox ConnectX-5 EDR 100Gb/s、RHEL 7.6；SMT off、boost on、performance governor。OpenFOAM 1906 由 GCC 9.2 和 OpenMPI 3.1.4 编译。测试包括 motorbike 100×40×40、motorbike 130×52×52、DrivAer 32m 和 DrivAer 64m，每个模型运行 3 次取平均。

## HPC 与工程仿真实测

### STREAM

单路 7601 的 Copy/Scale/Add/Triad 分别为 **147,875 / 147,951 / 149,710 / 149,375 MB/s**；双路分别为 **282,818 / 286,313 / 291,532 / 290,228 MB/s**。双 E5-2690 v4 对照 Triad 为 118,015 MB/s，AMD 报告据此给出双路 7601 高 **146%** 的厂商结论。

这些结果可以说明 Naples 的 8 通道带宽，但不能把 146% 当作所有应用的通用加速。尤其对照系统编译器和 DIMM 配置不同，知识库必须连同环境一起返回。

PRACE 的独立最佳实践指南另用 STREAM 5.1.0、GNU 7.2 与 Intel 18.0.1、`STREAM_ARRAY_SIZE=800000000` 测试双 7601 与双 Platinum 8180，报告称在 Intel 编译器下 7601 约为 8180 的 1.4–1.7 倍。图中没有机器可读绝对值，因此只保留范围。

### OpenFOAM 1906

AMD 把双路 7601 作为第一代基线，与双路 EPYC 7532 比较上述四个 CFD 模型。图表给出的总体表述是 7532 相比 7601 约 **27% 改善**。这不是 7601 的绝对秒数，却是同一报告内、明确模型和三次均值方法下的代际 CFD 参照。

OpenFOAM 是直接 CFD/工程仿真，而不是有限元。报告说明其可覆盖流动、湍流、传热、声学、固体力学与电磁问题，但本次测试实际运行的是 motorbike/DrivAer 流体模型，不能据此声称验证了结构有限元。

### HPCG 与有限元类似负载

PRACE 指南讨论了在 7601 上编译 HPCG 的选项以及稀疏矩阵/大向量对带宽的依赖，但没有提供可核对的 7601 HPCG 绝对成绩。这里把 NUMA 距离、STREAM 和 OpenFOAM 作为真实证据；若用户要求有限元数值，应继续寻找 CalculiX、Code_Aster、ANSYS 或 Abaqus 原始测试，不能用 STREAM 替代。

## 限制与检索提示

- 代际概述检索词：EPYC 7001、Naples、四 die、八通道、层次化 NUMA、Infinity Fabric。
- 具体例子检索词：EPYC 7601、149,375 MB/s、290,228 MB/s、STREAM Triad、146%。
- 完整报告检索词：8 NUMA node、距离 10/16/32、OpenFOAM 1906、motorbike、DrivAer 32m/64m。
- STREAM 的厂商对照编译器和内存配置不一致；只允许在报告原环境中引用。
- OpenFOAM 是直接 CFD，而 HPCG/稀疏矩阵只是有限元类似负载；当前没有 7601 直接结构有限元成绩。

## 来源

- AMD，EPYC 7601 双路 STREAM 原始报告：https://www.amd.com/content/dam/amd/en/documents/epyc-business-docs/performance-briefs/AMD-EPYC-SoC-Delivers-Exceptional-Results.pdf
- AMD，EPYC 7601/7532 OpenFOAM 1906 原始测试：https://www.amd.com/content/dam/amd/en/documents/epyc-business-docs/solution-briefs/AMD-EPYC-7002-OpenFOAM.pdf
- PRACE/EPCC，AMD EPYC Best Practice Guide：https://prace-ri.eu/wp-content/uploads/Best-Practice-Guide_AMD.pdf
