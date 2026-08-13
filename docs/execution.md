# 未及时收台与擦台事件附加手表触达 Execution

## 输入与基线

- Plan：`docs/pretty/table-not-done-additional-watch-touch/plan.md`
- 执行开始 HEAD：`50b90f67cd079163dad94e95491b705d6eba8c3d`
- 工作区归因：执行开始时 staged、unstaged、untracked 均为空；本文件及后续代码、测试、SQL 差异均归因于本次 Execution。临时归因目录位于仓库外 `/private/tmp/table-not-done-execution.H4xx0E`，未写入仓库。
- Plan 基线：`python3 /Users/jerry.zhang/.agents/skills/pretty-java-spring-core/scripts/validate-pretty-docs.py docs/pretty/table-not-done-additional-watch-touch --through plan`，退出码 0，3 份文档通过 Plan 阶段校验。
- Plan 基线：`mvn -pl work-order-common,work-order-domain,work-order-infra,work-order-application,work-order-adapter,work-order-web -am -DskipTests compile`，退出码 0，8 个 Reactor 模块编译成功。
- Plan 基线：`mvn -pl work-order-domain,work-order-infra,work-order-application,work-order-adapter,work-order-web -am -Dtest=WorkOrderExecuteDomainServiceImplTest,WorkOrderParticipantDomainServiceImplTest,WorkOrderParticipantServiceImplTest,EventIngestBizImplTest,EventProcessResultRecorderBizImplTest,WorkOrderLinkageConsumeBizImplTest,WatchMessageRemoteGatewayAdapterTest,EventRequestConvertorTest -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 0，指定相关回归全部通过。
- Plan 基线：`git diff --check`，退出码 0，无空白错误。
- Plan 基线：`mvn -pl work-order-application,work-order-adapter -am -Dtest=EventIngestBizImplTest,EventProcessResultRecorderBizImplTest,WatchMessageRemoteGatewayAdapterTest -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 0，拟修改测试入口全部通过。
- 基线结论：通过，允许进入逐切片 RED/GREEN。

## 执行摘要

按已批准 Plan 执行 3 个 TASK、12 个行为切片。当前处于 TASK-001，最终实施范围、偏差和验证结论将在逐切片完成后补齐。

## 任务证据

### TASK-001 首次受理成功且永久关闭规则与补触达入口

- 状态：执行中
- 实际变更：待逐切片记录
- 任务级完成证据：待验证
- 实质偏差：待审计

#### 行为切片：首次受理为无工单成功

- UT 边界：直接构造 `EventIngestBizImpl`，mock 事件定义、事件记录、编号、主数据、模板编排和附加用例；使用真实未及时事件 policy 与 DTO，不启动 Spring。
- RED：`mvn -pl work-order-application -am -Dtest=EventIngestBizImplTest#shouldAcceptClearTableNotDoneWithoutCreatingWorkOrder -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 1；测试进入业务断言，期望 `ACCEPTED_NO_WORK_ORDER`，实际为 `ACCEPTED_READY_FOR_RULE`。
- GREEN：同一命令退出码 0，1 个测试通过；响应为无工单成功，模板与规则提交零调用，并捕获已落库事件快照组装的附加触达 DTO。

#### 行为切片：入口幂等与附加失败隔离

- UT 边界：连续调用 `EventIngestBizImpl#ingest`；mock 附加用例异常和 `EventRecordGateway#save` 唯一键冲突，回查固定首次记录，不启动 Spring。
- RED：`mvn -pl work-order-application -am -Dtest=EventIngestBizImplTest#shouldKeepAcceptedResultAndNotTouchAgainWhenAdditionalTouchFailsThenEventDuplicates -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 1；首次异常已被隔离、重复分支已提前返回，但重复响应的 `workOrderIds` 实际为 `null`，不满足稳定空集合合同。
- GREEN：同一命令退出码 0，1 个测试通过；首次仍为 `ACCEPTED_NO_WORK_ORDER`，重复为相同事件号的 `IGNORED_DUPLICATE`，空工单集合稳定，附加用例总计仅调用一次。

#### 行为切片：规则入口失败关闭且普通事件兼容

- UT 边界：直接构造 `EventRuleDispatchBizImpl` 和 `EventIngestCmdHandler`；mock 事件记录、转换器、规则服务与领域事件 publisher，使用真实事件 policy。
- RED：`mvn -pl work-order-application -am -Dtest=EventRuleDispatchBizImplTest#shouldSkipRuleDispatchForTableNotDoneEvent -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 1；测试编译明确显示重投服务尚未依赖未及时事件 policy，无法实施失败关闭判断。
- GREEN：同一命令退出码 0；TASK 级命令 `mvn -pl work-order-domain,work-order-application -am -Dtest=TableNotDoneAdditionalTouchPolicyTest,EventIngestBizImplTest,EventIngestCmdHandlerTest,EventRuleDispatchBizImplTest,EventProcessResultRecorderBizImplTest -Dsurefire.failIfNoSpecifiedTests=false test` 退出码 0，共 16 个测试通过；未及时事件不发布、不重投，普通事件仍发布并进入规则服务，新结果码纳入通用成功终态分类。

### TASK-002 唯一选择最新目标工单并完成待认领加急

- 状态：执行中
- 实际变更：`TableNotDoneAdditionalTouchAppServiceImpl#touchSafely`、`TableNotDoneWorkOrderQuery`、`WorkOrderRecordGateway#listTableNotDoneCandidates`、`WorkOrderService#listTableNotDoneCandidates`、`WatchMessageRemoteGateway#upgradeWorkOrderMessageToUrgent`
- 任务级完成证据：待验证
- 实质偏差：待审计

#### 行为切片：固定映射、发生日窗口与唯一目标

- UT 边界：直接构造真实附加应用服务、policy 和账单解析器；mock 候选工单领域端口与手表端口。
- RED：`mvn -pl work-order-application -am -Dtest=TableNotDoneAdditionalTouchAppServiceImplTest#shouldSelectFirstMatchingBillWithinOccurredDayAndUpgradeWaitClaimWorkOrder -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 1；领域窄查询类型不存在，符合预期能力缺口。
- GREEN：同一命令退出码 0，1 个测试通过；查询固定 `CLEAR_TABLE`、三个目标状态及 `[2026-08-13 00:00, 2026-08-14 00:00)`，倒序候选首张同账单 `WO-200` 被唯一加急。

#### 行为切片：账单缺失或候选不匹配时零触达

- UT 边界：真实 `TableBillIdResolveSupport` 与附加应用服务，mock 候选查询和手表端口；覆盖根节点 `tableBillId`、`orderId`、字符串化 `detail`、非法 JSON、缺失和不匹配场景。
- RED：首次特征测试即通过；该行为已由上一切片完成的真实解析器复用和顺序扫描实现满足，未制造虚假 RED。
- GREEN：`mvn -pl work-order-application -am -Dtest=TableBillIdResolveSupportTest,TableNotDoneAdditionalTouchAppServiceImplTest#shouldSkipTouchWhenEventBillMissingOrCandidatesDoNotMatch -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 0，2 个测试通过；缺失/不匹配均零触达，单候选非法 JSON 后继续扫描。

#### 行为切片：候选 SQL 条件与稳定排序

- UT 边界：直接构造 `WorkOrderServiceImpl`，mock mapper 和其他构造依赖，捕获 MyBatis `LambdaQueryWrapper`；不启动 Spring、不连接数据库。
- RED：`mvn -pl work-order-infra -am -Dtest=TableNotDoneWorkOrderQueryServiceTest -Dsurefire.failIfNoSpecifiedTests=false test` 首次退出码 1，测试读取 wrapper 参数早于 SQL segment 初始化；调整测试初始化顺序后再次退出码 1，暴露纯 UT 缺少 MyBatis lambda 元数据。两次均为测试夹具问题而非生产合同缺口。
- GREEN：初始化 `TableInfoHelper` 后同一命令退出码 0，2 个测试通过；wrapper 包含 `state=0`、门店/桌台/模板、三个状态、左闭右开窗口以及 `create_time DESC, work_order_id DESC`，缺关键维度时 mapper 零调用。同步新增并在基线 DDL 维护 `idx_work_order_not_done_lookup`。

#### 行为切片：待认领原消息加急适配

- UT 边界：应用 UT mock 手表领域端口；adapter UT 直接构造适配器并反射注入 mock `MessageCallbackRemote`，不启动 Spring。
- RED：首次 adapter 特征测试即通过；加急端口及适配已作为“固定映射、发生日窗口与唯一目标”的最小 GREEN 跨层编译合同实现，未制造虚假 RED。
- GREEN：`mvn -pl work-order-adapter -am -Dtest=WatchMessageRemoteGatewayAdapterTest#should_upgrade_single_work_order_message_with_configured_source -Dsurefire.failIfNoSpecifiedTests=false test`，退出码 0；远端精确收到 `(["WO-200"], "WATCH")`，应用分支不调用完成回调。

### TASK-003 恢复当前有效手表接收人并发送专用二次提醒

- 状态：待执行
- 实际变更：待执行
- 任务级完成证据：待验证
- 实质偏差：待审计

## 测试与验证结果

- 受影响模块编译：待最终验证
- 本次全部新/改 UT：待最终验证
- 直接相关回归 UT：待最终验证
- 快速静态检查：待最终验证
- 覆盖率：待最终验证
- 实际声明范围：待最终审计

## 偏差与未验证范围

- 相对 Plan 的实质偏差：待最终审计
- 工作区归因限制：当前无
- Pretty 外未验证范围：生产 MySQL 数据分布、索引选择和查询耗时；运行时事件定义的来源、启停、点位和 payload schema 配置；历史参与关系及执行快照完整率；真实云手表字段兼容、超时状态、去重效果、送达和设备展示；部署、灰度、指标与告警。
- 声明限制：不得据本地代码与 UT 声称生产索引必然命中、历史数据全部可解析、真实员工已收到提醒或外部配置已经生效。

## 最终审计与结论

### 自动审计

- 核对范围：待最终审计
- 发现与处置：待最终审计
- 新鲜证据核对：待最终验证
- Execution 机械校验：待最终验证

### 最终结论

- 状态：执行中
- 交付范围：待最终审计
- 后续授权边界：不自动 commit、push、创建 MR、合并或发布。
