# Threadripper 2990WX：非对称 NUMA、HPL 与 NAMD 实测案例

## 代际定位与快速回答

Ryzen Threadripper 2990WX 属于第二代 Threadripper、Colfax 平台。AMD 官方规格为 32 核 64 线程、3.0 GHz 基础频率、最高 4.2 GHz、64 MB L3、250 W TDP、sTR4 插槽和四通道 DDR4-2933。它适合回答“第二代 Threadripper 为什么有时核心很多却不一定快”这一类问题：决定性能的不只是 32 核，而是四个 die 中只有两个直接连接内存控制器，另外两个必须跨 die 访问内存。

因此，2990WX 是一个很典型的非对称内存局部性案例。操作系统、BIOS 的 UMA/NUMA 设置以及线程和内存页放置都会影响结果。AMD 为 WX 型号提供的 Dynamic Local Mode 会优先把繁忙线程调度到具有本地内存访问路径的 die；它不是增加内存通道，而是调度层面的缓解措施。

## NUMA 与内存拓扑

- 封装内有 4 个 die、8 组 L3 cache/核心簇；其中两个 die 直接连接四通道内存，两个计算 die 通过 Infinity Fabric 远程访存。
- 固件与操作系统模式可能把拓扑呈现为 UMA 或多个 NUMA node，所以不能脱离 `lscpu`、`numactl -H` 和 BIOS 设置声称某台机器固定暴露几个节点。
- 对线程独立、缓存命中率高的任务，远程访存影响可能较小；对稀疏矩阵、网格求解、频繁分配内存的任务，跨 die 延迟和有限的四通道带宽更容易成为瓶颈。
- 这也解释了为什么按 L3 cache 绑定 MPI rank 比任意调度更适合 HPL：它让线程组尽量在共享缓存和明确的核心簇内工作。

## 测试环境

Puget Systems 的 HPL 测试平台为 Threadripper 2990WX、Gigabyte X399 AORUS XTREME-CF、128 GB DDR4-2666、Samsung 970 Pro 512 GB；软件为 Ubuntu 18.04、GCC 7.3、AMD BLIS 1.2、Open MPI 3.1、HPL 2.2。测试者尝试了多种映射后，最佳配置是 8 个 MPI rank，每个 rank 使用 4 个 OpenMP 线程，并通过 `--map-by l3cache` 按 L3 cache 绑定。

NAMD 测试使用同类 X399 平台、128 GB DDR4-2666、Ubuntu 18.04 和 NAMD 2.13，CPU-only 与 RTX 2070/2080 Ti 加速配置均运行 500 timestep。报告还包含 2970WX 和双 Xeon 8180 的对照，但图表中的 2990WX 精确 day/ns 数值没有可靠的机器可读文本，因此本案例只保存正文明确数字和趋势。

## HPC 与科学计算实测

### HPL 2.2

最佳命令核心为 `mpirun -np 8 --map-by l3cache ... xhpl`，即 8 MPI rank × 4 OpenMP 线程。实测结果为 **596.5 GFLOP/s**。这个数字反映 BLIS 优化后的稠密双精度线性代数上限，不代表稀疏有限元求解器，也不能和不同 BLAS、矩阵规模或功耗设置的结果直接横比。

### NAMD 2.13

CPU-only 测试随线程增加表现出较均匀扩展，且该负载使用 SMT 时仍有收益。加入 GPU 后，单张 RTX 2070 相比 CPU-only 接近 5 倍加速；当增加到两张以上 RTX 2070/2080 Ti 时，总体只继续获得有限收益，报告认为 CPU 与主机侧供给已经限制 GPU。它适合作为“高核数并不自动意味着能喂满多张 GPU”的具体例子。

### 有限元与稀疏求解解释

当前来源没有给出 2990WX 的 ANSYS、Abaqus、CalculiX 或 Code_Aster 直接有限元成绩，不能把 596.5 GFLOP/s 写成有限元性能。可以把其非对称 NUMA、跨 die 远程访存和四通道带宽作为稀疏有限元的风险解释；需要数值时，应检索同代的直接 CAE 报告，或者明确引用 HPCG/稀疏 PDE 作为“类似负载”而非直接有限元。

## 限制与检索提示

- 代际概述检索词：第二代 Threadripper、Zen+、Colfax、WX、四通道、非对称 NUMA。
- 具体例子检索词：2990WX、596.5 GFLOP/s、8 MPI rank、4 OpenMP、BLIS 1.2、HPL 2.2。
- 完整报告检索词：两个直连内存 die、两个远程访存 die、Dynamic Local Mode、L3 cache 绑核、NAMD 2.13。
- “四 die”描述的是物理局部性；实际 NUMA node 数必须以目标机器的 BIOS 与操作系统输出为准。
- 本文有 HPL 与 NAMD 实测，但没有直接有限元成绩；任何 CAE 推断都必须标注为相似性分析。

## 来源

- AMD 官方规格：https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen-threadripper/ryzen-threadripper-2000-series/amd-ryzen-threadripper-2990wx.html
- Puget Systems，HPL 环境、绑核方法和 596.5 GFLOP/s 原始报告：https://www.pugetsystems.com/labs/hpc/how-to-run-an-optimized-hpl-linpack-benchmark-on-amd-ryzen-threadripper-2990wx-32-core-performance-1291/
- Puget Systems，NAMD 2.13 CPU/GPU 扩展测试：https://www.pugetsystems.com/labs/hpc/amd-threadripper-and-1-4-nvidia-2080ti-and-2070-for-namd-molecular-dynamics-1321/
- AMD，Dynamic Local Mode 发布说明：https://www.amd.com/en/newsroom/press-releases/2018-10-29-amd-expands-2nd-generation-ryzen-threadripper-de.html
