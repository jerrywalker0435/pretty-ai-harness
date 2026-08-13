# 未及时收台与擦台事件附加手表触达 Design

## 输入与范围

- PRD：`docs/pretty/table-not-done-additional-watch-touch/prd.md`
- 领域语言：`CONTEXT.md`
- 覆盖需求：`REQ-001`、`REQ-002`、`REQ-003`、`REQ-004`、`REQ-005`、`REQ-006`、`REQ-007`、`REQ-008`、`REQ-009`、`REQ-010`、`REQ-011`、`REQ-012`
- 本设计负责：两类事件的受理分流、事件级防重、目标工单选择、当前有效手表派发对象解析、两类手表动作、外部响应兼容、失败隔离及查询索引。
- 本设计不负责：创建、补建、重开、取消或修改工单；模板匹配、规则执行、延迟计划、附加触达补偿；新增上游字段或返回附加触达详情。

## 设计摘要

两类未及时事件沿用现有事件入口校验和唯一键入库；首次成功落为 `ACCEPTED_NO_WORK_ORDER` 后，在返回前同步调用独立应用用例，重复事件、领域事件发布和规则重投入口均不再触发该用例。目标工单查询先用索引条件限定事件发生日、门店、桌台、模板和状态，再复用既有账单解析口径选出按创建时间、工单号倒序的第一张同账单工单。待认领工单调用原消息加急能力；执行中或已完成工单从当前参与关系恢复当前轮次员工，并仅在原执行渠道为手表时发送固定文案的独立提醒。附加流程位于事件持久化事务之外，所有查询、解析和远端失败只留内部摘要，不修改事件成功结果或工单。

```text
事件上报
  |
  v
既有校验 -> 首次事件入库 -> 是否为未及时事件？ -- 否 --> 既有模板/规则链路
                                |
                                是
                                v
                   回写 ACCEPTED_NO_WORK_ORDER
                                |
                                v
                     同步执行附加触达用例
                                |
              +-----------------+------------------+
              |                                    |
       目标工单不存在/解析失败                 选出唯一目标工单
              |                                    |
              v                         +----------+----------+
             跳过                       |                     |
                                  WAIT_CLAIM        EXECUTING / COMPLETED
                                       |                     |
                                       v                     v
                                  原消息加急        解析当前有效手表接收人
                                                             |
                                                             v
                                                    发送专用二次提醒
              +----------------------------------------------+
              |
              v
   完成、跳过或失败均返回同一事件受理结果；不进入规则、不修改工单
```

## 现状与约束

- PRD 要求：`REQ-001`、`REQ-007`、`REQ-009` 要求首次落库后同步尝试、返回 `ACCEPTED_NO_WORK_ORDER` 且不进入规则；`REQ-003`、`REQ-006` 分别固定目标工单和接收人口径；`REQ-008`、`REQ-010` 固定 at-most-once 与失败不补偿语义。
- 已核实仓库事实：`work-order-application/src/main/java/com/haidilao/workorder/application/event/command/ingest/EventIngestBizImpl.java#ingest` — 先持久化事件，数据库唯一键冲突后回查重复事件；当前仅 `ACCEPTED_READY_FOR_RULE` 继续模板触发编排，入口方法没有事务注解。
- 已核实仓库事实：`sql/work_order_mysql.sql#t_event_record` — 唯一键 `uk_event_type_source_event(event_type_code, source_event_id)` 已覆盖 PRD 的事件身份，不需要第二套入口幂等键。
- 已核实仓库事实：`work-order-application/src/main/java/com/haidilao/workorder/application/event/executor/command/ingest/EventIngestCmdHandler.java#execute` — 仅 `ACCEPTED_READY_FOR_RULE`、`ACCEPTED_DELAYED_TRIGGER_PENDING` 发布 `EventIngestedEvent`；新结果码默认不会进入既有异步规则消费。
- 已核实仓库事实：`work-order-application/src/main/java/com/haidilao/workorder/application/event/command/dispatch/EventRuleDispatchBizImpl.java#dispatchToRule` — 当前显式重投按事件号直接调用规则处理，尚无未及时事件的失败关闭保护。
- 已核实仓库事实：`work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/gateway/WorkOrderRecordGateway.java#listByQuery` 与 `work-order-infra/src/main/java/com/haidilao/workorder/infra/core/repository/workorder/WorkOrderServiceImpl.java#buildListByParamWrapper` — 现有组合查询没有创建时间窗口，且按创建时间、主键正序，不能直接满足唯一最新选择。
- 已核实仓库事实：`work-order-application/src/main/java/com/haidilao/workorder/application/workorder/support/TableBillIdResolveSupport.java#resolve` — 已统一支持根节点 `tableBillId`、兼容 `orderId` 和 `detail` 嵌套 JSON，解析失败返回空值。
- 已核实仓库事实：`work-order-application/src/main/java/com/haidilao/workorder/application/workorder/support/WorkOrderParticipantSyncSupport.java#syncClaimedParticipant`、`#syncCompletedParticipant` — 领取、转办、完成会关闭旧关系并写入当前处理人或历史处理人，且保留 `dispatchRound`；它比工单主表执行人字段更适合表达当前有效接收人。
- 已核实仓库事实：`work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/dispatch/service/impl/WorkOrderDispatchDomainServiceImpl.java#persistDispatchRecord` — 常规派发审计以 `DispatchChannel.SYSTEM` 落库，现有 `t_work_order_dispatch_record.channel_type` 不能直接证明原消息是否通过手表发送。
- 已核实仓库事实：`work-order-domain/src/main/java/com/haidilao/workorder/domain/workorder/execute/WorkOrderExecuteDomainServiceImpl.java#resolveChannelType` — 执行渠道来自工单执行配置快照；空值或不支持值按 `WATCH` 降级，显式非手表值走对应其他渠道。
- 已核实仓库事实：`work-order-domain/src/main/java/com/haidilao/workorder/domain/shared/gateway/remote/WatchMessageRemoteGateway.java` 与 `work-order-adapter/src/main/java/com/haidilao/workorder/adapter/remote/outbound/watch/WatchMessageRemoteGatewayAdapter.java` — 已存在云手表消息能力端口、来源编码配置和统一异常风格，但当前只有消息完成回调。
- 已核实仓库事实：`work-order-adapter/src/main/java/com/haidilao/workorder/adapter/remote/outbound/executer/WatchDeviceDeliveryGatewayAdapter.java#deliver` — 常规推送依赖规则执行命令、消息策略和执行结果，不能直接承载不进入规则引擎的附加触达。
- 外部合同：当前云手表依赖提供 `MessageCallbackRemote.upgradeMessageToUrgent(List<String>, String)` 和 `PushEventRemote.pushEvent(RemoteMessageDto)`；后者支持事件类型、门店、标题、正文、桌号、业务 ID、接收人和业务 ID 去重。真实设备展示、超时后实际送达状态不属于本地可证明范围。
- 工程约束：所有新增 Java 代码使用 JDK 8；应用、领域核心编排按业务步骤添加中文注释；日志只输出不超过三个关键字段，不记录完整 payload、复杂实体或接收人明细。

## 方案与权衡

采用“事件入口分流 + 独立附加触达应用用例 + 既有领域端口扩展”的方案。事件入口只识别类型、固化不建单结果并调用用例；目标查询、账单匹配、状态决策、接收人恢复和失败隔离不堆入 `EventIngestBizImpl`。依赖方向保持 `web -> application -> domain`，持久化查询由 `infra` 实现，云手表调用由 `adapter` 实现。

未采用以下方案：

- 不复用 `WorkOrderExecuteDomainService` / `DeviceDeliveryGateway`：该链路会读取模板触达渠道与重试次数、构造常规工单消息，并用执行结果推进事件终态，违反“不进规则、不建单、不重试”的合同。
- 不让 SQL 直接解析账单 JSON：历史数据同时存在根节点、`orderId` 兼容和字符串化 `detail`，在 SQL 中复制这套逻辑会形成第二种账单口径；本设计只在数据库做有界粗筛，在应用层复用同一解析器。
- 不新增独立防重表或复用窗口型 `t_idempotency_guard`：入口唯一键已经精确覆盖事件身份；窗口守卫的令牌持有、提交、释放语义允许过期或失败释放，与“失败后永久不补触达”相冲突。
- 不把 `t_work_order_dispatch_record.channel_type` 当作手表渠道真相：当前值表达派发计算渠道 `SYSTEM`，机械过滤 `WATCH` 会使常规历史工单全部漏发；改用实际执行时使用的工单执行配置快照判断渠道。

## 详细设计

### 决策索引

| 决策 | 问题 | 采用方案 |
| --- | --- | --- |
| `DEC-001` | 首次触达与失败后不补偿如何防重 | 以事件唯一键和“本次新入库”分支作为唯一启动闸门 |
| `DEC-002` | 如何正确且稳定选择唯一目标工单 | 索引粗筛后按既有解析器匹配账单，固定双字段倒序 |
| `DEC-003` | 如何恢复当前有效手表派发对象 | 执行配置快照判渠道，当前参与关系判人员和轮次 |
| `DEC-004` | 两类手表动作通过什么端口 | 扩展现有手表消息能力端口，使用两个显式方法 |

### DEC-001 以事件唯一键作为附加触达启动闸门

- 驱动因素与相关 `REQ`：`REQ-001`、`REQ-007`、`REQ-008`、`REQ-010`；同一事件只能由首次成功受理启动一次，失败和重复上报均不能补触达。
- 候选或决定性证据：现有 `t_event_record` 唯一键可在线程间、实例间裁决首次插入；新增永久守卫会重复保存同一事实，现有窗口守卫又可能释放或过期；只使用远端去重无法保护本地查询和加急动作。
- 采用方案及理由：`EventIngestBizImpl` 在基础校验通过后，按未及时事件类型直接回写 `ACCEPTED_NO_WORK_ORDER`；只有当前请求成功完成首次插入和该结果回写时才同步调用附加触达。唯一键冲突回查分支直接返回 `IGNORED_DUPLICATE`，不调用附加用例。二次提醒额外使用 `businessId=eventId`、`businessIdDedup=true` 抵抗远端超时歧义，但不把它作为入口幂等依据。
- 后果：无需新增表，串行和并发重复都不会重新启动；进程在成功落库后、远端调用前退出时会永久漏触达，这是 PRD 明确的 at-most-once、无补偿取舍。
- 重新评估条件：若未来要求附加触达最终送达、人工补偿或失败重试，应引入独立 outbox/触达任务状态，而不是放宽本次事件唯一键语义。

### DEC-002 目标工单采用有界数据库粗筛与统一账单解析

- 驱动因素与相关 `REQ`：`REQ-002`、`REQ-003`、`REQ-011`；需正确处理历史 payload 形态，并在时间相同场景稳定选出一张工单。
- 候选或决定性证据：现有查询缺少日期范围和目标排序；既有解析器已覆盖三种账单存储形态；现有索引没有同时覆盖门店、桌台、模板和创建时间。
- 采用方案及理由：新增窄查询对象 `TableNotDoneWorkOrderQuery` 和 `WorkOrderRecordGateway#listTableNotDoneCandidates`。查询必须同时包含 `state=0`、门店、桌台、单一模板、`WAIT_CLAIM/EXECUTING/COMPLETED`、`[dayStart, nextDayStart)`，并按 `create_time DESC, work_order_id DESC` 返回。应用用例先解析事件账单，再按返回顺序解析候选工单账单，首个 trim 后精确相等的候选即为唯一目标；任何一侧不可解析都跳过。
- 后果：账单语义只有一个实现，查询范围被自然日和业务维度限制；需要读取粗筛候选的 payload，且极端热点桌台仍可能返回较多候选。
- 重新评估条件：若生产执行计划或候选数量表明单桌台单模板单日扫描不可接受，再在不改变解析口径的前提下增加结构化账单快照列和索引。

### DEC-003 以执行渠道快照和当前参与关系组合恢复接收人

- 驱动因素与相关 `REQ`：`REQ-005`、`REQ-006`、`REQ-011`；必须排除历史轮次、失效人员和非手表渠道，同时兼容当前派发审计表以 `SYSTEM` 记录的事实。
- 候选或决定性证据：派发审计 `channel_type` 不是实际设备渠道；工单 `executeConfigSnapshot.touchPoint` 是执行时渠道事实；参与关系在领取、转办、完成时维护 `is_current`、`relation_status`、角色和轮次。
- 采用方案及理由：先按与正常执行链路一致的规则解析 `touchPoint`：显式 `FEISHU/APP/KPAD` 等非手表渠道直接跳过，空值或历史未知值按既有默认 `WATCH` 兼容。执行中查询当前有效 `CURRENT_HANDLER`，已完成查询当前有效 `HISTORY_HANDLER`；只保留 `state=1`、`is_current=1`、`relation_status=ACTIVE`、`dispatchRound` 非空的关系，取其中最大轮次后仅保留同轮次人员，按 trim 后 `employeeId` 去重。员工编码为空则剔除，姓名为空可回退员工编码；结果为空时跳过提醒。
- 后果：不需修改工单或历史派发记录，领取、转办和完成后的人员口径与员工端一致；参与关系缺失或历史轮次为空时选择失败关闭，即不发送可能误达的提醒。
- 重新评估条件：当派发审计表开始可靠保存实际设备渠道与逐员工送达真相，或业务要求提醒原始候选池而不是当前处理链时，改为专门的派发接收人投影。

### DEC-004 扩展现有手表消息能力端口

- 驱动因素与相关 `REQ`：`REQ-004`、`REQ-005`、`REQ-007`、`REQ-010`；两种动作外部 API 不同，但都属于同一云手表消息边界，且结果不能影响事件响应。
- 候选或决定性证据：复用规则执行网关会继承模板与重试语义；新建场景专用网关会复制同一供应商、配置和异常处理；单一 `action + 可选字段` 命令容易产生非法组合。
- 采用方案及理由：在 `WatchMessageRemoteGateway` 增加两个 `void` 方法，保持现有同步调用、失败抛异常的风格；应用用例统一捕获异常。二次提醒使用专用不可变命令，不复用 `workorder.rule.execution.AssigneeUserEntity`，避免反向耦合规则执行模型。
- 后果：调用点语义明确，远端 DTO、来源编码和成功判断仍封装在 adapter；现有端口实现需同时适配回调和主动推送两个云手表 client。
- 重新评估条件：若附加提醒使用独立供应商、凭证、SLA、重试政策或独立团队所有权，再拆出专用端口。

### 模块职责与依赖方向

| 模块 | 职责 | 禁止事项 |
| --- | --- | --- |
| `work-order-web` / 既有入站适配 | 保持现有事件上报 Qo/Vo 和入口行为 | 不返回目标工单、动作、接收人或触达结果 |
| `work-order-application` | 受理分流；组装 `TableNotDoneAdditionalTouchDTO`；编排日期窗口、查询、账单解析、接收人解析、动作调用和失败隔离 | 不直连 mapper、repository 或云手表 client；不修改工单 |
| `work-order-domain` | 未及时事件到模板的固定映射、状态到动作的决策；定义窄查询对象、接收人对象和远端端口合同 | 不依赖 `infra` / `adapter`；不承载 JSON 远端 DTO |
| `work-order-infra` | 实现目标工单候选查询和索引友好的排序；复用参与关系网关查询 | 不解析或发送云手表消息 |
| `work-order-adapter` | 适配加急 API 与主动推送 API；构造固定消息、转换接收人、校验远端结果 | 不选择工单、不解析当前轮次、不改变事件结果 |
| `work-order-api` / `work-order-common` | 复用现有响应字段；补充事件编码、结果码和固定文本常量 | 不增加附加触达响应字段 |

核心短合同固定如下：

```java
public interface TableNotDoneAdditionalTouchAppService {
    void touchSafely(TableNotDoneAdditionalTouchDTO commandDTO);
}

public interface WorkOrderRecordGateway {
    List<WorkOrderRecordEntity> listTableNotDoneCandidates(TableNotDoneWorkOrderQuery query);
}

public interface WatchMessageRemoteGateway {
    void completeWorkOrderMessages(List<String> workOrderIds, String operatorCode, String operatorName);
    void upgradeWorkOrderMessageToUrgent(String workOrderId);
    void sendTableNotDoneReminder(TableNotDoneWatchReminderCommand command);
}
```

`TableNotDoneAdditionalTouchDTO` 只含 `eventId/eventDefineCode/storeCode/pointCode/occurredAt/payloadData`。`TableNotDoneWatchReminderCommand` 只含 `eventId/eventDefineCode/workOrderId/storeCode/tableCode/receivers`；receiver 为独立 `WatchReminderReceiverEntity(employeeCode, employeeName)`，构造时去空、去重并防御性复制。外部 `R`、`RemoteMessageDto`、`PushEventEmployeeDto`、紧急等级协议和远端返回码不得越过 adapter。

### 事件受理与规则隔离

1. 沿用现有事件定义、来源、门店、桌台、发生时间、payload schema 和启停校验；两个事件定义必须以 `SHOP_TABLE` 点位、启用状态配置，payload schema 必须保留 `tableBillId`、兼容字段 `orderId` 及嵌套兼容字段 `detail`。允许来源继续由事件定义配置，不在代码中扩大来源范围。
2. `EventIngestBizImpl#ingestAndPersist` 对通过校验的未及时事件直接写入 `ACCEPTED_NO_WORK_ORDER`，`reasonDesc` 固定为“事件已成功受理，不生成工单”，工单关联为空；非未及时事件仍写 `ACCEPTED_READY_FOR_RULE`。
3. 只有首次持久化返回的未及时事件调用 `touchSafely`。调用发生在成功结果已持久化之后，且不得置于包含事件写入的数据库事务内；应用用例返回后统一 `finish`。
4. `EventIngestCmdHandler` 保持发布白名单，不把 `ACCEPTED_NO_WORK_ORDER` 加入领域事件发布条件。
5. `EventRuleDispatchBizImpl#dispatchToRule` 增加共享事件分类的防御性判断：读取到未及时事件时直接跳过，不调用 `EventProcessAppService`。因此显式重投、误操作或未来恢复入口也不能为这两类事件建单。
6. `ACCEPTED_NO_WORK_ORDER` 作为成功终态加入事件结果枚举和展示标签；不得加入规则重试扫描或模板触发计划状态集合。既有结果判断若只区分“处理中/终态”，应将其归为无工单成功终态；仅服务固定任务建单的 accepted 集合不得无条件加入该码。

首次响应合同：

| 字段 | 值 |
| --- | --- |
| `eventId` | 首次受理事件号 |
| `resultCode` | `ACCEPTED_NO_WORK_ORDER` |
| `workOrderId` | `null` |
| `workOrderIds` | 空集合 |
| `reasonDesc` | `事件已成功受理，不生成工单` |
| `processedAt` | 成功结果持久化时间 |

重复上报继续返回 `IGNORED_DUPLICATE`、首次事件号和首次处理时间；因首次事件无工单关联，两个工单字段仍为空，且不暴露附加触达历史。

### 目标工单选择与数据结构

固定映射由领域策略维护为不可变映射：

| 事件编码 | 目标模板编码 |
| --- | --- |
| `CLEAR_TABLE_NOT_DONE` | `CLEAR_TABLE` |
| `WIPE_TABLE_NOT_DONE` | `WIPE_TABLE` |

日期窗口直接使用已按既有入口口径解析并持久化的 `occurredAt`：`dayStart = occurredAt.toLocalDate().atStartOfDay()`，`nextDayStart = dayStart.plusDays(1)`，不使用受理时间或服务器当前日期。查询必须使用左闭右开区间，避免跨日边界重复。

新增索引迁移，不新增表和字段：

```sql
ALTER TABLE `t_work_order_record`
  ADD INDEX `idx_work_order_not_done_lookup`
  (`state`, `store_code`, `point_code`, `template_code`, `create_time`, `work_order_id`);
```

状态只有固定三个值，放在索引后过滤，优先保证门店、桌台、模板、日期范围和目标排序共用同一访问路径。实施时必须用目标数据库 `EXPLAIN` 验证命中该索引、日期范围没有退化为全表扫描；不以索引存在代替执行计划验证。

选择伪代码：

```text
eventBillId = resolve(event.payloadData)
if empty(eventBillId): skip

candidates = query(store, table, mappedTemplate, targetStatuses, dayStart, nextDayStart)
// repository contract: createTime DESC, workOrderId DESC
for candidate in candidates:
    if eventBillId == trim(resolve(candidate.payloadData)):
        target = candidate
        break
if target is absent: skip
```

一旦 `target` 被选中，后续只读取该实体快照中的状态，不重新查询或选择其他工单。任何候选解析异常按当前候选不匹配处理；查询整体异常则结束本次附加流程。

### 状态决策与当前接收人

| 决策时状态 | 动作 | 接收人规则 |
| --- | --- | --- |
| `WAIT_CLAIM` | 调用 `upgradeWorkOrderMessageToUrgent(workOrderId)` | 不解析接收人，不新发消息 |
| `EXECUTING` | 发送专用二次提醒 | 当前有效 `CURRENT_HANDLER`，当前最大非空派发轮次 |
| `COMPLETED` | 发送专用二次提醒 | 当前有效 `HISTORY_HANDLER`，当前最大非空派发轮次 |
| 其他或空 | 跳过 | 不执行远端调用 |

执行中/已完成分支先校验工单原执行渠道，再查询参与关系。显式非手表渠道、当前关系为空、派发轮次为空或有效员工集合为空均直接跳过。读取关系后即冻结接收人快照；并发领取、转办或完成只可能使本次发送给已读取的集合或因查询为空而跳过，不得重查工单、切换加急/提醒分支或额外重试。

### 云手表合同

加急适配固定把单个工单号包装为单元素集合，并使用现有 `WorkOrderWatchProperties.messageSourceFromCode` 调用 `upgradeMessageToUrgent`。空响应、业务失败和异常统一转为内部异常，由附加用例隔离；不发送新消息。

二次提醒字段固定如下：

| 字段 | `CLEAR_TABLE_NOT_DONE` | `WIPE_TABLE_NOT_DONE` |
| --- | --- | --- |
| `eventType` | `WOKR_ORDER` | `WOKR_ORDER` |
| `title` | `未及时收台复核提醒` | `未及时擦台复核提醒` |
| `msg` | `{tableCode}桌台未及时收台，请线下复核处理` | `{tableCode}桌台未及时擦台，请线下复核处理` |
| `psCode` | 目标门店编码 | 目标门店编码 |
| `tableNo` | 目标桌台编码 | 目标桌台编码 |
| `businessId` | 本次 `eventId` | 本次 `eventId` |
| `businessIdDedup` | `true` | `true` |
| `employeeList` | 去重后的当前有效接收人全集 | 去重后的当前有效接收人全集 |

`workOrderId` 只用于本地调用上下文和摘要日志，不作为二次提醒 `businessId`，防止与原工单消息互相去重，也防止同一工单后续不同未及时事件被误吞。adapter 不复用动态工单模板；未知事件编码失败关闭，不回退成普通工单提醒。

### 一致性、失败与可观测性

- 一致性顺序固定为“事件成功结果落库 -> 同步附加触达 -> 返回成功结果”。附加触达不与事件写入、工单表或参与关系表开启跨资源事务。
- `touchSafely` 对事件账单解析、目标查询、候选解析、渠道解析、接收人查询和远端调用分阶段捕获异常；任一阶段失败即停止当前流程，既不向上抛出，也不调用另一动作。
- `EventIngestBizImpl` 在调用边界再做最后一层异常隔离，确保附加用例未来发生未预期运行时异常时仍执行 `finish(accepted)`。
- 不调用工单 `save/claim/complete/transfer`、状态日志或参与关系写端口；本功能只有事件结果写入、工单/参与关系读取和远端副作用。
- 日志事件采用 `table.not.done.touch.*` 前缀，每条最多携带 `eventId`、`workOrderId`、`phase/result` 三个关键字段。不得打印完整事件/工单实体、payload、员工列表或远端完整响应。
- 建议计数指标按 `attempted/skipped/succeeded/failed` 和动作类型聚合，不使用门店、桌台、工单号或员工号作为指标标签，避免高基数。

### 跨边界契约矩阵

| 边界/参与方 | 输入 | 输出/副作用 | 兼容方式 | 协作事项与验证限制 |
| --- | --- | --- | --- | --- |
| 上游事件方 -> 事件入口 | 两类事件、既有身份字段、`occurredAt`、门店/桌台、含账单字段的 payload | 既有响应结构，首次返回 `ACCEPTED_NO_WORK_ORDER` | 不新增字段；重复事件沿用 `IGNORED_DUPLICATE` | 上游来源必须包含在事件定义允许来源中；Pretty 内不验证真实上报方配置 |
| application -> infra | 固定模板、目标状态、日期窗口、门店/桌台 | 倒序候选工单集合 | 新增窄查询，不改变既有 `listByQuery` 排序 | 用 repository/mapper 测试和真实库 `EXPLAIN` 分别验证合同 |
| application -> 参与关系端口 | 工单号、状态对应角色 | 当前有效关系集合 | 复用既有端口；历史缺轮次失败关闭 | Pretty 内可验证过滤；无法证明生产历史数据完整率 |
| application -> 云手表端口 | 工单号或专用提醒命令 | 同步加急/推送，失败抛内部异常 | 现有端口新增显式方法；响应不外溢 | adapter 契约测试使用 mock；真实设备展示与超时歧义需联调观察 |
| adapter -> 云手表服务 | 加急回调或固定 `RemoteMessageDto` | 远端接收结果 | `businessId=eventId` 作为提醒级第二道防重 | 云手表需确认 `WOKR_ORDER` 及固定字段继续兼容，不能据本地 UT 声称真实送达 |

## 验证策略

- 覆盖验收标准：`AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005`、`AC-006`、`AC-007`、`AC-008`、`AC-009`、`AC-010`、`AC-011`、`AC-012`、`AC-013`。
- 稳定验证边界：验证首次/重复分流、固定映射与双字段排序、账单兼容解析、状态动作唯一性、渠道与当前轮次接收人过滤、远端消息字段、防重身份、失败吞吐和工单写端口零调用。
- Pretty 内验证：
  - 领域 UT：两类映射、三种目标状态、非目标状态、未知事件类型和状态竞态下动作只决策一次，对应 `AC-002`、`AC-005`、`AC-006`、`AC-012`。
  - 应用 UT：首次未及时事件落为 `ACCEPTED_NO_WORK_ORDER` 且不调用模板编排；重复冲突不调用附加用例；查询/解析/接收人/远端异常仍返回稳定成功结果，对应 `AC-001`、`AC-009`、`AC-010`、`AC-011`。
  - 查询与网关测试：日期左闭右开、状态/门店/桌台/模板过滤、创建时间及工单号倒序、账单不匹配跳过，对应 `AC-003`、`AC-004`。
  - 接收人 UT：显式非手表渠道、历史轮次、失效关系、空员工、重复员工被排除，多名同轮次有效员工全部保留，对应 `AC-007`。
  - adapter UT：加急参数、两类固定文案、`businessId=eventId`、去重开关、全量接收人和远端失败归一化，对应 `AC-005`、`AC-006`。
  - 无副作用回归：mock 验证工单保存、状态流转、参与关系写入、规则处理和领域事件发布均未发生；非未及时事件继续既有路径，对应 `AC-008`、`AC-013`。
  - 模块编译、现有相关测试、JDK 8 兼容检查、SQL 静态审查和 Pretty 文档机械校验。
- Pretty 外未验证范围：生产 MySQL 数据分布与索引执行计划、历史参与关系完整率、真实云手表服务的字段兼容、超时后的实际接收状态、真实设备展示和上游事件定义配置。
- 声明限制：本地 UT 或 mock 只能证明请求构造、分支与失败隔离，不能声称远端真实送达、历史数据全部可解析或生产索引一定生效。

验收映射：

| 验收标准 | 设计落点 |
| --- | --- |
| `AC-001` | 受理结果分流、发布白名单、规则重投失败关闭 |
| `AC-002` | 领域固定映射表 |
| `AC-003` | 日期窗口、候选查询和双字段倒序 |
| `AC-004` | 全条件粗筛与账单精确匹配 |
| `AC-005` | `WAIT_CLAIM` 单一加急分支 |
| `AC-006` | 两类固定提醒合同和全量接收人 |
| `AC-007` | 渠道快照、当前关系、轮次、身份过滤和去重 |
| `AC-008` | 只读端口与远端端口，禁止工单写入 |
| `AC-009` | 事件唯一键首次启动闸门 |
| `AC-010` | 事务外调用与双层异常隔离 |
| `AC-011` | 重复分支不调用附加用例、无补偿 |
| `AC-012` | 目标与接收人快照冻结、不重查不换分支 |
| `AC-013` | 事件类型白名单分流和既有查询/执行链路隔离 |

## 风险与回退

- 风险：历史工单执行配置或参与关系缺失，导致本应提醒的执行中/已完成工单失败关闭。触发信号是 `skipped` 中 `channel-unresolved/recipient-empty/dispatch-round-empty` 占比异常。缓解方式是按原因聚合指标并在上线前抽样核对历史数据；不以主表执行人或历史派发对象兜底，避免误发。回退时可关闭两类事件定义或附加触达开关，保留事件受理但停止远端动作；恢复后用抽样事件验证接收人口径，不补发停用期间事件。
- 风险：新索引在生产数据量和 MySQL 版本下未被采用，拉长同步上报耗时。触发信号是候选查询耗时和接口 P95/P99 上升。缓解方式是上线前对真实结构执行 `EXPLAIN`、上线后观察慢查询；回退索引或关闭附加触达不会影响已入库事件和工单。恢复验证需确认执行计划、慢查询和接口延迟恢复。
- 风险：远端超时但消息已接收，本地只能记录失败。事件唯一键禁止重试，二次提醒由 `eventId` 远端去重降低重复风险；加急属于同工单消息的状态提升。回退仅停止新增调用，不对已发送消息做撤回；恢复验证以新事件的远端调用结果和设备抽样为准。
- 风险：`ACCEPTED_NO_WORK_ORDER` 被既有调用方误当失败或被未来重投入口当作待处理。缓解方式是补齐结果枚举、展示、终态分类和显式重投保护，并做非未及时事件回归。若出现兼容问题，可关闭新事件定义并回退结果分流代码；已落库新结果码保持可读，恢复验证需覆盖查询展示、重复响应和规则重投不建单。
