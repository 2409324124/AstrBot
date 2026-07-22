# 代表案例：Xeon E5-2695 v2 与 E5-2699 v3 的 NREL 科学工程实测

## 适合回答什么

这篇案例用于回答“Ivy Bridge-EP 到 Haswell-EP 实际提升多大”“老 E5 做材料、分子动力学或工程仿真怎么样”。NREL 在同一研究中比较了 Peregrine 的双路 E5-2695 v2 节点和双路 E5-2699 v3 节点，覆盖 STREAM、MKL 矩阵乘、VASP、Gaussian、LAMMPS、Amber 与 FAST 风机工程模型。最重要的结论不是某个总分，而是：Haswell 每核心更强、满节点核心更多，但多数应用在半节点以后收益递减，超线程通常无益，节点吞吐需要靠合适的任务打包。

## 测试环境

| 项目 | Ivy Bridge-EP 节点 | Haswell-EP 节点 |
|---|---|---|
| CPU | 2×Xeon E5-2695 v2 | 2×Xeon E5-2699 v3 |
| 核心 | 24物理核，2.4GHz | 36物理核，2.3GHz |
| L3 | 30MB/socket | 45MB/socket，分成10核+8核双ring |
| 内存 | 32GB DDR3，8×4GB，总计每通道1 DIMM | 64GB，4×8GB/socket，每通道1 DIMM |
| OS | CentOS 6.3，kernel 2.6.32 | Linux kernel 2.6.32 |
| 范围 | 单节点，不测试 InfiniBand | 单节点 |

两台都是双路 ccNUMA。报告在应用中对比了 `Scatter` 与 `Compact` rank 映射：Scatter 尽量拉大 NUMA 距离并分散共享资源，Compact 使用连续 core IDs。实际最优策略取决于应用是共享缓存、内存带宽还是通信受限。

## STREAM 与内存放置

STREAM 5.10 使用 Intel C 14.0.2，编译参数包含 `-O2 -openmp -mavx`；A/B/C 三个数组各6GB，总工作集18GB。线程数由 `OMP_NUM_THREADS` 控制，需要时用 `KMP_AFFINITY=scatter` 固定线程。

报告没有在正文提供机器可读的精确带宽柱值，因此本库不从图像估算数字。可确认的趋势是：E5-2695 v2 接近满节点时，固定/分散线程比不固定更好；E5-2699 v3 对 pinning 不太敏感。两台机器的实测最大带宽都明显低于理论峰值，报告把这视为真实应用数据移动的潜在限制。

## 稠密矩阵与 VASP

10000×10000 的双精度矩阵乘使用 Intel compiler 14.0.2 和 MKL。双路 E5-2699 v3 满36核相对双路 E5-2695 v2 满24核的性能比约2.193。这个比值同时包含50%更多核心、FMA/AVX2、缓存与内存变化，不是“Haswell单核快2.193倍”。

VASP 5.3.5 使用 Intel compiler 14.0、Intel MPI 4.1.3 与 MKL，测试40原子 In2O3、4×4×4 k-point mesh、400eV cutoff。以达到600 jobs/day的初始斜率估计，Haswell约5核达到目标，Ivy Bridge约8核，初段每核心吞吐约为1.6倍；但两种节点在超过约半数核心后都明显偏离线性扩展。这说明高核心节点不一定缩短单个VASP任务，可能更适合并发多个中等rank任务。

## LAMMPS 与 Amber

LAMMPS 使用2013-08-14版本、Intel compiler 13.1.3、Intel MPI 4.1.1；模型为9996原子的乙腈立方盒、GAFF、PME、50,000步、0.5fs。相同MPI ranks下，E5-2695 v2节点吞吐约为E5-2699 v3的60%。Haswell可强扩展到36物理核，但启用超线程会显著降低吞吐。

Amber 14使用180,038原子的纤维素酶体系、CHARMM36、PME、1000步、1fs。相同ranks下，Ivy Bridge约为Haswell的70%；E5-2699 v3约在18线程开始饱和，继续增加ranks价值下降。

这两个例子说明“同一代际提升”会随模型和通信方式变化：LAMMPS约体现更大的提升，Amber更早受共享资源/通信限制。

## FAST：工程与结构动力学例子

FAST 是NREL风机耦合工程框架，组合空气动力、流体动力、伺服与结构动力模块。报告使用Intel compiler 13.1.3，按大量独立工况并发计算吞吐。相同物理核心数下，Haswell比Ivy Bridge约快23%；在各自满节点核心数下差距更大，因为FAST不同任务间资源争用较小。

FAST不是通用有限元求解器，但它是直接的工程/结构动态邻近工作负载。它表明对于大量独立载荷工况，高核心节点的正确使用方式可能是同时运行多个case，而不是给一个case开满超线程。

## NUMA、超线程与调度结论

- STREAM等内存流任务需要检查线程pinning和first-touch。
- VASP与Amber在半节点附近开始收益递减，应扫描ranks而不是固定开满。
- LAMMPS/Amber/FAST大多不受益于超线程，部分测试反而下降。
- 高吞吐队列应允许多个用户/任务共享节点，以利用单任务无法使用的剩余核心。
- 核心数必须与内存带宽、缓存、许可证和任务粒度共同评估。

## 限制与检索提示

检索别名：E5-2695 v2、Ivy Bridge-EP、E5-2699 v3、Haswell-EP、Peregrine、NREL、VASP、LAMMPS乙腈、Amber纤维素酶、FAST风机、结构动力学、工程仿真、NUMA scatter、超线程负收益。

报告比较的是完整节点而非同核数同频CPU替换；Haswell节点多12个物理核心且内存容量不同。文中“60%/70%/23%/2.193”只属于指定版本、模型和线程配置，不能套到其他软件版本或任意有限元程序。

## 官方与原始来源

- [NREL/OSTI: Parallel Application Performance on Two Generations of Intel Xeon HPC Platforms](https://www.osti.gov/servlets/purl/1226160)
- [Report DOI 10.2172/1226160](https://doi.org/10.2172/1226160)
- [Intel ARK: Xeon E5 v2 family](https://www.intel.com/content/www/us/en/ark/products/series/78582/intel-xeon-processor-e5-v2-family.html)
- [Intel ARK: Xeon E5 v3 family](https://www.intel.com/content/www/us/en/ark/products/series/78583/intel-xeon-processor-e5-v3-family.html)
