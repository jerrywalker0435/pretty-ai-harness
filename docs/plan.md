# 未及时收台与擦台事件附加手表触达 Plan

## 输入与范围

- PRD：`docs/pretty/table-not-done-additional-watch-touch/prd.md`
- Design：`docs/pretty/table-not-done-additional-watch-touch/design.md`
- 领域语言：`CONTEXT.md`
- 目标代码范围：`work-order-common` 的事件常量与文案、`work-order-domain` 的未及时事件策略和端口合同、`work-order-application` 的事件受理/规则隔离/附加触达编排、`work-order-infra` 的候选工单查询、`work-order-adapter` 的云手表适配，以及 `sql` 的查询索引迁移。
- 不变边界：不改变现有事件上报 Qo/Vo 和开放接口字段；不创建、重开、取消或修改工单及参与关系；不复用模板规则执行和 `DeviceDeliveryGateway`；不新增触达重试、补偿或独立幂等表；不把目标工单或触达结果返回上游；不修改 `CONTEXT.md`、ADR 或已批准的 PRD/Design。
- 本阶段唯一制品为本 `plan.md`；不写生产代码或测试，不执行 RED/GREEN，不操作 Git。

## 实施摘要

实施按三个行为闭环推进：先让两类未及时事件以 `ACCEPTED_NO_WORK_ORDER` 首次受理并关闭所有规则入口，再通过有界查询和统一账单解析选出唯一最新工单并完成待认领加急，最后恢复执行中/已完成工单的当前有效手表接收人并发送固定二次提醒。事件唯一键仍是唯一启动闸门，附加流程保持事务外同步尝试和双层失败隔离。新增应用代码只依赖领域端口，infra 与 adapter 分别封装数据库和云手表细节。所有行为测试均为不启动 Spring 的 UT，数据库执行计划、真实设备送达和运行时事件定义配置不作为本地完成门禁。

| TASK | 可观察行为 | 主要文件/模块 | 主要风险 | UT 边界 |
| --- | --- | --- | --- | --- |
| `TASK-001` | 首次未及时事件成功受理但不建单；重复、领域事件发布和显式重投均不触发规则或补触达 | `work-order-common`、`work-order-domain`、`work-order-application` | 入口幂等被绕过、结果码被误当待处理、附加异常污染响应 | 直接构造事件受理、命令处理和规则重投对象，mock 持久化及应用边界 |
| `TASK-002` | 仅从发生日内固定类型候选中选出同账单最新工单；待认领只加急原消息 | `work-order-domain`、`work-order-application`、`work-order-infra`、`work-order-adapter`、`sql` | 日期边界、排序不稳定、账单兼容分叉、同步查询性能 | 真实策略/解析器/应用对象配合 mock 领域端口；捕获 MyBatis wrapper 和远端请求 |
| `TASK-003` | 执行中/已完成仅向当前最大派发轮次的有效手表员工发送专用提醒，任何失败均不改事件或工单 | `work-order-domain`、`work-order-application`、`work-order-adapter` | 渠道误判、历史人员误发、接收人重复、超时歧义和状态竞态 | 真实接收人过滤与命令对象，mock 参与关系端口和云手表 client，断言完整边界命令 |

## 代码事实与约束

### 已核实代码事实

- `work-order-application/src/main/java/com/haidilao/workorder/application/event/command/ingest/EventIngestBizImpl.java#ingest`：入口先保存事件草稿，再回写受理结果；数据库唯一键冲突时回查并返回 `IGNORED_DUPLICATE`；当前只有 `ACCEPTED_READY_FOR_RULE` 会进入模板触发编排，方法没有事务注解。
- `sql/work_order_mysql.sql#t_event_record`：`uk_event_type_source_event(event_type_code, source_event_id)` 已精确覆盖事件身份，可裁决串行和并发首次插入。
- `work-order-application/src/main/java/com/haidilao/workorder/application/event/executor/command/ingest/EventIngestCmdHandler.java#execute`：领域事件发布是 `ACCEPTED_READY_FOR_RULE`、`ACCEPTED_DELAYED_TRIGGER_PENDING` 白名单；不把新结果码加入即可保持规则异步入口关闭。
- `work-order-application/src/main/java/com/haidilao/workorder/application/event/command/dispatch/EventRuleDispatchBizImpl.java#dispatchToRule`：显式重投当前会对任意已存在事件直接调用 `EventProcessAppService`，必须增加未及时事件失败关闭保护。
- `work-order-application/src/main/java/com/haidilao/workorder/application/event/command/ingest/EventRuleDispatchAsyncExecutor.java#isTerminalResultCode` 与 `work-order-application/src/main/java/com/haidilao/workorder/application/event/command/process/EventProcessResultRecorderBizImpl#shouldClearFailReason`：均维护通用事件终态/成功分类；新增结果码应归为无工单成功终态。固定任务和工单联动专用 accepted 集合只服务建单语义，不应加入该码。
- `work-order-application/src/main/java/com/haidilao/workorder/application/workorder/support/TableBillIdResolveSupport.java#resolve`：已支持根节点 `tableBillId`、兼容 `orderId` 和字符串化 `detail`，解析失败返回空值，目标选择必须直接复用该口径。
- `work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/gateway/WorkOrderRecordGateway.java#listByQuery` 与 `work-order-infra/src/main/java/com/haidilao/workorder/infra/core/repository/workorder/WorkOrderServiceImpl#buildListByParamWrapper`：现有查询没有创建时间窗口，并按 `create_time ASC, id ASC` 排序，不能改造为本场景查询而影响既有调用方。
- `work-order-infra/src/test/java/com/haidilao/workorder/infra/core/repository/workorder/WorkOrderServiceImplTest.java`：测试类被类级 `@Disabled` 禁用；本需求必须新增独立、启用的窄查询 UT，不能把查询合同放入该类后误以为已执行。
- `work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/gateway/WorkOrderParticipantGateway.java#listCurrentByWorkOrderIdsAndRoles` 与 `work-order-infra/src/main/java/com/haidilao/workorder/infra/gatewayimpl/workorder/WorkOrderParticipantGatewayImpl#loadParticipantRelations`：现有只读领域端口已经限定 `state=1`、`is_current=1`、`relation_status=ACTIVE` 并返回员工和 `dispatchRound`，新应用用例无需直连 participant repository。
- `work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/model/entity/WorkOrderRecordEntity#readExecuteSnapshotText`：可失败关闭地读取执行配置快照字段；正常执行链路对空值和未知 `touchPoint` 默认按 `WATCH` 兼容。
- `work-order-domain/src/main/java/com/haidilao/workorder/domain/shared/gateway/remote/WatchMessageRemoteGateway.java` 与 `work-order-adapter/src/main/java/com/haidilao/workorder/adapter/remote/outbound/watch/WatchMessageRemoteGatewayAdapter.java`：现有端口只提供消息完成回调，但已经封装来源编码和远端失败异常风格。
- 本地依赖字节码已核实：`MessageCallbackRemote.upgradeMessageToUrgent(List<String>, String)`、`PushEventRemote.pushEvent(RemoteMessageDto)` 可用；`RemoteMessageDto` 支持固定标题、正文、门店、桌号、`businessId`、接收人和 `businessIdDedup`。
- 根 `pom.xml` 固定 JDK 1.8、Surefire 3.2.5；仓库没有 JaCoCo 插件、增量阈值或其他明确覆盖率政策。

### 上游约束

- `REQ-001`、`REQ-007`、`REQ-008`、`REQ-009`、`REQ-010` / `AC-001`、`AC-009`、`AC-010`、`AC-011` / `DEC-001`：只有基础校验通过且首次成功回写结果的未及时事件启动一次同步附加触达；重复、跳过或失败后均不补触达，响应始终与触达结果隔离。
- `REQ-002`、`REQ-003`、`REQ-011` / `AC-002`、`AC-003`、`AC-004`、`AC-012` / `DEC-002`：事件到模板固定映射，按 `occurredAt` 自然日左闭右开查询，并按 `create_time DESC, work_order_id DESC` 的既定快照选首个同账单候选；之后不重查、不换分支。
- `REQ-004`、`REQ-005`、`REQ-006` / `AC-005`、`AC-006`、`AC-007` / `DEC-003`、`DEC-004`：待认领只调用原消息加急；执行中读取当前有效 `CURRENT_HANDLER`，已完成读取当前有效 `HISTORY_HANDLER`，取最大非空派发轮次并按员工编码去重后发送固定提醒。
- `REQ-012` / `AC-008`、`AC-013`：其他事件继续既有模板、延迟、规则和建单行为；附加用例不能调用任何工单或参与关系写端口，不能改变 API 字段。
- Design 固定二次提醒 `businessId=eventId`、`businessIdDedup=true`，标题与正文不得动态模板化；远端去重只是超时歧义下的第二道保护，不能替代事件入口唯一键。
- Design 已把生产 MySQL `EXPLAIN`、历史参与关系完整率、真实云手表兼容与送达、上游事件定义来源/payload 配置列为 Pretty 外验证，Plan 不为这些外部能力虚构本地完成证据。

### 拟议实现规则

- OOD 审查结论：用一个无状态 `TableNotDoneAdditionalTouchPolicy` 集中事件映射、状态动作和渠道兼容规则；用不可变查询/命令/接收人对象封装跨边界参数；通过构造器注入领域端口。不开第二套策略框架，不新增通用 `action + 可选参数` 命令，也不复制常规规则执行模型。
- 新 application 代码只依赖 `WorkOrderRecordGateway`、`WorkOrderParticipantGateway` 和 `WatchMessageRemoteGateway`；mapper、repository、MyBatis criteria、`RemoteMessageDto` 与 Dubbo client 分别留在 infra/adapter。
- `TableNotDoneAdditionalTouchDTO` 只传 `eventId/eventDefineCode/storeCode/pointCode/occurredAt/payloadData`；领域提醒命令在构造时去空、按员工编码去重并防御性复制，集合永不返回 `null`。
- 所有新增 Java 使用 JDK 8 等价写法；application/domain 核心方法按校验、查询、决策、远程调用和结果隔离添加中文分步注释。
- 新增日志统一使用 `table.not.done.touch.*`，单条最多三个关键字段，只记录 `eventId`、`workOrderId`、`phase/result` 的必要组合，不打印 payload、复杂实体、员工列表或完整远端响应。
- 只新增 UT；不新增或扩展 Spring slice、`@SpringBootTest`、`@DataJpaTest`、Testcontainers、嵌入式数据库、集成测试或端到端测试。

## 实施任务

### TASK-001 首次受理成功且永久关闭规则与补触达入口

- 追溯落点：`REQ-001`、`REQ-007`、`REQ-008`、`REQ-009`、`REQ-010`、`REQ-012`；`AC-001`、`AC-008`、`AC-009`、`AC-010`、`AC-011`、`AC-013`；`DEC-001`。
- 目标行为或风险闭环：两类未及时事件通过既有校验和首次入库后返回稳定无工单成功结果，并且只有当前首次请求同步调用一次附加用例；重复、领域事件发布和显式规则重投均不能进入模板/规则/建单路径。
- 已核实代码事实：`EventIngestBizImpl#ingestAndPersist` 当前统一回写 `ACCEPTED_READY_FOR_RULE`，而 `EventIngestBizImpl#ingest` 对其他结果直接返回；`EventRuleDispatchBizImpl#dispatchToRule` 尚无事件类型过滤。
- 继承约束：沿用现有定义、来源、启停、门店、点位、发生时间、payload schema、草稿保存和唯一键冲突回查；附加触达必须在 `ACCEPTED_NO_WORK_ORDER` 已持久化之后、事件受理事务之外调用；不修改响应 DTO/VO 结构。
- 拟议变更：
  - 在 `work-order-common/src/main/java/com/haidilao/workorder/common/constant/EventConstants.java#EventDefineCode` 增加 `CLEAR_TABLE_NOT_DONE`、`WIPE_TABLE_NOT_DONE`；在 `Constants.Text.Event` 增加固定受理文案“事件已成功受理，不生成工单”。
  - 在 `work-order-domain/src/main/java/com/haidilao/workorder/domain/common/enums/EventResultCodeEnum.java` 增加 `ACCEPTED_NO_WORK_ORDER` 及展示标签；新增 `domain/workorder/tablenotdone/TableNotDoneAdditionalTouchPolicy.java` 和 `TableNotDoneTouchAction.java`，以不可变映射集中 `CLEAR_TABLE_NOT_DONE -> CLEAR_TABLE`、`WIPE_TABLE_NOT_DONE -> WIPE_TABLE` 以及 `WAIT_CLAIM/EXECUTING/COMPLETED` 动作决策。
  - 新增 `work-order-application/src/main/java/com/haidilao/workorder/application/event/command/ingest/tablenotdone/TableNotDoneAdditionalTouchAppService.java` 和 `dto/TableNotDoneAdditionalTouchDTO.java`，合同保持 `void touchSafely(TableNotDoneAdditionalTouchDTO commandDTO)`。
  - 修改 `EventIngestBizImpl#ingestAndPersist`：通过校验的未及时事件回写 `ACCEPTED_NO_WORK_ORDER`、固定文案和空工单集合；修改 `#ingest`：仅该首次持久化分支组装已落库快照 DTO 并同步调用 `touchSafely`，调用边界捕获所有运行时异常后仍 `finish(accepted)`。唯一键冲突回查分支不调用附加用例。
  - 修改 `EventRuleDispatchBizImpl#dispatchToRule`，在加载事件后用同一 policy 识别未及时事件并直接跳过；`EventIngestCmdHandler` 保持原发布白名单，并为 `ACCEPTED_NO_WORK_ORDER` 增加“不发布规则事件”的信息级完成分支，避免把成功受理误记成“未受理”告警；新增日志最多只带 `eventId/eventTypeCode/resultCode` 三个字段。
  - 将 `ACCEPTED_NO_WORK_ORDER` 加入 `EventRuleDispatchAsyncExecutor#isTerminalResultCode` 和 `EventProcessResultRecorderBizImpl#shouldClearFailReason` 的通用终态/成功分类；不加入 `TaskCenterTaskOpsBizImpl`、`TaskCenterPublishStoreRepairBizImpl`、`WorkOrderLinkageConsumeBizImpl` 等要求后续建单的专用 accepted 集合。`OpsEventWebConvertor#resolveResultLabel` 已枚举遍历，无需生产修改即可显示新标签。
  - 修改/新增 UT：`TableNotDoneAdditionalTouchPolicyTest`、`EventIngestBizImplTest`、`EventIngestCmdHandlerTest`、`EventRuleDispatchBizImplTest`、`EventProcessResultRecorderBizImplTest`。
- 真实任务依赖：无。
- 验证入口：上述五个 UT 类；`mvn -pl work-order-domain,work-order-application -am -Dtest=TableNotDoneAdditionalTouchPolicyTest,EventIngestBizImplTest,EventIngestCmdHandlerTest,EventRuleDispatchBizImplTest,EventProcessResultRecorderBizImplTest -Dsurefire.failIfNoSpecifiedTests=false test`。
- 完成证据：Execution 记录两类首次结果的完整字段、附加 DTO 快照、重复/异常分支结果、规则与领域事件零副作用，以及普通事件仍进入原编排入口的回归结果。

#### 行为切片：首次受理为无工单成功

- Given-When-Then：Given `CLEAR_TABLE_NOT_DONE` 或 `WIPE_TABLE_NOT_DONE` 事件定义启用、来源和 payload 校验通过且事件身份从未入库，When 调用 `EventIngestBizImpl#ingest`，Then 最终持久化并返回 `ACCEPTED_NO_WORK_ORDER`，`workOrderId=null`、`workOrderIds=[]`、固定 `reasonDesc`，同步传给附加用例的 DTO 使用已持久化的 `eventId/occurredAt/payloadData`，且模板触发和异步规则提交均不发生。
- UT 边界：直接构造 `EventIngestBizImpl`；真实使用事件类型 policy/DTO，mock 事件定义、事件记录、编号、主数据、payload schema、模板编排和附加用例边界，不启动 Spring。
- 独立预期值：结果码和文案直接取自 `REQ-009`；工单字段为空取自首次响应合同；DTO 字段取固定输入和 mock 返回的事件编号，不通过生产方法重新计算。
- mock/fake/stub 边界：数据库唯一性/持久化、门店/点位主数据和模板/附加用例是系统边界；被测事件分流与结果组装使用真实对象。
- 预期 RED 原因：当前枚举、事件类型分类和附加用例合同不存在，受理只会返回 `ACCEPTED_READY_FOR_RULE` 并调用模板编排。
- 最小 GREEN 条件：新增结果码、共享分类、DTO/用例接口和事件入口专用分支；保持既有校验与 `finish` 结构不变。
- 风险选择性代码：入口顺序固定为 `ingestAndPersist -> resultCode 判断 -> touchSafely 捕获异常 -> finish`；不得在 `touchSafely` 外围新增事务，也不得先触达后回写成功结果。

#### 行为切片：入口幂等与附加失败隔离

- Given-When-Then：Given 首次未及时事件的附加用例抛出运行时异常，When 受理返回，Then 仍得到完整 `ACCEPTED_NO_WORK_ORDER`；Given 相同事件类型和 `sourceEventId` 再次或并发命中唯一键，When 回查到首次记录，Then 返回相同 `eventId` 的 `IGNORED_DUPLICATE` 且不再调用附加用例。
- UT 边界：直接调用事件受理 public API；用 mock `EventRecordGateway#save` 分别模拟成功和 `DuplicateKeyException`，用 mock 附加用例模拟异常，验证响应和边界副作用。
- 独立预期值：首次结果为 `ACCEPTED_NO_WORK_ORDER`，重复结果为 `IGNORED_DUPLICATE`，两个响应工单集合均为空；重复 `processedAt` 使用预置首次记录时间。
- mock/fake/stub 边界：唯一键竞争和远端前置用例是不可在纯 UT 中真实运行的边界；不 mock `EventIngestBizImpl` 内部分支。
- 预期 RED 原因：当前没有附加用例调用与隔离分支，也没有新结果码；重复分支虽存在，但尚不能证明不会补触达。
- 最小 GREEN 条件：只在当前请求获得新结果码时调用一次附加用例，并在入口边界吞掉异常；保留唯一键冲突分支的提前返回。
- 风险选择性代码：不新增防重 token 的 acquire/release，不因异常把事件改回 `PROCESS_FAILED`，也不在重复分支调用补偿逻辑。

#### 行为切片：规则入口失败关闭且普通事件兼容

- Given-When-Then：Given 已落库未及时事件，When 命令处理结束或运营显式调用规则重投，Then 不发布 `EventIngestedEvent`、不调用 `EventProcessAppService`；Given 普通 `ACCEPTED_READY_FOR_RULE` 事件，When 走同样入口，Then 原领域事件发布、转换和规则处理仍发生。
- UT 边界：分别直接构造 `EventIngestCmdHandler` 和 `EventRuleDispatchBizImpl`；mock publisher、事件记录 gateway、convertor 和规则应用服务，真实使用 event policy。
- 独立预期值：发布白名单仍只有两个既有码；未及时事件显式重投结果是无规则副作用，普通事件规则命令包含预置 `eventId`。
- mock/fake/stub 边界：Spring publisher 和规则应用服务是边界；策略分类使用真实对象。对零调用的断言仅证明禁止副作用，并辅以普通事件完整命令断言。
- 预期 RED 原因：显式重投当前会无条件调用规则应用服务，且新结果码尚不存在于终态/成功分类。
- 最小 GREEN 条件：在加载事件后增加共享分类短路，保持原非未及时分支原样；命令处理器将新结果识别为成功但不发布；只扩通用终态分类，不扩大建单专用 accepted 集合。
- 风险选择性代码：事件类型判断必须基于已加载记录的 `eventDefineCode`，不能依赖可能被误写的 `resultCode`；这样即使历史记录被标成失败也不能经重试建单。

### TASK-002 唯一选择最新目标工单并完成待认领加急

- 追溯落点：`REQ-002`、`REQ-003`、`REQ-004`、`REQ-010`、`REQ-011`；`AC-002`、`AC-003`、`AC-004`、`AC-005`、`AC-008`、`AC-010`、`AC-012`；`DEC-002`、`DEC-004`。
- 目标行为或风险闭环：在事件发生日的有界候选中按固定模板和目标状态查询，复用统一账单解析选出唯一最新同账单工单；目标为待认领时只提升该工单原手表消息紧急度。
- 已核实代码事实：现有 `listByQuery` 缺日期窗口且排序方向相反；`WorkOrderRecordEntity` 已包含选择所需的状态、payload、创建时间和执行快照；云手表 client 已提供单独加急 API。
- 继承约束：不修改既有 `WorkOrderActiveQuery/listByQuery` 合同；SQL 只做门店、桌台、模板、状态、自然日和有效记录粗筛，不复制 JSON 账单解析；选择后冻结工单实体快照，不重新查询或切换动作。
- 拟议变更：
  - 新增 `work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/tablenotdone/model/valueobject/TableNotDoneWorkOrderQuery.java`，字段固定为单一 `storeCode/pointCode/templateCode`、目标 `statuses`、`dayStart/nextDayStart`；扩展 `WorkOrderRecordGateway#listTableNotDoneCandidates(TableNotDoneWorkOrderQuery)`。
  - 新增 infra `TableNotDoneWorkOrderSearchCriteria`，扩展 `WorkOrderService`/`WorkOrderServiceImpl` 和 `WorkOrderRecordGatewayImpl`。repository 对关键维度或非法时间窗口失败关闭为空集合，wrapper 固定 `state=0`、等值门店/桌台/模板、三个目标状态、`create_time >= dayStart AND create_time < nextDayStart`、`create_time DESC, work_order_id DESC`。
  - 新增 `TableNotDoneAdditionalTouchAppServiceImpl`：先由 policy 解析固定模板，再用 `TableBillIdResolveSupport` 解析事件账单，按 `occurredAt.toLocalDate().atStartOfDay()` 计算窗口；顺序扫描已倒序候选，首个 trim 后账单精确相等者即目标。事件账单缺失、候选为空或全部不匹配均跳过。
  - 扩展 `WatchMessageRemoteGateway#upgradeWorkOrderMessageToUrgent(String)`；`WatchMessageRemoteGatewayAdapter` 将单工单号包装为单元素集合，用 `WorkOrderWatchProperties.messageSourceFromCode` 调用 `upgradeMessageToUrgent`，空响应、业务失败和异常统一抛内部 `BusinessException`，由应用用例隔离。
  - 新增迁移 `sql/alter_t_work_order_record_add_not_done_lookup_index_20260813.sql`，并在 `sql/work_order_mysql.sql#t_work_order_record` 同步索引 `idx_work_order_not_done_lookup(state, store_code, point_code, template_code, create_time, work_order_id)`；不新增表或字段。
  - 新增/修改 UT：`TableBillIdResolveSupportTest`、`TableNotDoneAdditionalTouchAppServiceImplTest`、独立启用的 `TableNotDoneWorkOrderQueryServiceTest`、`WorkOrderRecordGatewayImplTableNotDoneTest`、`WatchMessageRemoteGatewayAdapterTest`。
- 真实任务依赖：`TASK-001`，复用已确定的事件 policy、DTO、附加用例接口和新结果分流。
- 验证入口：上述五个 UT 类；索引静态检查 `rg -n "idx_work_order_not_done_lookup|create_time|work_order_id" sql/alter_t_work_order_record_add_not_done_lookup_index_20260813.sql sql/work_order_mysql.sql`。
- 完成证据：Execution 记录左右边界、模板/状态/门店/桌台条件、双字段倒序 SQL 片段、三种账单形态、唯一目标工单号、加急远端参数和所有跳过/失败分支结果。

#### 行为切片：固定映射、发生日窗口与唯一目标

- Given-When-Then：Given 事件发生于 `2026-08-13 23:59:59`，倒序候选中依次包含最新但账单不同、次新且同账单、较旧且同账单工单，When 执行附加触达，Then `CLEAR_TABLE_NOT_DONE` 只查询 `CLEAR_TABLE`（另一事件只查询 `WIPE_TABLE`），窗口精确为 `[2026-08-13 00:00:00, 2026-08-14 00:00:00)`，并只对次新的第一张同账单工单执行加急。
- UT 边界：直接调用真实 `TableNotDoneAdditionalTouchAppServiceImpl#touchSafely`；真实 policy 和 `TableBillIdResolveSupport`，mock 工单/参与关系/手表领域端口，捕获完整 `TableNotDoneWorkOrderQuery` 和加急工单号。
- 独立预期值：模板映射取自 `REQ-002`；自然日边界使用固定字面时间；目标工单号为预置 `WO-200`，不通过生产排序或解析方法生成预期值。
- mock/fake/stub 边界：数据库候选返回顺序和云手表调用是边界；映射、时间窗口、账单匹配和首个选择使用真实被测逻辑。
- 预期 RED 原因：当前无窄查询、附加应用实现、固定映射和加急端口。
- 最小 GREEN 条件：完成查询对象/端口、日期计算、顺序账单匹配和 `WAIT_CLAIM` 单一加急分支；不提前实现提醒分支的额外语义。
- 风险选择性代码：候选选择必须是单次顺序扫描；命中后立即冻结 `target`，后续动作只读取该实体的 `workOrderStatus/workOrderId`，不得因远端失败选择下一张。

#### 行为切片：账单缺失或候选不匹配时零触达

- Given-When-Then：Given 事件 payload 无可解析账单，或候选仅在账单、状态、门店、桌台、模板、日期任一条件不满足，When 执行附加触达，Then 不加急、不发送提醒、不查询参与关系；单个候选 payload 解析失败只视为不匹配并继续检查后续候选。
- UT 边界：真实解析器和应用服务，mock 候选查询与远端端口；用根节点 `tableBillId`、根节点 `orderId`、字符串化 `detail` 和非法 JSON 参数化覆盖。
- 独立预期值：三个兼容输入的账单均为固定字面值 `BILL-001`；缺失/非法输入预期为跳过，来自 `REQ-003` 和现有解析合同。
- mock/fake/stub 边界：候选集合由 stub 提供；不 mock 账单解析器，不通过私有方法验证。
- 预期 RED 原因：当前没有目标选择用例，也没有针对现有解析器三种兼容形态的独立 UT。
- 最小 GREEN 条件：复用现有解析器并对空结果失败关闭；不得为本需求另写 JSONPath、Map 或 SQL JSON 解析。
- 风险选择性代码：查询整体异常直接结束本次流程；候选解析为空只跳过当前候选，二者日志均不得包含 payload。

#### 行为切片：候选 SQL 条件与稳定排序

- Given-When-Then：Given 完整查询 criteria，When 调用 `WorkOrderServiceImpl#listTableNotDoneCandidates`，Then 交给 mapper 的 wrapper 同时包含 `state=0`、单一门店/桌台/模板、三个状态、左闭右开时间条件，并依次包含 `create_time DESC`、`work_order_id DESC`；任一关键等值条件或时间为空时返回空且不访问 mapper。
- UT 边界：直接构造 repository，mock `WorkOrderRecordMapper` 和其他构造依赖，用 `ArgumentCaptor<LambdaQueryWrapper<WorkOrderRecordPO>>` 检查 SQL segment 与独立参数值；不启动 Spring、不连接数据库。
- 独立预期值：过滤值和两端时间使用测试常量；排序列及方向直接取 `REQ-003`，不复用生产 wrapper 生成预期 SQL。
- mock/fake/stub 边界：MyBatis mapper 是数据库边界；真实执行 wrapper 构造。另用 gateway UT 捕获 infra criteria，证明 domain query 到 PO 查询的字段转换和返回顺序不被重排。
- 预期 RED 原因：当前窄方法和时间 criteria 不存在，现有方法生成正序且允许桌台为空。
- 最小 GREEN 条件：新增独立 criteria/method/wrapper 和 gateway 转换；不修改旧 `buildListByParamWrapper`。
- 风险选择性代码：查询核心固定为 `eq(state/store/point/template) + in(statuses) + ge(dayStart) + lt(nextDayStart) + orderByDesc(createTime) + orderByDesc(workOrderId)`；UT 只能证明构造合同，不能代替生产 MySQL 执行计划。

#### 行为切片：待认领原消息加急适配

- Given-When-Then：Given 唯一目标工单状态为 `WAIT_CLAIM` 且工单号 `WO-200`，When 应用用例调用手表端口，Then adapter 仅调用 `upgradeMessageToUrgent(["WO-200"], configuredSource)`，不调用主动推送；远端空响应、失败或异常时应用用例正常返回且不改选工单。
- UT 边界：应用 UT mock 领域手表端口验证选择结果；adapter UT 直接构造适配器并注入 mock `MessageCallbackRemote`，捕获远端完整参数，不启动 Spring。
- 独立预期值：单元素集合、来源编码和工单号均为固定 fixture；“不新发消息”取自 `AC-005`。
- mock/fake/stub 边界：Dubbo client 是外部边界；adapter 归一化、响应判断和异常转换使用真实代码。
- 预期 RED 原因：现有端口和 adapter 只有完成回调方法，没有加急能力。
- 最小 GREEN 条件：新增显式端口方法和单一远端适配；应用用例在 `WAIT_CLAIM` 动作中只调用该方法并隔离异常。
- 风险选择性代码：不复用 `callbackMessage`、`PushEventRemote` 或普通工单消息模板实现加急；不因远端失败重试或发送提醒兜底。

### TASK-003 恢复当前有效手表接收人并发送专用二次提醒

- 追溯落点：`REQ-005`、`REQ-006`、`REQ-007`、`REQ-010`、`REQ-011`、`REQ-012`；`AC-006`、`AC-007`、`AC-008`、`AC-010`、`AC-012`、`AC-013`；`DEC-003`、`DEC-004`。
- 目标行为或风险闭环：目标工单为执行中或已完成时，仅在执行配置判定为手表渠道后，恢复相应当前角色的最大有效派发轮次人员并发送一条按事件 ID 去重的固定提醒；任何查询、解析或远端失败均静默结束且不触发另一个动作。
- 已核实代码事实：参与关系 gateway 已在 infra 过滤当前/有效记录，但返回集合仍可能包含空轮次、多轮次、空员工或重复员工；`WatchMessageRemoteGatewayAdapter` 目前未注入 `PushEventRemote`；普通 `WatchDeviceDeliveryGatewayAdapter` 绑定规则执行命令和重试结果，不能复用。
- 继承约束：执行中只查 `CURRENT_HANDLER`，已完成只查 `HISTORY_HANDLER`；显式 `FEISHU/APP/KPAD` 均跳过，空或历史未知渠道按 `WATCH` 兼容；不以工单主表执行人或历史派发记录兜底；远端命令和接收人列表在调用前冻结。
- 拟议变更：
  - 新增不可变 `work-order-domain/src/main/java/com/haidilao/workorder/domain/shared/model/watch/WatchReminderReceiverEntity.java` 和 `TableNotDoneWatchReminderCommand.java`；receiver 规范化 `employeeCode/name`，command 防御性复制并按员工编码保持顺序去重。
  - 扩展 `WatchMessageRemoteGateway#sendTableNotDoneReminder(TableNotDoneWatchReminderCommand)`；不引入 `AssigneeUserEntity` 或 `ExecuteWorkOrderCommand`。
  - 完成 `TableNotDoneAdditionalTouchAppServiceImpl` 的提醒分支：从目标实体读取 `touchPoint` 交给 policy 判断渠道；按状态选择唯一角色，通过 `WorkOrderParticipantGateway#listCurrentByWorkOrderIdsAndRoles` 查询；过滤空轮次，取最大轮次，只保留该轮次有效员工，姓名空时回退员工编码并去重；构造一次提醒命令。读取完目标状态和接收人后不再查询或切换分支。
  - 在 `WatchMessageRemoteGatewayAdapter` 注入 `PushEventRemote`，直接构造固定 `RemoteMessageDto`：`eventType=WOKR_ORDER`、两类固定标题/正文、`psCode/storeCode`、`tableNo/tableCode`、`businessId=eventId`、`businessIdDedup=true`、全量去重接收人；未知事件类型、空关键字段、空接收人及远端非成功统一抛内部异常，由应用层隔离。
  - 扩充 `TableNotDoneAdditionalTouchAppServiceImplTest` 和 `WatchMessageRemoteGatewayAdapterTest`；使用现有 `WorkOrderParticipantGatewayImpl`/`WorkOrderParticipantDomainServiceImpl` 相关 UT 作为只读关系口径回归，不修改 participant 写链路。
- 真实任务依赖：`TASK-002`，复用唯一目标工单快照、应用用例和既有手表端口适配器。
- 验证入口：`TableNotDoneAdditionalTouchAppServiceImplTest`、`WatchMessageRemoteGatewayAdapterTest`、`WorkOrderParticipantDomainServiceImplTest`、`WorkOrderParticipantServiceImplTest`。
- 完成证据：Execution 记录两种状态对应角色、最大轮次与去重后的完整领域命令、两类完整远端 DTO、非手表/空接收人跳过、查询/远端异常隔离、状态竞态不换分支和工单/参与关系写端口零调用。

#### 行为切片：执行中当前轮次接收人过滤

- Given-When-Then：Given 手表渠道的 `EXECUTING` 工单具有当前有效 `CURRENT_HANDLER` 关系，其中包含轮次 1、轮次 2、空轮次、空员工和轮次 2 的重复员工，When 执行附加触达，Then 只向轮次 2 的非空员工全集发送一次提醒，重复员工只保留一次，空姓名回退员工编码。
- UT 边界：真实 policy、应用服务、receiver/command；mock 工单、参与关系和手表领域端口，捕获角色查询和完整提醒命令，不启动 Spring。
- 独立预期值：角色固定为 `CURRENT_HANDLER`，最大轮次固定为 `2`，预期员工顺序与编码使用字面 fixture，不调用生产去重方法生成。
- mock/fake/stub 边界：参与关系持久化和远端发送是边界；轮次选择、身份过滤、姓名回退和命令冻结使用真实代码。
- 预期 RED 原因：当前应用用例没有参与关系读取、轮次过滤或提醒命令类型。
- 最小 GREEN 条件：按目标状态查询一个角色，过滤空轮次后取最大值，再按员工编码有序去重并发送一个命令。
- 风险选择性代码：不得把 `listByWorkOrderIdsAndRoles` 的全历史查询或主表 `executeUserId` 当作兜底；gateway 已过滤当前有效关系，应用层只负责轮次与身份语义。

#### 行为切片：已完成历史处理人提醒

- Given-When-Then：Given 手表渠道的 `COMPLETED` 工单和当前有效 `HISTORY_HANDLER` 关系，When 执行附加触达，Then 查询角色仅为 `HISTORY_HANDLER`，向最大非空派发轮次的所有去重员工发送提醒，且不重开、不更新工单或参与关系。
- UT 边界：直接调用应用服务 public API；mock 领域读端口和手表端口，用负向写端口断言补充证明 `save/claim/complete/transfer/deactivate` 未被调用。
- 独立预期值：角色、员工集合和命令中的原 `workOrderId/eventId/storeCode/tableCode` 均使用测试 fixture；工单状态仍为测试构造的 `COMPLETED`。
- mock/fake/stub 边界：持久化和远端为边界；状态到角色、接收人过滤与命令构造使用真实逻辑。零写调用是 `AC-008` 的补充断言，不替代对提醒命令的主要业务断言。
- 预期 RED 原因：当前无 `COMPLETED` 专用接收人口径和提醒动作。
- 最小 GREEN 条件：复用同一接收人过滤流程，仅由 policy 将 `COMPLETED` 映射到 `HISTORY_HANDLER`；不增加工单生命周期方法。
- 风险选择性代码：工单状态一旦读入并选定提醒分支，即使 mock 远端回调中改变原实体状态也只允许已选分支一次，不重新查工单或改为加急。

#### 行为切片：非手表、空接收人与解析失败关闭

- Given-When-Then：Given `touchPoint` 显式为 `FEISHU`、`APP` 或 `KPAD`，或参与关系没有非空轮次/员工，When 执行附加触达，Then 不发送任何提醒；Given `touchPoint` 为空、非法 JSON 或历史未知值，When 存在有效接收人，Then 按既有兼容规则视为 `WATCH`；参与关系查询或解析抛异常时正常返回且不尝试加急。
- UT 边界：真实实体快照读取和 policy，mock 参与关系与手表端口；参数化覆盖显式非手表、空、未知和异常场景。
- 独立预期值：显式跳过集合固定为 `FEISHU/APP/KPAD`，空和 `LEGACY_CHANNEL` 预期为手表兼容，来自 `DEC-003`，不读取生产允许值集合生成预期。
- mock/fake/stub 边界：关系查询异常由 mock 模拟；JSON 读取、渠道决策和失败隔离使用真实代码。
- 预期 RED 原因：当前没有本场景渠道判断、接收人空结果处理和分阶段异常隔离。
- 最小 GREEN 条件：在查参与关系前完成渠道短路；关系或解析失败只记录三字段以内摘要并结束，不调用另一动作。
- 风险选择性代码：不能读取 `t_work_order_dispatch_record.channel_type`，也不能把显式非手表值按未知值降级为手表。

#### 行为切片：两类固定二次提醒远端合同

- Given-When-Then：Given 分别收到 `CLEAR_TABLE_NOT_DONE` 和 `WIPE_TABLE_NOT_DONE` 提醒命令，When adapter 调用 `PushEventRemote`，Then远端 DTO 的标题分别为“未及时收台复核提醒”“未及时擦台复核提醒”，正文分别包含对应桌台及“请线下复核处理”，共同字段为 `eventType=WOKR_ORDER`、`businessId=eventId`、`businessIdDedup=true`、目标门店/桌台和全部接收人；远端空响应、失败或异常统一抛内部异常。
- UT 边界：直接构造 adapter，反射注入 mock Dubbo `PushEventRemote`/`MessageCallbackRemote`，用 `ArgumentCaptor<RemoteMessageDto>` 断言完整边界请求，不启动 Spring。
- 独立预期值：所有固定字段直接来自 Design 云手表合同表；接收人 DTO 使用独立字面员工编码和姓名。
- mock/fake/stub 边界：云手表 client 是唯一 mock；领域命令规范化、远端 DTO 转换和返回判断使用真实代码。
- 预期 RED 原因：现有 adapter 未注入主动推送 client，也没有专用命令和固定消息构造。
- 最小 GREEN 条件：新增显式端口方法、client 注入、两类固定字段映射、接收人转换和统一异常；不复用动态模板 router。
- 风险选择性代码：`workOrderId` 只用于本地日志上下文，不写入 `businessId`；未知事件编码必须失败关闭，不能回退为普通工单标题。

#### 行为切片：附加全链路失败隔离与竞态单分支

- Given-When-Then：Given 目标查询、候选解析、渠道解析、参与关系查询、加急或提醒远端调用任一阶段异常，When `touchSafely` 返回并由事件入口完成响应，Then 事件结果仍为首次持久化的 `ACCEPTED_NO_WORK_ORDER`，没有工单/参与关系写入；Given 目标状态在首次读取后并发改变，Then 最多执行已选择的一个动作且不重查、不切换、不重试。
- UT 边界：以应用服务 public API 为主要边界，按阶段参数化 mock 一个异常；事件入口 UT 再覆盖最后一层未知异常。通过预置会变状态的实体或 mock 回调验证动作快照冻结。
- 独立预期值：稳定响应字段取 `REQ-009`，动作数量上限为一个且类型取首次读取状态，禁止写端口列表取 `AC-008`。
- mock/fake/stub 边界：各领域/远端端口按系统边界模拟故障；应用编排、异常捕获和动作冻结使用真实逻辑。
- 预期 RED 原因：当前无附加应用实现及分阶段异常隔离，事件入口也没有该调用边界兜底。
- 最小 GREEN 条件：`touchSafely` 统一不向上抛出，并在每个失败阶段立即停止；入口保留第二层 catch；方法内不使用循环重试或二次状态查询。
- 风险选择性代码：异常日志只含 `eventId/workOrderId/phase` 或 `eventId/phase/result` 三个字段；不把异常消息、payload、接收人或远端响应写入上游 `reasonDesc`。

## 测试与验证

### UT 方案

- 行为切片与测试入口：
  - `TASK-001` 三个切片 -> `TableNotDoneAdditionalTouchPolicyTest`、`EventIngestBizImplTest`、`EventIngestCmdHandlerTest`、`EventRuleDispatchBizImplTest`、`EventProcessResultRecorderBizImplTest`。
  - `TASK-002` 四个切片 -> `TableBillIdResolveSupportTest`、`TableNotDoneAdditionalTouchAppServiceImplTest`、`TableNotDoneWorkOrderQueryServiceTest`、`WorkOrderRecordGatewayImplTableNotDoneTest`、`WatchMessageRemoteGatewayAdapterTest`。
  - `TASK-003` 五个切片 -> `TableNotDoneAdditionalTouchAppServiceImplTest`、`WatchMessageRemoteGatewayAdapterTest`；参与关系既有行为由 `WorkOrderParticipantDomainServiceImplTest`、`WorkOrderParticipantServiceImplTest` 回归。
- 集中命令：`mvn -pl work-order-domain,work-order-infra,work-order-application,work-order-adapter -am -Dtest=TableNotDoneAdditionalTouchPolicyTest,EventIngestBizImplTest,EventIngestCmdHandlerTest,EventRuleDispatchBizImplTest,EventProcessResultRecorderBizImplTest,TableBillIdResolveSupportTest,TableNotDoneAdditionalTouchAppServiceImplTest,TableNotDoneWorkOrderQueryServiceTest,WorkOrderRecordGatewayImplTableNotDoneTest,WatchMessageRemoteGatewayAdapterTest -Dsurefire.failIfNoSpecifiedTests=false test`
- 直接相关回归 UT：`mvn -pl work-order-domain,work-order-infra,work-order-application,work-order-adapter,work-order-web -am -Dtest=WorkOrderExecuteDomainServiceImplTest,WorkOrderParticipantDomainServiceImplTest,WorkOrderParticipantServiceImplTest,EventIngestBizImplTest,EventProcessResultRecorderBizImplTest,WorkOrderLinkageConsumeBizImplTest,WatchMessageRemoteGatewayAdapterTest,EventRequestConvertorTest -Dsurefire.failIfNoSpecifiedTests=false test`
- 测试数据规则：时间、账单、模板、状态、轮次、员工和远端 DTO 预期均使用独立字面 fixture；不调用生产映射/解析/排序方法生成 expected；主断言是响应、选中的工单、完整领域命令或完整远端请求，交互次数只用于证明禁止建单/写入/第二动作。

### Execution 基线

- 受影响模块编译：`mvn -pl work-order-common,work-order-domain,work-order-infra,work-order-application,work-order-adapter,work-order-web -am -DskipTests compile`
- 相关现有 UT：`mvn -pl work-order-domain,work-order-infra,work-order-application,work-order-adapter,work-order-web -am -Dtest=WorkOrderExecuteDomainServiceImplTest,WorkOrderParticipantDomainServiceImplTest,WorkOrderParticipantServiceImplTest,EventIngestBizImplTest,EventProcessResultRecorderBizImplTest,WorkOrderLinkageConsumeBizImplTest,WatchMessageRemoteGatewayAdapterTest,EventRequestConvertorTest -Dsurefire.failIfNoSpecifiedTests=false test`
- 必要快速静态检查：`git diff --check`
- 将修改的测试入口：`mvn -pl work-order-application,work-order-adapter -am -Dtest=EventIngestBizImplTest,EventProcessResultRecorderBizImplTest,WatchMessageRemoteGatewayAdapterTest -Dsurefire.failIfNoSpecifiedTests=false test`；其余拟新增测试类在基线时不存在，不虚构基线执行结果。
- 基线限制：不执行全仓测试、数据库连接、生产 `EXPLAIN`、Dubbo 联调或真实设备验证；任一上述可控命令失败时 Execution 停止，不修改生产代码或把基线问题并入本需求。

### 最终验证

- 受影响模块编译：`mvn -pl work-order-common,work-order-domain,work-order-infra,work-order-application,work-order-adapter,work-order-web -am -DskipTests compile`
- 本次全部新/改 UT：`mvn -pl work-order-domain,work-order-infra,work-order-application,work-order-adapter -am -Dtest=TableNotDoneAdditionalTouchPolicyTest,EventIngestBizImplTest,EventIngestCmdHandlerTest,EventRuleDispatchBizImplTest,EventProcessResultRecorderBizImplTest,TableBillIdResolveSupportTest,TableNotDoneAdditionalTouchAppServiceImplTest,TableNotDoneWorkOrderQueryServiceTest,WorkOrderRecordGatewayImplTableNotDoneTest,WatchMessageRemoteGatewayAdapterTest -Dsurefire.failIfNoSpecifiedTests=false test`
- 直接相关回归 UT：`mvn -pl work-order-domain,work-order-infra,work-order-application,work-order-adapter,work-order-web -am -Dtest=WorkOrderExecuteDomainServiceImplTest,WorkOrderParticipantDomainServiceImplTest,WorkOrderParticipantServiceImplTest,WorkOrderLinkageConsumeBizImplTest,EventRequestConvertorTest -Dsurefire.failIfNoSpecifiedTests=false test`
- 快速静态检查：`git diff --check`；`rg -n "idx_work_order_not_done_lookup|ACCEPTED_NO_WORK_ORDER|listTableNotDoneCandidates|sendTableNotDoneReminder|upgradeWorkOrderMessageToUrgent" sql work-order-common/src/main/java work-order-domain/src/main/java work-order-infra/src/main/java work-order-application/src/main/java work-order-adapter/src/main/java`；`python3 ~/.agents/skills/pretty-java-spring-core/scripts/validate-pretty-docs.py docs/pretty/table-not-done-additional-watch-touch --through plan`。
- SQL 确定性验证只证明迁移与基线 DDL 同步、字段顺序和代码 wrapper 合同；不把本地 wrapper UT 称为数据库集成测试。

### 覆盖率

- 仓库政策：无明确政策，使用 Pretty 默认值。
- 适用范围：可由 UT 覆盖的新增或实质修改 Java 行为，包括事件 policy、事件分流/规则保护、附加应用编排、窄查询构造、通用终态分类和手表 adapter；纯常量、Lombok 数据载体、SQL 与机械 import 不以无价值测试追逐覆盖率。
- 行阈值：90%。
- 分支阈值：80%。
- JaCoCo：`~/.agents/skills/pretty-java-spring-core/scripts/run-coverage.sh --project-dir .`
- 增量检查：在上一步生成各模块 `jacoco.xml` 后执行 `python3 ~/.agents/skills/pretty-java-spring-core/scripts/check-new-code-coverage.py --repo . --base HEAD --report work-order-domain/target/site/jacoco/jacoco.xml --report work-order-infra/target/site/jacoco/jacoco.xml --report work-order-application/target/site/jacoco/jacoco.xml --report work-order-adapter/target/site/jacoco/jacoco.xml --file work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/tablenotdone/TableNotDoneAdditionalTouchPolicy.java --file work-order-application/src/main/java/com/haidilao/workorder/application/event/command/ingest/EventIngestBizImpl.java --file work-order-application/src/main/java/com/haidilao/workorder/application/event/command/dispatch/EventRuleDispatchBizImpl.java --file work-order-application/src/main/java/com/haidilao/workorder/application/event/command/ingest/EventRuleDispatchAsyncExecutor.java --file work-order-application/src/main/java/com/haidilao/workorder/application/event/command/process/EventProcessResultRecorderBizImpl.java --file work-order-application/src/main/java/com/haidilao/workorder/application/event/command/ingest/tablenotdone/TableNotDoneAdditionalTouchAppServiceImpl.java --file work-order-infra/src/main/java/com/haidilao/workorder/infra/core/repository/workorder/WorkOrderServiceImpl.java --file work-order-infra/src/main/java/com/haidilao/workorder/infra/gatewayimpl/workorder/WorkOrderRecordGatewayImpl.java --file work-order-adapter/src/main/java/com/haidilao/workorder/adapter/remote/outbound/watch/WatchMessageRemoteGatewayAdapter.java --line-threshold 90 --branch-threshold 80`。
- 覆盖率限制：工具只统计相对 `HEAD` 新增生产行；对既有行为修改同时以具名针对性 UT 证明，不在工具无法统计修改行时虚构修改行百分比。

### 声明限制

- Pretty 外未验证范围：生产 MySQL 数据分布、索引选择和查询耗时需在目标库执行 `EXPLAIN` 并观察慢查询；两类事件定义的允许来源、启用状态、`SHOP_TABLE` 点位和含账单字段的 payload schema 需通过运行时配置确认；历史参与关系和执行快照完整率需数据抽样；真实云手表字段兼容、超时后实际接收状态、去重效果和设备展示需联调/观测；部署、灰度、指标告警和事件定义开关操作不在 Execution 内。
- 完成时仅可声明：代码与 UT 证明首次/重复分流、固定映射、日期窗口和候选排序构造、账单匹配、状态单分支、接收人过滤、远端请求构造、失败隔离、规则/工单写副作用关闭以及其他事件相关回归；不得声明生产索引一定命中、历史数据全部可解析、真实员工已收到提醒或外部配置已经生效。
