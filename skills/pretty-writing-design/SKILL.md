---
name: pretty-writing-design
description: Create or revise an evidence-backed Java/Spring Design contract for a later Apply execution.
---

# 编写 Design

把 PRD 和真实仓库事实收敛为可评审、可执行的技术合同。Design 定义外部边界、职责、数据所有权、依赖方向、运行时语义、模型、风险和行为级实施影响；不选择业务结果，不复制完整源码，也不证明真实实现质量。

## 输入、证据与交付

- 读取同目录 `prd.md`、适用 Context/Context Map/ADR、构建配置和受影响真实代码；仓库事实必须有来源，不猜测 API、Schema 或依赖。
- 首次调查前用 `scripts/design_run.py freeze` 冻结 PRD、AGENTS、Skill 和共享协议版本；随后一次 `evidence`，成稿后 `bind-candidate`，最后 `freshness` 与 `preflight`。所有运行证据必须位于 `docs/pretty/<topic>/tmp/<run-id>/`，具体参数以脚本帮助为准。
- 默认写入 `docs/pretty/<topic>/design.md`，topic 使用小写 kebab-case。完成后停止，请用户 Review；后续由用户调用 `$pretty-executing` Apply。
- 交付只能声明“已通过机械、证据和新鲜度检查，等待用户 Review”；不生成 Design Reviewer receipt，也不启动独立 Reviewer。真实实现质量只在 Apply 最终 Gate 证明。
- 临时文件和本地命令按 [运行授权](../pretty-common/references/runtime-authorization.md) 执行；正常交付后用 `design_run.py cleanup` 清理登记产物，中断时保留 run 目录供恢复。

## Design 合同门禁

- 业务语义、外部合同、职责归属、数据所有权、依赖方向、一致性和长期扩展点必须关闭未知项；业务语义不明返回 PRD，技术合同不明停止并请求澄清，不能把未知项推给 Execution。
- 只描述一次真实受影响链路：入口 → caller/callee → Adapter → 持久化或外部系统。设计边界只表达系统与外部参与者、服务、消息基础设施和调度器的合同；内部模块和逐方法调用树属于实施影响。
- 不写完整 Java、完整测试、执行命令、执行结果、覆盖率数字或质量自评。配置数据 DML、事件定义、模板关系、白名单、种子/reference data、激活/禁用/回滚由人工运维负责；结构性 DDL 只能声明为代码库文件交付且不执行。
- Design 不得要求新增无领域归属的通用规范化 Helper（如 `normalizeText`），也不得用 `continue`、空值降级、步骤注释等普通实现指令削弱共享质量规则；例外必须绑定具体 Symbol 和事实证据。

## 固定文档结构

最终文档严格使用以下六个二级章节：

1. `设计结论`
2. `方案全景`
3. `关键设计与权衡`
4. `设计边界`
5. `实施影响`
6. `验证与风险`

`实施影响` 必须包含变更职责链路和至少一个结果 TASK。每个 TASK 必须按 [Design 模板](assets/design.md) 提供：`REQ/AC` 追溯、可观察结果、输入与不变量、可区分失败语义、公共验证入口、影响锚点、验证观察面、Execution 交付和人工运维产物。TASK 按可观察结果垂直拆分，不按 Controller/Service/Repository 横向拆分；每个 PRD 需求和验收标准都要映射，明确非实施项除外并说明原因。

## 质量检查与用户 Review

机械校验负责章节、TASK 字段、REQ/AC 覆盖、占位内容、Mermaid 和 DDL/DML 归属；证据流程负责来源哈希和候选绑定。共享质量原则、路由和运行授权按需读取：

- [质量基线](../pretty-common/references/quality-principles.md)
- [质量路由](../pretty-common/references/quality-routing.md)
- [运行授权](../pretty-common/references/runtime-authorization.md)

校验通过后请求用户 Review。用户审批的是业务和技术合同，不等于实现质量批准；Execution 首次写代码前还必须完成合同可执行性预检，发现缺失即返回 Design。

## 红线

- 不创建 `plan.md` 或新的规范阶段。
- 不修改 PRD、生产代码、测试代码、配置数据或治理文档；Context/ADR 由 `domain-modeling` 维护。
- 不把逐文件实施计划冒充设计边界，不保留占位词、待定技术选择或未经证据支持的兼容承诺。
- 不把配置数据 DML、发布、部署、激活、回滚或数据库执行分配给 Execution。
