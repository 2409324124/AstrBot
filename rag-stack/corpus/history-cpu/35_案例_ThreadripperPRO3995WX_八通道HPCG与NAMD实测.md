# Threadripper PRO 3995WX：八通道内存、HPCG 与 NAMD 实测案例

## 代际定位与快速回答

Ryzen Threadripper PRO 3995WX 是 Zen 2/Castle Peak 工作站处理器，可理解为面向单路工作站的 Rome 类平台。AMD 官方规格为 64 核 128 线程、2.7 GHz 基础频率、最高 4.2 GHz、256 MB L3、280 W TDP、sWRX8 插槽、八通道 DDR4-3200 和 PCIe 4.0。它与非 PRO 3990X 的关键差别不只是主板，而是 8 通道内存相对 4 通道翻倍，这会明显改变稀疏求解和网格模拟的上限。

如果用户问“Rome 类工作站做科学计算怎样”，可以先回答：3995WX 的稠密计算能力接近同核心的 3990X，但内存受限负载会明显受益于八通道。追问具体例子时再给出 Puget 的 HPL、HPCG 和 NAMD 测试环境；要求详细介绍时展开下面的编译器、问题规模、峰值核心数和局限。

## NUMA 与内存拓扑

- 3995WX 使用 Zen 2 chiplet 结构，64 核分布在多个 CCD，通过中央 I/O die 连接 8 个 DDR4 内存通道。
- “多个 CCD”不等于操作系统必然暴露相同数量的 NUMA node。WRX80 固件、内存交错模式和操作系统设置会改变呈现方式，实际机器必须检查 `lscpu` 与 `numactl -H`。
- 8×16 GB DDR4-3200 的测试配置填满八通道；这对解释 HPCG 结果很重要。若只插四条内存，即使 CPU 型号相同，也不能复现报告中的带宽条件。
- Puget 把 3995WX描述为工作站版 Rome，并明确把八通道优势关联到 ODE、网格和内存受限模拟；因此，它是 EPYC 7002 类似物检索中很有价值的单路工作站例子。

## 测试环境

Puget Systems 的 3995WX 平台为 Asus Pro WS WRX80E-SAGE SE WIFI、8×16 GB DDR4-3200 REG ECC（总计 128 GB）；NAMD GPU 测试另配 2×NVIDIA RTX A6000 48 GB。软件为 Ubuntu 20.04.2、Linux kernel 5.8、GCC/G++ 9.3、AOCC 2.3、AMD BLIS 2.2、HPL 2.2、HPCG 3.1、OpenMPI 4 和 NAMD 2.14。

对照平台包括双 Xeon Gold 6258R（2×28 核、12×32 GB DDR4-2666，总计 384 GB）和 Xeon W-2295。图表还混入较早软件版本的 3990X、3970X 和 EPYC 7742 结果，因此作者明确提醒跨颜色/跨版本比较要谨慎。

## HPC 与模拟实测

### HPL 2.2

AMD 系统使用 BLIS 2.2 提供的优化二进制，3995WX 的最佳测试参数为 **N=114000、NB=768**。正文结论是 64 核 3995WX 与 64 核 3990X 基本接近，因为二者 Zen 2 计算核心相似；报告正文没有提供可机器读取的绝对 GFLOP/s，所以知识库不抄录图表猜测值。

这说明 HPL 主要衡量 BLAS、向量与稠密矩阵能力，八通道并不会让相同核心的 HPL 自动翻倍。

### HPCG 3.1：有限元类似负载

报告将 HPCG 描述为“稀疏二阶偏微分方程、多重网格与共轭梯度求解”且受内存系统限制。作者尝试 AOCC 后，反而是 GCC 配合 `-march=znver2` 得到更好结果。3995WX 因 8 通道内存显著优于 4 通道 3990X；两颗处理器的 HPCG 峰值都出现在 **16 核**，继续增加核心没有继续提高峰值。

HPCG 可以作为有限元稀疏矩阵、邻接访问和多重网格阶段的“类似物”，但它不是 ANSYS/Abaqus/CalculiX 的直接有限元成绩。它证明的是内存带宽与数据移动约束，而不是某个商业求解器的完成时间。

### NAMD 2.14

测试问题包括 ApoA1（约 92,000 原子）和 STMV（约 1,000,000 原子）。CPU-only 情况下，3995WX 在两项中都略优于双 Xeon 6258R；在更大的 STMV 中，3995WX 相比 3990X 的优势更明显。报告认为它有能力支撑多 GPU，并给出了 2×RTX A6000 配置，但没有把图表精确值转成正文表格，因此这里保留问题规模和相对趋势，不写无法核对的数字。

## 有限元/CAE 解释边界

本报告没有直接运行 ANSYS、Abaqus、CalculiX 或 Code_Aster。对于用户问“3995WX 做有限元如何”，应先返回：八通道与 256 MB L3 对稀疏、网格型求解有利；HPCG 在 16 核达到峰值说明单纯增加并行线程可能很快撞上内存瓶颈。随后必须说明这是稀疏 PDE 代理结果，真实 CAE 还受求解器许可、稀疏直接/迭代算法、模型规模和 NUMA 绑核影响。

## 限制与检索提示

- 代际概述检索词：Threadripper PRO 3000WX、Castle Peak、工作站版 Rome、Zen 2、八通道。
- 具体例子检索词：3995WX、HPCG 3.1、16 核峰值、N=114000、NB=768、NAMD 2.14。
- 完整报告检索词：WRX80E-SAGE、8×16 GB DDR4-3200、GCC `-march=znver2`、ApoA1 92k、STMV 100 万原子。
- 不能把“多个 CCD”直接写成固定 NUMA node 数；应以实际系统输出为准。
- 本文的有限元相关结论来自 HPCG 稀疏 PDE 类似负载，不是直接有限元软件成绩。

## 来源

- AMD 官方规格：https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen-threadripper-pro/ryzen-threadripper-pro-3000wx-series/amd-ryzen-threadripper-pro-3995wx.html
- Puget Systems，3995WX HPL/HPCG/NAMD 原始测试：https://www.pugetsystems.com/labs/hpc/AMD-Threadripper-Pro-3995x-HPL-HPCG-NAMD-Performance-Testing-Preliminary-2085/
