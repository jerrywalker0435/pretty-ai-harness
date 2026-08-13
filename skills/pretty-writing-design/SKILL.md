---
name: pretty-writing-design
description: Use when creating, revising, or reviewing a Pretty design.md for a Java/Spring change after its PRD has been approved and before implementation planning.
---

# 编写 Java/Spring Design

## 目标

把已批准 PRD 和真实仓库约束转化为供上下游与技术团队评审的技术合同。Design 锁定边界、契约、关键决策、验证限制和剩余风险，不展开逐文件实施或完整代码。

**REQUIRED SUB-SKILL：** 完整读取并使用 `pretty-java-spring-core` 的共享合同、Design 模板和 Java/Spring 质量检查。本 Skill 是本阶段唯一流程控制器。

## 工作流

### 1. 确认模式与输入

宣布使用 `pretty-writing-design`。用户只要求评估、检查或 Review 时进入只读评审；要求创建或修订时进入写作模式。

写作模式读取已由用户批准的：

```text
docs/pretty/<topic>/prd.md
```

缺失、未批准、含占位或外部结果仍不唯一时，返回 PRD。读取共享合同要求的领域上下文，唯一输出为：

```text
docs/pretty/<topic>/design.md
```

已有文件原地修订。简单变更仍保留七章，但内容可极短。

### 2. 执行只读评审

读取用户给出的 Design、必要 PRD、源码、测试、配置和领域上下文；不修改、移动或复制文件，不更新领域文档，不生成 Plan。

依次输出：阻塞问题、重要改进、上下游与 Plan 影响、`可进入 Plan / 修正后再进入 Plan`，然后停止。每条发现说明位置、证据或限制、影响和建议。只有标准文档链运行机械校验；结论不等于用户批准。

### 3. 建立事实并关闭技术未知

检查足以支持决策的入口、调用链、职责、领域对象、持久化、外部合同、配置和 UT 边界，区分 PRD 要求、仓库事实和设计选择。仓库事实使用相对路径加 symbol/test/config；个人绝对路径或私有资料不能充当团队证据。

事实能决定时自行查明；只有共享合同的四项条件同时成立时才使用 `grilling`，一次解决一个高影响技术决策。外部结果不清楚返回 PRD。Design 获批前不能残留会迫使 Plan 决定架构、契约、所有权、一致性或验证声明的未知项；外部资源是否已存在不是此类未知。


### 4. 应用共享质量路由

按照共享合同“质量 Skill 路由”中的 Design 行判断，只完整读取实际触发的 Skill；未命中时不加载。

将有效发现落实到仓库事实、`DEC`、边界契约或风险。发现改变 `REQ/AC` 时返回 PRD；不创建 Skill 调用清单。

`domain-modeling` 按共享合同同步 `CONTEXT.md`、必要的 `CONTEXT-MAP.md` 与 ADR；改变 `REQ/AC` 时返回 PRD。不要无条件调用全部能力，不在 Design 使用实现期代码审查或 Spring 测试技术 Skill。有效发现落实到事实、`DEC`、契约或风险，不创建 Skill 清单章节。

### 5. 编写 Design

严格使用七章模板：

- 所有 Design 提供 3–6 行摘要。
- 复杂流程使用固定 ASCII 工具；两个以上高影响 `DEC` 增加索引；跨团队合同增加契约矩阵。
- 一个 `DEC` 只回答一个可独立挑战的问题，包含驱动因素与相关 `REQ`、候选或证据、采用方案与理由、后果、重新评估条件。
- 明确职责、依赖方向、主流程、输入输出、错误、一致性、兼容和适用运行风险。
- 验证策略映射 `AC` 与技术风险到稳定 Pretty 内验证边界，并列 Pretty 外未验证范围和声明限制；真实数据库、服务、部署或 Reviewer 不构成下游门禁。
- 只用短签名或伪代码澄清合同；不写逐文件任务、完整实现、完整测试、fixture、Mock 操作或执行命令。

`DEC` 写选择的直接正负后果；“风险与回退”只汇总设计未消除的剩余风险、缓解、回退和恢复验证，避免与发布/观测重复。

### 6. 自审、校验并请求 Review

确认全部 `REQ/AC` 有真实落点，职责、依赖、接口、错误、一致性、兼容、验证限制和风险互相一致，无需求越权、实现泄漏、未知决策、个人路径或占位内容。运行：

```bash
python3 <pretty-java-spring-core-dir>/scripts/validate-pretty-docs.py \
  docs/pretty/<topic> --through design
```

告知路径、主要 `DEC`、领域文档/ADR 变更和校验结果，请求一次用户 Review，然后停止。不得自动进入 Plan。

## 红线

- 不替 PRD 决定外部结果。
- 不为展示完整性制造候选、接口、模式或 `DEC`。
- 不把内部实现细节伪装成技术合同。
- 不以外部环境、独立 Reviewer 或非 UT 测试作为 Plan/Execution 门禁。
- 不在只读评审中修改文件。
