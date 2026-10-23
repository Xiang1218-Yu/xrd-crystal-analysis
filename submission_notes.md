# Submission Notes

题目类型：D 科学计算 → 化学与材料
分类标识：D

本题要求修复 FCC 金属粉末 X 射线衍射分析器，涉及布拉格定律、FCC 消光规则、公共晶格参数与仪器零点偏移联合拟合、仪器展宽校正和 Scherrer 尺寸估计。

行为追溯：19 个测试函数均在 docstring 中登记唯一 Case ID，并引用 `instruction.md` 对应原文；拒收测试断言非零退出码、题面授权的 `stderr` 固定标识、既有输出字节不变以及目录无额外临时文件。成功路径只通过 `--output` 提交 JSON，不把 `stdout` 当作业务结果。
