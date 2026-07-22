# Ryzen 5 1600X、2600X、3600：Zen 到 Zen 2 的 CCX 与科学负载案例

## 代际定位与快速回答

这份案例用三个六核型号代表桌面 Ryzen 的前三代：Zen 的 Ryzen 5 1600X、Zen+ 的 Ryzen 5 2600X、Zen 2 的 Ryzen 5 3600。它们都是单 socket、双通道内存的桌面平台，通常由 Linux/Windows 暴露为单个 NUMA node；性能局部性主要来自 CCX、缓存和 Zen 2 的 CCD/I/O die，而不是多 socket 服务器式 NUMA。

用户问“早期 Ryzen 做科学计算如何”时，应先说明：六核十二线程适合中小型并行任务，但双通道带宽和 CCX 间延迟会限制稀疏矩阵、大网格与多 GPU 供给。追问具体例子时分别返回 1600X 的多线程编译/渲染、2600X 的 3D particle movement、3600 的 NAMD/神经仿真与精确核间延迟；要求详细介绍时再展开平台和功耗。

## NUMA、CCX 与内存拓扑

### Ryzen 5 1600X：Zen

1600X 是 6C/12T、3.6/4.0 GHz、95 W 的 Summit Ridge 型号。一个 Zen die 内有两个 CCX，核心跨 CCX 通信会经过片上互联；平台只有双通道 DDR4。它一般不是多 NUMA node 服务器，但线程调度、缓存共享和内存频率仍会影响延迟敏感工作。

### Ryzen 5 2600X：Zen+

2600X 同为 6C/12T，3.6/4.2 GHz、95 W，仍是双 CCX、双通道 AM4，但 Zen+ 改进了缓存/内存延迟和频率机制。它适合做“拓扑相近、微架构小改”的类比案例：不能期待核心数不变时所有应用等比例提升，低延迟与频率敏感项目通常更受益。

### Ryzen 5 3600：Zen 2

3600 是 6C/12T、3.6/4.2 GHz、65 W，由一个 7nm compute die 与一个 12nm I/O die 组成，带 32 MB L3、双通道 DDR4-3200 和 24 条 PCIe 4.0。AnandTech 的 core-to-core ping 实测约为：同一核心的 SMT 线程 **7.5 ns**，同 CCX 核心 **34 ns**，跨 CCX 核心 **87–91 ns**。这些不是 DRAM 延迟，而是核间通信延迟。

实际操作系统通常仍显示单 NUMA node；不要因为有两个 CCX或 CCD/I/O die 就虚构多个 NUMA node。对进程绑核更有意义的是避免频繁跨 CCX 共享写热点，并确认内存频率与 Infinity Fabric 设置。

## 测试环境

三个型号来自 AnandTech 不同年份的公开测试套件，并非同一次严格代际对照，因此本案例不跨文章比较绝对分数。1600X 测试围绕 Windows 10、Chromium 编译、Blender、Cinebench、ray tracing、加密与转码；2600X 深度评测包含 3D particle movement/Brownian Motion 等系统与科学代理；3600 使用更新的测试套件，包含 NAMD ApoA1、DigiCortex、3DPM、y-Cruncher、Photoscan 与功耗 wrapper。

由于旧 AnandTech 子页当前会重定向，本文只保存搜索索引可核对的原文结论和 3600 页面明确的数字，不从失效图表猜测 1600X/2600X 成绩。

## HPC 与科学计算实测

### Zen / Ryzen 5 1600X

原评测结论指出，12 线程在 2D→3D photo conversion、ray tracing、Blender、Cinebench、encryption、video transcoding 和 Chromium compilation 中产生显著优势；单线程 IPC 相比当时 Kaby Lake 较弱。这是“并行吞吐强、单线程不一定强”的实测例子，但网页正文没有可核对绝对分数。

### Zen+ / Ryzen 5 2600X

评测的 3DPM 是 Brownian Motion/三维粒子运动算法，单线程受频率和 IPC 影响，多线程还要承担同步和缓存行为；这比单纯 Cinebench 更接近科学代码结构。现有机器可读内容确认了测试方法和型号，但没有可核对的 2600X 绝对结果，因此知识库不写伪精确值。

### Zen 2 / Ryzen 5 3600

3600 测试套件包括 NAMD ApoA1 分子动力学、DigiCortex 32k neuron/1.8B synapse 神经仿真、3DPM Brownian Motion 和 y-Cruncher AVX。功耗 wrapper 的明确结果是：y-Cruncher AVX 峰值约 **90 W**，全核约 3.875–3.925 GHz；3DPM AVX 全程不超过约 **75 W**；Photoscan 峰值约 **80 W**，大段可变线程阶段约 60 W。

这里的 90 W 不是违反 65 W TDP：AMD 65 W 型号的 PPT 可到 88 W，测量方法与短时峰值也会造成接近 90 W 的读数。真实 HPC 部署应记录 PPT、散热和持续全核频率。

## 有限元/CAE 解释边界

三个评测都没有直接运行 ANSYS、Abaqus、CalculiX 或 Code_Aster。3DPM、NAMD、DigiCortex 和 y-Cruncher 可用于类比计算、线程和缓存行为，但不能替代有限元求解时间。对于大型稀疏 FEA，双通道带宽和有限内存容量通常会比六核算力更早成为限制；小模型或前后处理则可能更看重单线程和延迟。

## 限制与检索提示

- 代际概述检索词：Ryzen Zen、Zen+、Zen 2、1600X、2600X、3600、双通道、CCX。
- Zen 具体例子：1600X、12 线程、Chromium 编译、Blender、ray tracing、转码。
- Zen+ 具体例子：2600X、3DPM、Brownian Motion、双 CCX、延迟改进。
- Zen 2 完整报告：3600、7.5 ns、34 ns、87–91 ns、NAMD ApoA1、DigiCortex、y-Cruncher 90 W。
- 三篇测试环境不相同，不能把绝对分数拼成严格代际比例。
- 通常单 NUMA node 不等于没有局部性；CCX/cache/片上互联仍会影响共享数据。
- 当前没有直接有限元成绩，所有 CAE 结论必须标记为相似性分析。

## 来源

- AnandTech，Ryzen 5 1600X vs Core i5：https://www.anandtech.com/show/11244/the-amd-ryzen-5-1600x-vs-core-i5-review-twelve-threads-vs-four
- AnandTech，第二代 Ryzen 2600X 深度评测：https://www.anandtech.com/show/12625/amd-second-generation-ryzen-7-2700x-2700-ryzen-5-2600x-2600
- AnandTech，Ryzen 5 3600 评测：https://www.anandtech.com/show/15787/amd-ryzen-5-3600-review-amazons-best-selling-cpu
- Tom's Hardware，Ryzen 5 3600 规格与平台补充：https://www.tomshardware.com/reviews/amd-ryzen-5-3600-review,6287.html
