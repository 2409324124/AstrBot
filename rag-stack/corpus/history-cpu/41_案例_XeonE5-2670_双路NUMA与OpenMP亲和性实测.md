# 代表案例：Xeon E5-2670 双路 NUMA、STREAM 与 OpenMP 任务亲和性实测

## 适合回答什么

这篇案例用于回答“初代 Xeon E5（Sandy Bridge-EP）在双路科学计算中表现怎样”“能否给一个 NUMA 亲和性造成实际差异的例子”。代表型号是 Xeon E5-2670。它不是用一个综合跑分概括整代，而是采用 Sandia 国家实验室论文中 MareNostrum III 节点的真实平台，解释跨 socket 后内存放置为什么会直接影响 STREAM 和任务并行归并排序。

## 测试环境

| 项目 | 配置 |
|---|---|
| CPU | 2×Intel Xeon E5-2670，Sandy Bridge-EP |
| 核心 | 每颗 8 核，双路共 16 个物理核 |
| 标称频率 | 2.6 GHz |
| 内存 | 8×4 GB DDR3-1600，共 32 GB |
| 系统 | MareNostrum III 计算节点，SUSE Linux |
| 集群互连 | InfiniBand |
| 工作负载 | STREAM；task-parallel merge sort，输入为 `2^33` 个整数 |

这是一台典型双路 ccNUMA 节点：每颗处理器有自己的内存控制器和本地内存，操作系统通常把两颗 socket 暴露为两个 NUMA node。论文重点不是比较厂商峰值，而是比较 OpenMP task 在相同机器上的放置策略。

## NUMA、线程与任务放置

只使用一颗 E5-2670 时，线程和内存都位于同一个 socket，论文观察到不同 task mapping 没有明确收益。扩展到两颗 socket 后，任务可能在另一 NUMA node 执行并读取远端内存；这时仅有线程亲和性还不够，还要让产生数据、消费数据的 task 与数据页位置一致。

研究比较默认调度与拓扑感知的任务亲和性。双 socket 全部投入时，合适的 task mapping 最多带来约 **20% 性能提升**。这个结果直接说明：初代 E5 的双路扩展不能只看 16 核总数；first-touch、线程绑定以及任务依赖图与 NUMA node 的对应关系会改变有效内存带宽。

“最多约20%”是该论文给定 merge sort 和实现中的结果，不是 E5-2670 对所有程序的固定加速比。单 socket 没有同样收益，也不能把它解释成更换 CPU 所得性能。

## STREAM 与 HPC 类似负载

论文用 STREAM 检查节点内存子系统，并用 `2^33` 整数的 task-parallel merge sort 形成远大于缓存的工作集。STREAM代表连续内存带宽，merge sort同时包含任务创建、同步、数据重排和跨 NUMA 数据消费。两者共同揭示了这类双路平台的主要边界：当工作集超过缓存后，执行位置和数据位置与核心数量同等重要。

它没有报告可与其他文章直接横向比较的 E5-2670 STREAM MB/s，因此本文不填入推测数字。可复用的实测结论是：一颗 socket 内任务映射收益不明显，使用两颗 socket 后，拓扑感知映射最高约改善20%。

## 对有限元、CFD与CAE的意义

这个测试不是直接的 ANSYS、Abaqus 或 CalculiX 成绩。它与有限元/CAE 的相似点在于：装配、网格分区、稀疏矩阵向量乘、预条件和多重网格都可能产生“任务在一颗 socket 执行、数据在另一颗 socket”的远端访问。

因此在双路 E5-2670 上运行有限元或 CFD 时，可以把该案例用于解释以下调优方向：按 NUMA node 分区网格；对每个分区执行 first-touch；让 MPI rank 或 OpenMP task 靠近其数据；分别测单路和双路强扩展。不能把20%直接当作任何商业有限元软件的预期提升，实际结果还取决于求解器、矩阵结构、MPI/OpenMP 混合方式和I/O。

## 限制与检索提示

检索别名：Xeon E5-2670、初代 Xeon E5、E5 v1、Sandy Bridge-EP、MareNostrum III、双路 NUMA、OpenMP task affinity、STREAM、merge sort、`2^33` 整数、20% 性能提升、有限元类似负载、first-touch。

论文研究的是任务亲和性而非完整 CPU 评测；未给出 HPL、HPCG 或直接有限元绝对成绩。平台只有 32 GB DDR3-1600，不能代表更大内存配置。结果必须连同双路拓扑、SUSE Linux、问题规模和“最多”限定一起引用。

## 官方与原始来源

- [Sandia/OSTI：Approaches for Task Affinity in OpenMP](https://www.osti.gov/servlets/purl/1369612)
