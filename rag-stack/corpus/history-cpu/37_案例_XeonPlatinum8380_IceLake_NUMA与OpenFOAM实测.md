# Xeon Platinum 8380：Ice Lake NUMA、OpenFOAM 与 HPC 应用实测案例

## 代际定位与快速回答

Xeon Platinum 8380 是第三代 Xeon Scalable/Ice Lake-SP 的 40 核旗舰代表：40 核 80 线程、2.3 GHz 基础频率、最高 3.4 GHz、60 MB L3、270 W。相对第二代 Cascade Lake，平台从每 socket 6 通道 DDR4-2933 提升到 8 通道 DDR4-3200，并加入 PCIe 4.0；这对 OpenFOAM 等内存带宽敏感应用比单看核心数更重要。

用户问“Ice Lake Xeon 总体性能如何”时，可以先说它以更多核心、八通道和成熟 AVX-512 软件栈显著提高多线程 HPC，但不同应用结果分化：LULESH、NAMD、GROMACS、OpenFOAM 和 Quantum Espresso 不会按同一比例加速。追问具体例子时给出 Intel 的 OpenFOAM 代际比值；要求详细介绍时，再给出双路内存插法、系统版本和 Phoronix 的 110 项独立测试结论。

## NUMA 与内存拓扑

- 双路 8380 至少形成两个 socket-local 内存域，每 socket 有 8 个 DDR4-3200 通道；两颗合计 16 通道。
- Ice Lake-SP 可通过固件的 Sub-NUMA Clustering 把一个 socket 进一步划分为更小的局部域，但具体是否启用、Linux 暴露 2 个还是更多 NUMA node，必须以测试机 BIOS 和 `numactl -H` 为准。
- Intel OpenFOAM 报告的 8380 配置为 16×16 GB，Phoronix 为 16×32 GB；两者都填满双路的 16 个通道，但容量分别是 256 GB 和 512 GB。
- 资料没有提供两台机器的 NUMA distance 矩阵，因此不能把其他 Ice Lake 服务器的节点距离复制给这两个测试。对复现实验，应记录 SNC、HT、Turbo、first-touch 与 MPI rank 绑定。

## 测试环境

### Intel OpenFOAM 厂商测试

平台为 Coyote Pass、2×Platinum 8380（每颗 40 核、2.3/3.4 GHz、270 W）、16×16 GB DDR4-3200（256 GB）、Intel 960 GB SSD、CentOS 8.4、kernel 4.18、HT on、Turbo on、Mellanox HDR 200Gb/s。报告图表以第一代 Platinum 8160 为 1.00，比较第二代 8280 和第三代 8380。

该图表的不同代际使用了不同采集日期、OpenFOAM 版本和系统环境，因此适合做厂商代际案例，不适合拆解成纯 IPC、纯内存或纯核心数收益。

### Phoronix 独立测试

Intel reference server 配置 2×8380、16×32 GB DDR4-3200 Hynix（512 GB）和 Micron 9300 3.8 TB NVMe；系统为 Ubuntu 20.04、Linux 5.11、performance governor。所有对照服务器都使用各自平台支持的最大内存通道数和额定频率，并统一存储盘。总计运行 **110 项测试**，对照包括双 Platinum 8280 与双 EPYC 7763/7713/75F3。

## HPC 与工程仿真实测

### OpenFOAM

Intel 厂商图表的相对性能为：Platinum 8160 = **1.00**、Platinum 8280 = **1.10**、Platinum 8380 = **1.67**。报告把 OpenFOAM 定义为高度内存带宽敏感，并指出第三代平台具有 8 通道 DDR4-3200，而第二代是 6 通道 DDR4-2933。

这个 1.67 是对 8160 的整机代际比值，不是“8380 比 8280 快 67%”；按图表比值，8380/8280 约为 1.52，但由于环境不完全一致，也只能作为该厂商报告内部的参考。

Phoronix 的统一 Ubuntu 测试则给出不同视角：OpenFOAM 在所测配置中仍由 AMD EPYC 处理器领先。两组资料并不矛盾——一个说明 8380 相比旧 Xeon 大幅进步，另一个说明它在同代跨厂商 CFD 中未必最快。

### LULESH、NAMD、GROMACS 与 Quantum Espresso

Phoronix 正文报告：双 8380 在 LULESH 水动力学代理中领先该批对照；NAMD 2.14 大致接近 EPYC 7713；GROMACS 位于 EPYC 7713 与 7763 之间；Quantum Espresso 落后所测 Zen 3，但相对双 8280 有明显提升。这些是同一 Ubuntu/Linux 5.11 测试批次的定性结论，图表绝对值未可靠提取，因此知识库不猜测数值。

### HPCG 与有限元边界

Phoronix 测试套件包含 HPCG，Intel 也提供 8380 集群的 oneMKL HPCG 运行指南，但当前可访问正文没有给出可核对的 8380 绝对 HPCG 成绩。LULESH 是显式冲击水动力学代理，OpenFOAM 是直接 CFD；二者都可帮助回答工程仿真问题，但都不是 ANSYS/Abaqus/CalculiX 结构有限元完成时间。

如果用户问“8380 做有限元是否好”，合理回答是八通道、40 核和成熟 Intel 编译器有利于并行求解，但 NUMA 绑定、许可证、稀疏直接/迭代算法和模型内存占用会决定扩展曲线；随后应明确当前案例只有 CFD/HPC 类似负载，没有直接结构有限元成绩。

## 限制与检索提示

- 代际概述检索词：第三代 Xeon Scalable、Ice Lake-SP、Sunny Cove、八通道、PCIe 4.0。
- 具体例子检索词：Platinum 8380、OpenFOAM、8160=1.00、8280=1.10、8380=1.67。
- 完整报告检索词：Coyote Pass、16×16 GB、16×32 GB、Ubuntu 20.04、Linux 5.11、110 项测试、LULESH、NAMD 2.14。
- 实际 NUMA node 数和 SNC 状态必须在目标服务器验证；两个来源都没有给 distance matrix。
- Intel 图表属于厂商结果且代际环境不完全一致；Phoronix 提供更统一的跨平台对照，但正文趋势没有绝对图表值。
- 本案例有 OpenFOAM 与 LULESH 工程/HPC 负载，没有直接结构有限元成绩。

## 来源

- Intel，OpenFOAM on Intel Xeon Scalable Processors：https://www.intel.com/content/dam/www/central-libraries/us/en/documents/2022-05/openfoam-scalable-processors-brief.pdf
- Phoronix，双 Xeon Platinum 8380 Linux 独立测试：https://www.phoronix.com/review/intel-xeon-8380-linux
