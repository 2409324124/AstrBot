# Threadripper 1950X：双 die NUMA、Creator/Game Mode 与 Linux HPC 实测

## 代际定位与快速回答

Ryzen Threadripper 1950X 是第一代 Threadripper/Whitehaven 的 16 核旗舰，规格为 16 核 32 线程、3.4 GHz 基础频率、最高 4.0 GHz、180 W、四通道 DDR4 和 64 条 PCIe 3.0。它由两个活跃 Zeppelin die 组成，每个 die 有 8 核、两个内存通道和 32 条 PCIe；跨 die 访问必须经过 Infinity Fabric。

如果用户问“第一代 Threadripper 性能如何”，应先回答它在 2017 年以大量线程和四通道带宽提供很强的并行吞吐，但跨 die 延迟与操作系统的 UMA/NUMA 模式会影响负载。追问具体例子时，可给出 NPB EP.C 比同价 i9-7900X 快 24%、OpenSSL 快约 12%；要求详细介绍时，再展开 Creator/Game Mode、Linux 环境和功耗。

## NUMA 与 Creator/Game Mode

- 两个活跃 die 都有本地内存控制器：每 die 直接连接两个 DDR4 通道，合计四通道。一个 die 上的核心访问另一 die 所接内存时存在额外跳转。
- AnandTech 初始测试中的 Creator Mode 启用全部 16C/32T，并向软件呈现 UMA 取向；Game Mode 关闭一个 die，同时采用 NUMA/本地化取向，以减少跨 die 延迟并兼容不能正确处理大量核心的游戏。
- Game Mode 不是“免费降低 NUMA 延迟”。复测的 19 个多线程项目中，它相对 Creator Mode 从约 +1% 到 -48%，Corona 为 -48%、LuxMark 为 -45%；多数吞吐任务因失去一半核心显著变慢。
- 单线程测试大多在 Creator/Game Mode 之间相差不超过约 5%。是否切换不能只看延迟，必须看应用是线程吞吐、内存局部性还是兼容性受限。
- 某些内存/神经仿真负载表现不同：DigiCortex 中 SMT-off 的 1950X 因较低主存延迟和 16 个物理线程表现最好，而 Creator/UMA 结果明显靠后。这说明 NUMA 策略需要由具体数据访问模式决定。

## 测试环境

### AnandTech Windows 模式复测

处理器为 1950X（16C/32T、3.4 GHz、180 W），主板 ASUS X399 ROG Zenith Extreme，4×8 GB G.Skill DDR4，分别测试 DDR4-2400 C15 与 DDR4-3200 C14；Windows 10 Pro 64-bit。模式切换涉及重启，所以 BIOS 重置或模式变化会影响复现。

### Phoronix Linux 测试

平台为 Gigabyte X399 AORUS Gaming 7、4×8 GB DDR4-3200、Samsung 950 Pro 256 GB NVMe、Radeon R9 Fury；系统为 Ubuntu 17.04、Linux 4.13 Git、Mesa 17.3-dev、GCC 6.3、EXT4，所有处理器使用 performance governor。对照包括 Ryzen 7 1800X、Core i7-7740X/7820X 和同价 Core i9-7900X。

功耗由 WattsUp Pro 测量整机 AC 输入，不是 CPU package power。1950X 全套测试平均为 **171 W**，i9-7900X 为 **179 W**；performance governor 会影响空闲与平均功耗，所以不能拿它替代 TDP。

## HPC 与科学计算实测

### NAS Parallel Benchmarks 与 OpenMP

NPB 的 EP.C 是高度并行的 embarrassingly-parallel 项目，1950X 比 i9-7900X 快 **24%**。Rodinia LavaMD 的 OpenMP 高线程负载中，1950X 也明显领先 20 线程 7900X；正文未给机器可读绝对值，故只保留趋势。

早期可复现结果集 `1708257-TY-THREADRIP83` 包含 STREAM、HPC Challenge 和 HPCG。网页图表没有可核对的绝对数值，因此案例记录结果集 ID和测试存在性，不抄图猜数。HPCG 是稀疏 PDE/有限元类似负载，不是直接结构有限元成绩。

### OpenSSL、编译与其他负载

线程友好的 OpenSSL 中，1950X 约比 i9-7900X 快 **12%**。默认 x86-64 Linux kernel 编译约 **36 秒**，且比 7900X 略快。完整评测结论是多线程、OpenMP、ray tracing 等能充分利用线程的项目经常由 1950X 领先；TensorFlow、Xsbench、Blender 等 IPC 或线程扩展较弱的测试可能由 Intel 领先。

这组分化很适合检索“类似物”：用户问高并行 Monte Carlo、OpenMP 时返回 NPB/LavaMD；问稀疏有限元时返回 NUMA 风险和 HPCG 结果集；问低线程 CAE 前后处理时则提醒第一代 Zen IPC 较弱。

## 有限元/CAE 解释边界

现有资料没有 1950X 的 ANSYS、Abaqus、CalculiX 或 Code_Aster 直接成绩。可以引用双 die NUMA、HPCG 测试集和 OpenMP 扩展作为相似性证据，但不能把 NPB EP.C 的 24% 或 OpenSSL 的 12% 套用到有限元求解时间。直接求解器、迭代求解器和前后处理会有不同的线程与内存行为。

## 限制与检索提示

- 代际概述检索词：第一代 Threadripper、Whitehaven、1950X、双 Zeppelin die、四通道、Infinity Fabric。
- 具体例子检索词：NPB EP.C、24%、OpenSSL 12%、kernel build 36 秒、171 W。
- 完整报告检索词：Creator Mode、Game Mode、UMA、NUMA、Corona -48%、LuxMark -45%、Ubuntu 17.04、Linux 4.13。
- Creator/Game Mode 是 Windows/Ryzen Master 时代的模式语义；Linux 或现代固件必须直接查看实际 NUMA 拓扑。
- HPCG 绝对值未从图表可靠取得；本案例没有直接结构有限元成绩。

## 来源

- AnandTech，1950X/1920X 完整评测与 Creator/Game Mode：https://www.anandtech.com/show/11697/the-amd-ryzen-threadripper-1950x-and-1920x-review
- AnandTech，Game Mode 复测：https://www.anandtech.com/show/11726/retesting-amd-ryzen-threadrippers-game-mode-halving-cores-for-more-performance
- Phoronix，1950X Linux 完整评测：https://www.phoronix.com/review/amd-tr-1950x
- Phoronix，包含 STREAM/HPC Challenge/HPCG 的早期结果集：https://www.phoronix.com/review/threadripper-1950x-pre/2
