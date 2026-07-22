# 代表案例：Xeon E5-2697 v4、Gold 6148 与 Gold 6248 的 NUMA/HPCG 实测

## 适合回答什么

这篇案例用于回答“Broadwell-EP 到第一/第二代 Xeon Scalable 的内存与稀疏求解性能有什么变化”。RRZE研究在同一方法下测试单socket E5-2697 v4和Gold 6248，并说明Gold 6148在本文用例中与6248结果相同。它同时展示了一个比CPU代际更容易被忽视的事实：NUMA balancing、透明大页和SNC/CoD设置能带来12%甚至约2倍的表观差异。

## 测试环境

| 项目 | Broadwell-EP | Cascade Lake-SP |
|---|---|---|
| CPU | Xeon E5-2697 v4 | Xeon Gold 6248 |
| 核心/线程 | 18/36 | 20/40 |
| L3 | 45MiB inclusive shared L3 | 27.5MiB non-inclusive victim L3 |
| 内存 | 4通道DDR4-2400 | 6通道DDR4-2933 |
| 理论内存带宽 | 76.8GB/s | 140.8GB/s |
| OS | Ubuntu 18.04.3，kernel 4.15 | 相同 |
| 编译器 | Intel 19.0 update 2 | 相同 |

微基准关闭Turbo并固定频率：E5-2697 v4核心/Uncore为2.0/2.8GHz，Gold 6248为1.6/2.4GHz；真实应用才启用Turbo。LIKWID 4.3用于计数和带宽测量。Skylake-SP Gold 6148也参加了测量，作者说明本文展示的用例与Gold 6248一致，因此没有重复绘图；这只能支持“这些测试中相同”，不能概括所有指令或安全补丁场景。

## NUMA、CoD/SNC 与操作系统设置

E5-2697 v4的Cluster-on-Die（CoD）和Gold 6248的Sub-NUMA Clustering（SNC）都能把一个socket逻辑切成两个ccNUMA domains。开启后，本地核心只能直接使用半个socket对应的L3/内存控制器；适当pinning可减少共享资源冲突，但进程和内存页放错域会产生远端访问。

在Gold 6248、Ubuntu 18.04.3上，默认`NUMA balancing=on`与`THP=madvise`使大工作集的单核load-only微基准最多慢约2倍；满socket与最优设置相比仍差12%。研究后续采用`NUMA balancing=off`、`THP=always`。关闭SNC让单核主存访问约慢4%，但同时恢复完整socket L3视图。

这组数字不是建议所有系统永久关闭NUMA balancing或强制THP。它证明的是：基准报告若不写OS、THP、NUMA与pinning设置，就不足以归因到CPU。

## STREAM 与内存带宽

STREAM使用2GB工作集，分别测试标准stores、scalar和non-temporal stores，并比较compact/scatter及CoD/SNC开关。带宽受写分配、向量化与线程跨NUMA域的方式影响。E5-2697 v4和Gold 6248都出现典型的饱和曲线；compact策略只填满第一个域时，会让域间负载不平衡，scatter更容易同时利用两个内存域。

报告的微基准最高可达到约85%理论带宽，但不同工具、编译参数和store策略可能给出完全不同结果。尤其不能把STREAM报告的24 bytes/iteration直接当作真实内存流量而忽略write allocate。

## HPCG：稀疏迭代求解器例子

HPCG 3.1使用纯MPI、每物理核一个进程，因为MG中的对称Gauss-Seidel平滑器无法有效共享内存并行且占超过80%运行时间。每进程局部问题为`160^3`，工作集约1.3GB，最多25次CG迭代，并启用`HPCG_CONTIGUOUS_ARRAYS`。

| 单socket结果 | E5-2697 v4 | Gold 6248 |
|---|---:|---:|
| HPCG模型预测 | 10.27 GFLOP/s | 17.37 GFLOP/s |
| HPCG实测 | 8.98 GFLOP/s | 13.95 GFLOP/s |
| 主要变化 | 4通道、18核 | 6通道、20核、更多带宽 |

Gold 6248实测约为E5-2697 v4的1.55倍，而不是按AVX-512宽度得到的2倍或按理论峰值线性增长。HPCG的SpMV、WAXPBY和MG由内存流量决定；实测和roofline预测的差异还受到MPI进程自然失同步、缓存复用和kernel间barrier影响。

## 对有限元、CFD与CAE的意义

HPCG的27点stencil、显式稀疏矩阵、CG和多重网格与许多有限元/有限体积迭代阶段相似。可迁移结论包括：

- Gold 6248的六通道内存比E5 v4四通道更适合单socket大规模稀疏求解。
- NUMA域、first-touch与MPI rank放置能改变有效带宽，不能只看CPU型号。
- AVX-512对稠密DGEMM帮助大，对HPCG整体收益受内存限制。
- 商业有限元还受求解器类型、矩阵结构、许可证与I/O影响，不能把13.95 GFLOP/s当作ANSYS/Abaqus成绩。

## 限制与检索提示

检索别名：E5-2697 v4、Broadwell-EP、Gold 6148、Skylake-SP、Gold 6248、Cascade Lake-SP、CoD、SNC、NUMA balancing、THP、HPCG 8.98、HPCG 13.95、稀疏矩阵、有限元类似负载、roofline、LIKWID。

本报告只测单socket；不覆盖UPI跨socket、双路内存放置和集群网络。Gold 6148与6248“结果相同”只限文中用例。所有数字依赖Ubuntu 18.04.3、Intel compiler 19.0u2与指定频率/问题规模。

## 官方与原始来源

- [OSTI: Understanding HPC Benchmark Performance on Intel Broadwell and Cascade Lake Processors](https://www.osti.gov/servlets/purl/1771077)
- [Report DOI 10.2172/1771077](https://doi.org/10.2172/1771077)
- [Intel ARK: Xeon E5 v4 family](https://www.intel.com/content/www/us/en/ark/products/series/91287/intel-xeon-processor-e5-v4-family.html)
- [Intel ARK: First-generation Xeon Scalable](https://www.intel.com/content/www/us/en/ark/products/series/125191/intel-xeon-scalable-processors.html)
- [Intel ARK: Second-generation Xeon Scalable](https://www.intel.com/content/www/us/en/ark/products/series/192283/2nd-gen-intel-xeon-scalable-processors.html)
