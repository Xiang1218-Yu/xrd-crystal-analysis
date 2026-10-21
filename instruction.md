# 粉末 X 射线衍射分析器的物理一致性修复

你接手的是一个用于分析粉末 X 射线衍射峰的 Python 工具。它读取一个 JSON 文件，依据给定的 X 射线波长和一组实验峰位，计算每个峰的晶面间距，并在给定的候选晶面指数中寻找与立方晶体模型一致的 `(h, k, l)`，最后估计晶格常数并标记无法由同一晶格解释的峰。

请在保留命令行接口和 JSON 字段结构的前提下修复程序，使它适用于常见的立方晶系粉末衍射分析。完成后，下面的命令必须继续可用：

```bash
python3 src/xrd_analyzer.py --input examples/peaks.json --output /tmp/xrd-result.json
```

## 输入约定

- `wavelength` 是一个对象，包含数值 `value` 和单位 `unit`。支持 `angstrom`、`nm`、`pm` 三种单位；内部计算统一使用 Å。
- 每个 `peaks` 元素至少包含 `id`、`two_theta_deg` 和 `intensity`。`two_theta_deg` 是衍射仪记录的 2θ 角，单位为角度制；峰强度只用于保留原始观测信息，不改变几何计算。
- `candidate_hkls` 是候选晶面指数数组。每个指数由三个非负整数构成，但 `(0, 0, 0)` 不是有效晶面。
- `crystal_system` 固定为 `cubic`。立方晶系满足 `1/d² = (h²+k²+l²)/a²`。
- `lattice_parameter_bounds_angstrom` 给出材料可能晶格常数的合理范围，两个端点都包含；`outlier_tolerance` 是以 Å 表示的晶格常数残差阈值。
- 输入数据是按照固定晶体模型和布拉格定律生成的可复现仿真数据，不代表真实实验采集记录。

## 输出约定

输出 JSON 必须包含：

- `crystal_system`：原样保留输入晶系；
- `lattice_parameter_angstrom`：由非异常峰估计的晶格常数；
- `peaks`：与输入峰一一对应的结果数组，每项保留 `id`、`intensity`，并新增：
  - `d_spacing_angstrom`；
  - `assigned_hkl`，格式为长度为 3 的整数数组；
  - `lattice_parameter_angstrom`；
  - `residual_angstrom`；
  - `anomalous`，布尔值。
- `anomalous_peak_ids`：所有被标记为异常的峰 ID，顺序与输入一致。

计算时请遵守以下科学约束：

1. 布拉格定律为 `nλ = 2d sin(θ)`，本题取一级衍射 `n = 1`。仪器字段是 `2θ`，计算三角函数前必须先得到 `θ`。
2. Python 的三角函数使用弧度；输入角度是度数。波长单位转换不能改变物理结果。
3. 对立方晶系，单个峰在候选 `(h,k,l)` 下对应的晶格常数为 `a = d * sqrt(h²+k²+l²)`。
4. 先在给定的晶格常数合理范围内筛选候选，再使用各峰候选值之间的一致性估计公共晶格常数；明显偏离公共晶格常数的峰应标记为异常，异常峰不能拉偏最终估计。
5. 不应通过删除峰、跳过计算或硬编码示例文件中的结果来规避约束。

请保持现有公开函数和命令行参数兼容，避免引入需要联网下载的运行时依赖。完成后至少执行构建/语法检查，并用多个不同波长和单位的输入自检。
