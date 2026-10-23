# 面心立方金属粉末 XRD 相一致性与晶粒尺寸分析器修复

你接手的是一个用于金属粉末 X 射线衍射（XRD）快速质控的 Python 工具。实验室使用 Cu Kα 辐射测量候选面心立方（FCC）金属粉末，并希望程序能按主相模型完成峰索引、仪器校正、异常峰识别和相干衍射域尺寸估计。

当前实现保留了旧版命令行和 JSON 结构，但其物理计算、结构选择规则和峰展宽处理不正确。请修复程序，使它满足以下科学约束和接口约定。完成后，下面的命令必须继续可用：

```bash
python3 src/xrd_analyzer.py --input examples/peaks.json --output /tmp/xrd-result.json
```

输入数据由固定物理模型生成、可复现，但不代表真实实验采集记录。

## 输入约定

- `wavelength` 包含数值 `value` 和单位 `unit`。支持 `angstrom`、`nm`、`pm`；内部物理计算统一使用 Å。`value` 必须是有限正数；值为 `0`、负数、NaN 或无穷大时必须拒绝。
- `crystal_system` 固定为 `cubic`；`structure` 固定为 `fcc`，表示样品主相遵循面心立方反射选择规则。
- `peaks` 中每项至少包含 `id`、`two_theta_deg`、`fwhm_deg` 和 `intensity`。前两个量和 FWHM 都以 2θ 的度数表示；强度只作原样保留，不能替代结构或几何判定。
- `candidate_hkls` 是候选晶面指数数组。每项由三个非负整数组成；`(0, 0, 0)` 无效。
- `lattice_parameter_bounds_angstrom` 是主相晶格常数的闭区间。
- `zero_shift_bounds_deg` 是所有峰共享的仪器 2θ 零点偏移 `δ` 的闭区间。生成数据符合：`observed_2theta = ideal_2theta + δ`。
- `peak_position_tolerance_deg` 是预测仪器峰位的绝对残差容差。
- `instrument_fwhm_deg` 是同一峰位附近的仪器 FWHM，单位为 2θ 度数。
- `shape_factor` 是 Scherrer 公式形状因子；未给出时使用 `0.9`。
- 既有 `outlier_tolerance` 字段必须继续接受以兼容旧输入；新输入的异常判定以 `peak_position_tolerance_deg` 为准。

## 输出约定

输出 JSON 必须保留已有公开字段，并满足：

- `crystal_system`、`structure`：原样保留输入值；
- `lattice_parameter_angstrom`：仅由主相非异常峰得到的公共晶格常数；
- `zero_shift_two_theta_deg`：估计的共同仪器 2θ 零点偏移；
- `crystallite_size_nm`：由可用主相非异常峰汇总的相干衍射域尺寸，单位 nm；没有可用峰时为 `null`；
- `peaks`：与输入顺序一一对应，保留 `id`、`intensity`、`fwhm_deg`，并包含：
  - `d_spacing_angstrom`；
  - `assigned_hkl`：长度为 3 的整数数组；若无法索引可为 `null`；
  - `lattice_parameter_angstrom`；
  - `residual_angstrom`；
  - `predicted_two_theta_deg`：公共主相模型预测的仪器 2θ，包含估计的零点偏移；
  - `two_theta_residual_deg`：记录峰位与预测峰位的绝对差；
  - `corrected_fwhm_deg`：仪器展宽扣除后的样品展宽；无有效结果时为 `null`；
  - `crystallite_size_nm`：单峰 Scherrer 尺寸；无有效结果时为 `null`；
  - `anomalous`：布尔值；
- `anomalous_peak_ids`：所有异常峰 ID，顺序与输入一致。
- 输入校验、物理拟合或 JSON 序列化失败时，命令行必须以非零状态退出，且不得创建、覆盖或留下半截的目标输出 JSON。成功写出时应先完整生成结果并以原子替换方式提交目标文件。

### 命令行输出通道

成功结果只通过 `--output` 指向的文件提交，标准输出 `stdout` 不承载业务结果，题面不要求其内容。输入校验、物理拟合或 JSON 序列化失败时，进程必须以非零状态退出，并允许通过标准错误 `stderr` 输出诊断信息；测试可以读取并断言该通道。以下两类拒收必须在 `stderr` 中包含对应的固定标识：

- `wavelength.value` 为 `0`、负数、NaN 或无穷大时：`wavelength must be a finite positive number`；
- `candidate_hkls` 中不存在 FCC 允许反射时：`no FCC-allowed candidate hkl`。

## 科学与行为约束

### 1. FCC 结构选择规则

主相是 FCC。只有 `(h, k, l)` **全为奇数或全为偶数**时，反射才被允许；混合奇偶性的候选晶面不可分配给 FCC 主相峰。例如 `(1,1,1)`、`(2,0,0)`、`(2,2,0)`、`(3,1,1)` 可用，而 `(1,0,0)`、`(2,1,1)`、`(2,2,1)` 不可用。

### 2. 联合峰位模型

一级衍射遵循 `λ = 2d sin(θ)`。仪器记录的是 2θ，因此对给定零点偏移应先计算：

```text
θ = radians((observed_2theta - δ) / 2)
```

立方晶系满足：

```text
1/d² = (h² + k² + l²)/a²
a = d × sqrt(h² + k² + l²)
```

不得逐峰独立选择局部最优晶面后直接平均。应在给定晶格常数范围、零点偏移范围和 FCC 允许反射集合中寻找一个公共模型，使最多有效峰能被同一 `a` 和 `δ` 解释。

### 3. 异常峰

用最终公共模型预测每个峰的仪器 2θ。若 `abs(observed_2theta - predicted_2theta) > peak_position_tolerance_deg`，则该峰为异常。不能分配允许 FCC 反射、校正后无有效布拉格角或候选晶格常数越界的峰同样为异常。异常峰不能参与顶层晶格常数、零点偏移或尺寸估计，但仍必须出现在结果中。

### 4. 仪器展宽校正与 Scherrer 尺寸

仅对已索引的非异常主相峰计算尺寸。`fwhm_deg` 和 `instrument_fwhm_deg` 都是 2θ 的角度宽度，计算前必须转为弧度。按高斯近似：

```text
β_sample = sqrt(β_observed² - β_instrument²)
```

如果 `β_observed <= β_instrument`，该峰没有可用的正样品展宽，`corrected_fwhm_deg` 和该峰的 `crystallite_size_nm` 都必须为 `null`；不得强行写为零、无穷大或任意有限数。

对有效峰使用 Scherrer 公式：

```text
D = K × λ / (β_sample × cos(θ))
```

其中 `K` 为 `shape_factor`，`λ` 为 Å，`β_sample` 与 `θ` 都为弧度；输出时将 Å 转为 nm。顶层尺寸应为有效主相非异常峰尺寸的稳健汇总，异常峰和不可校正展宽峰不可拉偏结果。

### 5. 单位与兼容性

同一物理波长分别表示为 Å、nm 或 pm 时，晶格常数、零点偏移、峰索引、异常判定和尺寸应在数值容差内等价。请保留公开函数和命令行参数兼容，不引入需要联网下载的运行时依赖，也不得硬编码示例峰 ID、数值或预期输出。
