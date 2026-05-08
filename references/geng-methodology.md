# 耿同学论文造假识别方法论

This reference condenses the user-provided methodology. Use it as the primary audit logic for paper images, tables, and experimental data.

## 1. 图片造假识别：同一底片，不同结果

Look for conflicts between image identity and experimental labels:

- Same mouse posture/body outline with different fluorescence intensity.
- Same visual subject marked as different groups or treatment conditions.
- Reused image across different figures, panels, or experiments.
- "Image misuse" is less plausible when the same subject carries different signal layers.

Judgment target: not merely visual similarity, but a contradiction between shared visual identity and claimed experimental meaning.

## 2. 数据重复识别：复制粘贴和低级改写痕迹

Check for:

- Entire columns or multiple columns repeated.
- Long consecutive repeated sequences.
- Same fractional decimals with different integer parts.
- One column created from another by a fixed add/subtract offset.
- Values that are not identical but look lightly modified after copying.

Interpretation: exact repeats suggest copy-paste; near repeats can be more suspicious when they look manually disguised.

## 3. 末位数字分析：人脑编数痕迹

For continuous measurements such as weight, organ mass, fluorescence intensity, cell proportion, and concentration:

- Terminal 0 or 5 concentration.
- Uneven first/second/third decimal-place distribution.
- Overly tidy decimal endings.
- Too many values ending in 0, 5, 8, 9, 99, 100, 500.

This is often more useful than Benford for ordinary experimental data because many paper datasets have narrow ranges.

## 4. 数学关系检查：生成方向是否反了

Check whether:

- Percentages match raw counts after reasonable rounding.
- count / proportion implies the same denominator too often.
- A percentage column looks chosen first, with counts reverse-engineered later.
- Columns have fixed add/subtract/multiply relationships.
- Many values "just happen" to satisfy a special multiple or denominator rule.

Strong suspicion arises when data seem generated backward: desired percentages first, raw counts later.

## 5. 分布和趋势检查：曲线是否过于同款

Plot extracted numeric series when possible:

- Multiple groups have surprisingly identical trends.
- Curves look transformed from one template by add/subtract/multiply/divide.
- Noise is too smooth or too similar across independent groups.
- Values avoid natural outliers or biological variation.

Question: does the data texture look naturally generated or spreadsheet-templated?

## 6. 实验常识检查：数据是否像实验产生的

Use domain priors:

- Measurement precision should fit instrument and experimental convention.
- Mouse weight, organ weight, cell percentages, fluorescence, and similar measures should show natural variation.
- "Raw data" can become stronger evidence if it is mathematically tidy but experimentally implausible.

Report when something is mathematically valid but experimentally unnatural.

## 7. 作者回应反查：解释压力测试

When authors or the paper itself offer explanations, test them:

- Can rounding explain all decimal regularities?
- If image misuse, why did signal intensity or labels also change?
- Does "raw data" introduce new contradictions?
- Does one explanation cover the entire anomaly network, or only one local issue?

Real mistakes usually admit a consistent explanation. Fabricated explanations often create new test points.

## Reusable Order

1. Images: same image, same subject, different signal/label.
2. Tables: exact repeats, repeated sequences, fixed differences.
3. Digits: terminal 0/5 concentration and over-neat decimals.
4. Formulas: counts, percentages, ratios, denominators, rounding.
5. Distributions: template-like curves and unnatural smoothness.
6. Explanations: pressure-test benign explanations against all evidence.
