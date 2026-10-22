# 含零点偏移的粉末 X 射线衍射联合索引修复

你接手的是一个用于分析立方晶系粉末 X 射线衍射（XRD）峰位的 Python 工具。仪器记录的峰位除了来自布拉格定律，还可能带有一个对所有峰相同的 `2θ` 零点偏移。程序需要从包含离群峰的测量数据中，**联合**估计晶格常数、零点偏移和每个峰的晶面指数。

请在保留现有命令行接口和已有 JSON 字段结构兼容的前提下修复程序。以下命令必须继续可用：

```bash
python3 src/xrd_analyzer.py --input examples/peaks.json --output /tmp/xrd-result.json
```

输入数据由固定物理模型生成，可复现，但不代表真实实验采集记录。

## 输入约定

- `wavelength` 是一个对象，包含数值 `value` 和单位 `unit`。支持 `angstrom`、`nm`、`pm`，内部计算必须统一为 Å。
- `peaks` 中每个元素至少包含 `id`、`two_theta_deg` 和 `intensity`。`two_theta_deg` 是仪器记录的 2θ（角度制）。强度只用于保留原始观测，不可用来跳过或改变几何计算。
- `candidate_hkls` 是候选晶面指数数组；每项由三个非负整数组成，`(0, 0, 0)` 无效。
- `crystal_system` 固定为 `cubic`；`lattice_parameter_bounds_angstrom` 是晶格常数的闭区间。
- `zero_shift_bounds_deg` 是共同仪器零点偏移 `δ` 的闭区间，单位为度。生成数据遵循：`observed_2theta = ideal_2theta + δ`。
- `peak_position_tolerance_deg` 是单峰预测 2θ 残差的绝对容差，用于判定异常峰。
- 既有 `outlier_tolerance` 字段必须继续接受，用于与旧输入兼容；新输入的异常判定以 `peak_position_tolerance_deg` 为准。

## 输出约定

输出 JSON 必须保留原有字段，并新增/满足以下字段：

- `crystal_system`：原样保留；
- `lattice_parameter_angstrom`：仅由非异常峰给出的公共晶格常数估计；
- `zero_shift_two_theta_deg`：估计的共同 2θ 零点偏移；
- `peaks`：与输入顺序一一对应，每项保留 `id`、`intensity`，并包含：
  - `d_spacing_angstrom`；
  - `assigned_hkl`：长度为 3 的整数数组；
  - `lattice_parameter_angstrom`：该峰按最终索引、校正零点偏移得到的候选晶格常数；
  - `residual_angstrom`：该候选与公共晶格常数的绝对差；
  - `predicted_two_theta_deg`：最终公共模型对该晶面的预测仪器 2θ（包含估计零点偏移）；
  - `two_theta_residual_deg`：记录峰位与预测峰位的绝对差；
  - `anomalous`：布尔值。
- `anomalous_peak_ids`：全部异常峰 ID，顺序与输入一致。

## 科学与行为约束

1. 布拉格定律为 `λ = 2d sin(θ)`，取一级衍射。仪器字段是 2θ；反算 `d` 前，必须先用估计的 `δ` 校正仪器 2θ，再除以 2 得到 θ，并将角度转换为弧度。
2. 对立方晶系，`1/d² = (h²+k²+l²)/a²`，故候选晶格常数为 `a = d × sqrt(h²+k²+l²)`。正向预测时应使用该关系和布拉格定律，最后再加上 `δ` 得到仪器 2θ。
3. 不得独立地为每个峰选择局部最优晶面后再平均。应在 `lattice_parameter_bounds_angstrom` 与 `zero_shift_bounds_deg` 内寻找能使最多有效峰同时一致的公共模型；候选峰索引、晶格常数和零点偏移必须联合确定。
4. 使用最终公共模型计算每个峰的预测 2θ。若其绝对峰位残差严格大于 `peak_position_tolerance_deg`，则该峰为异常；异常峰不可参与最终公共晶格常数和零点偏移估计。
5. 波长改为物理等价的 `nm` 或 `pm` 输入时，晶格常数、零点偏移、峰索引和异常判定应保持等价。
6. 不得通过硬编码示例中的峰 ID、数值或预期输出，删除输入峰，或跳过异常峰计算来规避约束。

请保持现有公开函数和命令行参数兼容，不引入联网下载的运行时依赖。完成后至少执行语法检查，并自行验证正、负零点偏移、不同波长单位与多个异常峰情形。
