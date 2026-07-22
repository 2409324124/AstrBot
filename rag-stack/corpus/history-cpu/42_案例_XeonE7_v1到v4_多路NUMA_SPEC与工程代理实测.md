# 代表案例：Xeon E7 v1–v4 多路 NUMA、数据库、SPEC 与工程代理实测

## 适合回答什么

这篇案例用于回答“Xeon E7 每一代能否给出具体多路服务器例子”“E7 的 NUMA 和科学工程性能怎样”。E7 面向四路及更大关键业务系统，公开资料不像 EPYC 那样集中提供 HPL/HPCG；因此本报告把同一产品线的四个代表型号拆开：初代 E7-8870、E7-4890 v2、E7-8890 v3 和 E7-8890 v4。每一项保留系统规模与软件环境，绝不把不同机器的 SPEC 数字当成等条件代际增幅。

## 测试环境

| 代际与代表型号 | 已核对的实测系统 | 实测类型 |
|---|---|---|
| 初代 E7-8870 | 8 socket、80 个物理核的上一代基线系统 | Intel 企业数据库案例；另有 CTP 指标 |
| E7-4890 v2 | NEC NX7700x A2010M-60，4 socket、60 核、1 TB 内存、Violin 闪存 | Windows Server 2012 Datacenter、SQL Server 2012 Enterprise SP1 x64 |
| E7-8890 v3 | 4 socket、72 核系统 | SPEC CPU2006 CFP speed |
| E7-8890 v4 | Cisco 四路 96 核；Huawei KunLun 9016 十六路 384 核 | SPEC CPU2006、CPU2017、SPEC OMP2012 |

这些结果横跨数据库吞吐、CPU speed/rate 和 OpenMP 科学代理负载，适合展示“类似物”和具体报告，但不能拼成一张未经控制变量的代际排行榜。

## NUMA 与多路拓扑

初代 E7-8870 案例使用 8 颗处理器；E7-4890 v2 案例缩减为 4 颗处理器。Intel 白皮书明确把四路 v2 机器视为 **4 个 NUMA node**，并讨论 Hyper-V 的 V-NUMA。每颗处理器的本地内存控制器提供低延迟区域，访问其他 socket 的页要经过多路互连；数据库内存、虚拟机和线程若没有按拓扑放置，就可能把更多核心变成远端访问来源。

E7-8890 v3 的四路系统同样至少具有 socket 级 NUMA 边界。十六路 E7-8890 v4 则是更极端的 ccNUMA 例子：384 个物理核被分散在 16 个 socket，OpenMP 线程、页放置和工作集分块比单路频率更能决定扩展效率。SPEC OMP 总分是整机结果，不能缩放成单颗 CPU 分数。

## 初代 E7-8870：八路系统基线

Intel 企业系统白皮书把 **8×E7-8870、80 个物理核、2.40 GHz** 的服务器作为上一代 SQL 基线。另一份 Intel CTP 表给出 E7-8870 为 **178,400 MTOPs**，但 CTP 是出口管制使用的综合计算指标，不是数据库、HPC 或有限元 benchmark；它只能帮助确认型号级计算分类，不能与 SPEC、STREAM 或 HPL 直接比较。

这个案例对初代 E7 最有价值的信息是八路规模和跨 socket NUMA 边界，而不是一个可移植的应用分数。白皮书的后续 v2 对照使用了不同 SQL Server 版本，因此本库不会把结果标成纯 CPU IPC 提升。

## E7-4890 v2：四路、1 TB 与 SQL/NUMA

v2 测试机是 NEC NX7700x A2010M-60：**4×E7-4890 v2、60 个物理核、1 TB 内存**，配 Violin 闪存、Windows Server 2012 Datacenter 和 SQL Server 2012 Enterprise SP1 x64。白皮书报告在高负载区开启 Hyper-Threading 约改善 **15%**；最大并发量约由 2300 增至 2500，较稳定吞吐区约由 1800 增至 2000。

四路 v2/60 核相对八路 v1/80 核的系统级结果，HT 关闭约为 **1.02×**，HT 开启约为 **0.99×**。这说明更少 socket 可以接近上一代八路系统，但 v1 使用 SQL Server 2008 R2、v2 使用 SQL Server 2012 SP1，存储和平台也属于整机设计；这些比值不能归因成 E7-4890 v2 单颗比 E7-8870 快多少。

## E7-8890 v3：四路 SPEC 浮点例子

SPEC CPU2006 官方结果列表中的四路 E7-8890 v3 配置为 **72 个物理核**，CFP2006 base/peak 为 **103/109**。CFP speed 套件包含一组单任务浮点科学程序，比数据库案例更接近计算内核，但仍不是 HPL、HPCG 或商业有限元。

作为相邻参照，双路 E7-4870 v2 的官方列表结果为 CINT base/peak 45.3/48.9、CFP base/peak 68.6/71.5。两台机器在 socket 数、核心数、编译器和平台上不同，因此 103 对 68.6 只能说明这些已提交整机的结果，不能声称 v3 架构本身快了固定百分比。

## E7-8890 v4：四路 SPEC 与十六路 OpenMP 工程代理

四路 E7-8890 v4 配置有 **96 个物理核**；同一官方 CPU2006 结果体系中，CINT base/peak 为 **69.6/71.3**，CFP base/peak 为 **118/126**。Dell PowerEdge R930 的 SPEC CPU2017 rate 结果还给出 SPECrate2017_int_base **318**。不同 SPEC 版本的分数定义不同，318 不能与 CPU2006 的118或126直接相除。

更接近 HPC/CAE 的例子来自 Huawei KunLun 9016：**16×E7-8890 v4、384 个物理核**，SPEC OMP2012 的 SPECompG_base2012 为 **59.8**、peak 为 **67.2**。套件包含 `362.fma3d` 和 `370.mgrid331`：前者是有限元/结构动力学相似代理，后者是多重网格相似代理。因此它可用来回答“E7 v4 有没有有限元类似负载”，但仍不是 Abaqus、ANSYS 或某个真实工程模型的求解时间。

## 对有限元、CFD与HPC的意义

E7 v4 的 SPEC OMP 是四代中最直接的工程计算证据：fma3d 涉及有限元类计算，mgrid331 涉及规则网格与多重网格。十六路系统同时提醒使用者，多路扩展必须检查数据分块、线程绑定、first-touch、远端内存和同步开销。

数据库结果反映大内存和并发场景，SPEC CPU speed/rate 反映标准化计算程序，SPEC OMP反映共享内存科学代理。三类结果分别回答不同问题，不能互相替代。若用户问真实有限元项目，本报告应明确回答“找到有限元类似代理，但没有同一平台的商业有限元绝对成绩”。

## 限制与检索提示

检索别名：Xeon E7-8870、初代 E7、Westmere-EX、E7-4890 v2、Ivy Bridge-EX、E7-8890 v3、Haswell-EX、E7-8890 v4、Broadwell-EX、4 个 NUMA node、V-NUMA、SQL Server、SPEC CPU2006、SPEC CPU2017、SPEC OMP2012、SPECompG 59.8、fma3d、mgrid331、有限元类似负载、十六路 384 核。

E7 v1/v2 数据来自厂商整机白皮书，存在软件版本变化；v3/v4 SPEC结果来自不同提交系统。本文只在每项结果内部解释，不做跨环境的精确代际百分比。CTP 178,400 MTOPs 不是应用跑分。没有获得同一硬件上的 OpenFOAM、HPL、HPCG 和直接商业有限元成套结果。

## 官方与原始来源

- [Intel：Xeon E7 企业系统性能白皮书](https://www.intel.com/content/dam/www/public/ijkk/jp/ja/documents/white-papers/xeon-e7-enterprise-system-performance-paper.pdf)
- [Intel：CTP Metrics for Intel Xeon Processor](https://www.intel.com/content/dam/support/us/en/documents/processors/CTP-Metrics-for-Intel-Xeon-Processor.pdf)
- [SPEC CPU2006：CINT2006 results](https://www.spec.org/cpu2006/results/cint2006/)
- [SPEC CPU2006：CFP2006 results](https://www.spec.org/cpu2006/results/cfp2006/)
- [SPEC CPU2017：Dell PowerEdge R930 / E7-8890 v4 result](https://www.spec.org/cpu2017/results/res2017q2/cpu2017-20161026-00010.html)
- [SPEC OMP2012：Huawei KunLun 9016 / 16×E7-8890 v4](https://www.spec.org/omp2012/results/res2017q2/omp2012-20170519-00097.pdf)
