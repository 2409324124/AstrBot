# 代表案例：Threadripper 3970X 的 NUMA、HPL、HPCG 与 NAMD 实测

## 适合回答什么

这是一篇“Threadripper 3000 / 3970X 做 HPC、仿真或本地计算怎么样”的具体实例。结论不是简单的“32 核很快”：3970X 的 Zen 2 计算能力和32核扩展性很好，HPL 与 NAMD 能有效使用大量核心；但它只有四通道内存，HPCG 这类稀疏、带宽受限负载在约8核后就明显触顶。对有限元/CAE，要先判断求解器是计算受限还是内存受限。

## 型号、芯片与 NUMA 拓扑

3970X 为 Zen 2、32核64线程、3.7/4.5GHz、128MB L3、280W，使用 sTRX4/TRX40。它由4个8核 CCD 和中心 I/O die 组成，每个 CCD 含两个4核 CCX，每个 CCX共享16MB L3；四通道 DDR4 和 PCIe 4.0 都接到中心 I/O die。

与2990WX不同，3970X不再有“部分计算 die 没有直连内存”的拓扑。多数操作系统把它呈现为一个 NUMA node，因此不需要2990WX那种本地/分布式内存模式切换。但单 NUMA node 不代表缓存访问完全均匀：线程在CCX间迁移仍会失去本地L3数据，长时间计算应固定线程并保持 first-touch 内存初始化。

## 测试环境

Puget Systems 的同机测试配置为：

| 项目 | 配置 |
|---|---|
| CPU | Threadripper 3970X，32核，约3.8GHz全核频率 |
| 主板 | Gigabyte TRX40 AORUS |
| 内存 | 8×16GB DDR4-2933，共128GB，四通道 |
| OS | Ubuntu 20.04 pre-release，kernel 5.4.0-14 |
| 编译器/库 | GCC/G++ 9.2.1、AMD BLIS 2.0、OpenMPI 3.1.3 |
| 测试 | HPL 2.2、HPCG 3.1、NAMD 2.13、NumPy/OpenBLAS |

该内存使用8条DIMM且频率2933；它不能直接代表4条DDR4-3200/3600或容量不同的机器。主板BIOS、散热和持续全核频率也会改变结果。

## HPL：计算密集型例子

HPL 使用AMD BLIS 2.0的优化二进制，问题规模 `N=114000`、块大小 `NB=768`，约占128GB内存的88%；使用32个物理核，不使用SMT。作者公开的绘图数据给出3970X约1326 GFLOP/s，3990X约1571 GFLOP/s。相同32核的2990WX被3970X领先约2.5倍，但其中也包含Zen 2架构、内存拓扑和BLIS版本变化，不能只归因于频率。

3970X从1核扩展到32核的HPL曲线接近按动态频率修正后的趋势；它比64核3990X更容易在全部核心上保持利用率。这个案例适合代表稠密线性代数、渲染和计算强度较高的任务。

## HPCG：有限元/稀疏求解器的反例

HPCG 3.1 使用 `104×104×104` 的局部问题和60秒运行时间，包含稀疏矩阵、共轭梯度与多重网格操作。正文报告3970X和3990X都在约8核附近基本达到平台峰值，之后增加核心收益很小；六通道Xeon W和每socket八通道EPYC则更平滑地接近满核。

这不是直接的ANSYS、Abaqus或CalculiX分数，但它是稀疏PDE求解器的有用类似物：当工作集超过缓存、每次浮点运算需要大量主存流量时，3970X的四通道内存无法按32核同比扩展。因此：

- 稀疏迭代有限元求解器不应默认开满64线程。
- 应实测8、12、16、24、32物理核，并同时观察内存带宽与求解时间。
- SMT对带宽受限阶段可能无收益；多个独立case并发可能比单case占满核心更有效。
- 直接求解器的分解阶段可能更计算密集，不能用HPCG一概而论。

当前公开样板没有同一台3970X上的可审计ANSYS/Abaqus/CalculiX原始结果，所以本库明确把HPCG标成“有限元类似负载”，不伪装成商业CAE实测。

## NAMD：科学计算与CPU/GPU平衡

NAMD 2.13 测试包含约92,000原子的ApoA1和约100万原子的STMV，各500步。CPU-only曲线显示3970X可扩展到32核；加入GPU后，作者估计每张RTX 2080 Ti级GPU约需要12–18个CPU核心保持较好平衡。在ApoA1案例中，3970X配两张2080 Ti比3990X配两张RTX Titan略快，作者认为64核系统受GPU数量/平衡限制；在更大的STMV中，3990X组合重新领先。

这说明“CPU越多越快”对异构科学程序也不成立。CPU负责的力计算、GPU数量、PCIe布局、模型规模都会改变平衡点；上述结果不能外推到新版NAMD、其他GPU或不同分子体系。

## 适用性判断

- 适合：HPL/BLAS、并行编译、渲染、多个独立仿真case、能较好分块的CPU任务，以及最多两张高端GPU的工作站。
- 谨慎：单个大规模稀疏有限元、内存带宽主导的CFD、需要超过256GB/512GB可靠ECC内存、要求多GPU直连和服务器级RAS的场景。
- 与EPYC 7742相比：3970X频率高、桌面交互和按核计算表现好；7742拥有每socket八通道内存、更大容量和服务器平台，HPCG/大模型通常更合适。

## 限制与检索提示

检索别名：3970X、Threadripper 3000、TRX40、Zen 2 HEDT、HPL 1326 GFLOP/s、HPCG约8核饱和、NAMD ApoA1、NAMD STMV、有限元类似负载、稀疏求解器、四通道内存瓶颈。

Puget原始图像端点当前拒绝自动读取；1326 GFLOP/s来自作者在正文中公开的Pandas绘图数据。HPCG/NAMD只记录正文明确说明的趋势，不猜测图中不可读取的具体柱值。

## 官方与原始来源

- [AMD 2019 Threadripper 3960X/3970X launch](https://www.amd.com/en/newsroom/press-releases/2019-11-7-amd-introduces-world-s-fastest-high-end-desktop-pr.html)
- [Puget: Threadripper 3990X vs 3970X HPL, NumPy and NAMD](https://www.pugetsystems.com/labs/hpc/threadripper-3990x-vs-3970x-performance-and-scaling-hpl-numpy-namd-plus-gpus-1692/)
- [Puget: HPC comparison of Threadripper, Xeon W and EPYC 7742](https://www.pugetsystems.com/labs/hpc/hpc-parallel-performance-for-3rd-gen-threadripper-xeon-3265w-and-epyc-7742-hpl-hpcg-numpy-namd-1717/)
- [ServeTheHome: Threadripper 3970X topology and system review](https://www.servethehome.com/amd-ryzen-threadripper-3970x-review-32-cores-of-madness/)
