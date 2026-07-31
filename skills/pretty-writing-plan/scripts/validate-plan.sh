#!/usr/bin/env bash

set -u

usage() {
  echo "用法：validate-plan.sh <计划文件> | --self-test" >&2
}

resolve_plan_relative_path() {
  source_plan=$1
  case "$source_plan" in
    docs/pretty/*/*) printf '%s\n' "${source_plan#docs/pretty/}" ;;
    */docs/pretty/*/*) printf '%s\n' "${source_plan#*/docs/pretty/}" ;;
    *) return 1 ;;
  esac
}

validate_plan_path() {
  plan_file=$1
  relative_path=$(resolve_plan_relative_path "$plan_file") || return 1

  topic=${relative_path%%/*}
  file_name=${relative_path#*/}
  if [ "$file_name" = "$relative_path" ] || printf '%s\n' "$file_name" | grep -Fq '/'; then
    return 1
  fi
  if ! printf '%s\n' "$topic" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$'; then
    return 1
  fi
  printf '%s\n' "$file_name" | grep -Eq "^[0-9]{4}-[0-9]{2}-[0-9]{2}-${topic}-plan\\.md$"
}

validate_document_contract() {
  document_plan=$1
  awk '
    function fail(message) {
      print "错误：" message > "/dev/stderr"
      failures++
    }

    BEGIN {
      section_order = "输入、目标与边界|具体实施任务|集成单元与执行编排|" \
        "需求到任务追溯|跨层验收矩阵|代码实现质量门禁|" \
        "测试与覆盖率门禁|计划生成质量审查|执行交接说明"
      expected_count = split(section_order, expected, "|")
    }

    /^```/ { in_fence = !in_fence; next }
    !in_fence && /^## / {
      section = $0
      sub(/^## /, "", section)
      section_count++
      if (section_count > expected_count || section != expected[section_count]) {
        fail("顶级章节顺序错误，第 " section_count " 节实际为：" section)
      }
    }

    END {
      if (section_count != expected_count) {
        fail("Plan 必须且只能包含约定的 " expected_count " 个顶级章节")
      }
      exit failures > 0 ? 1 : 0
    }
  ' "$document_plan"
}

validate_handoff_contract() {
  handoff_plan=$1
  handoff_relative_path=$(resolve_plan_relative_path "$handoff_plan") || return 1
  expected_handoff_path="docs/pretty/$handoff_relative_path"
  awk -v expected_path="$expected_handoff_path" '
    function fail(message) {
      print "错误：" message > "/dev/stderr"
      failures++
    }

    function field_value(line, value) {
      value = line
      sub(/^\*\*[^*]+：\*\*[[:space:]]*/, "", value)
      sub(/^[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      return value
    }

    /^```/ { in_fence = !in_fence; next }
    !in_fence && /^## 执行交接说明$/ { in_handoff = 1; next }
    !in_fence && in_handoff && /^## / { in_handoff = 0 }
    !in_fence && in_handoff && /^\*\*Plan 路径：\*\*/ {
      path_count++
      plan_path = field_value($0)
      next
    }
    !in_fence && in_handoff && /^\*\*校验状态：\*\*/ {
      validation_count++
      validation_status = field_value($0)
      next
    }
    !in_fence && in_handoff && /^\*\*未决项：\*\*/ {
      unresolved_count++
      unresolved_items = field_value($0)
      next
    }
    !in_fence && in_handoff && /^\*\*下一步选择：\*\*/ {
      next_count++
      next_choice = field_value($0)
      next
    }
    !in_fence && in_handoff && $0 !~ /^[[:space:]]*$/ {
      fail("执行交接说明只允许记录 Plan 路径、校验状态、未决项和下一步选择：" $0)
    }

    END {
      if (path_count != 1 || plan_path != "`" expected_path "`") {
        fail("执行交接说明必须唯一记录当前权威 Plan 路径：" expected_path)
      }
      if (validation_count != 1 || validation_status == "") fail("执行交接说明必须唯一记录非空校验状态")
      if (unresolved_count != 1 || unresolved_items == "") fail("执行交接说明必须唯一记录未决项，无未决项时写无")
      if (next_count != 1 || next_choice == "") fail("执行交接说明必须唯一记录下一步选择")
      exit failures > 0 ? 1 : 0
    }
  ' "$handoff_plan"
}

validate_orchestration_contract() {
  contract_plan=$1
  awk '
    function fail(message) {
      print "错误：" message > "/dev/stderr"
      failures++
    }

    function field_value(line, value) {
      value = line
      sub(/^.*\*\*[[:space:]]*/, "", value)
      sub(/[。.][[:space:]]*$/, "", value)
      sub(/^[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      return value
    }

    function task_number(label, value) {
      value = label
      sub(/^任务/, "", value)
      sub(/-.*/, "", value)
      return value + 0
    }

    function valid_task_label(label, name) {
      if (label !~ /^任务[1-9][0-9]*-/) return 0
      name = label
      sub(/^任务[0-9]+-/, "", name)
      return name != "" && index(name, "`") == 0 && index(name, "[") == 0 &&
        index(name, "]") == 0 && index(name, "/") == 0 && index(name, "\\") == 0 &&
        name !~ /[*_#<>{}|~]/ &&
        name !~ /(TODO|TBD|已完成|进行中|待处理|待开发|待验证|已验证|已关闭|已取消)/
    }

    function has_bare_task_ref(line) {
      gsub(/`任务[1-9][0-9]*-[^`]+`/, "", line)
      return line ~ /任务[1-9][0-9]*/
    }

    function close_unit() {
      if (unit_id == "") return
      if (included_count != 1 || unit_task_count == 0) {
        fail("集成单元 " unit_id " 必须且只能有一个非空的嵌套包含任务列表")
      }
      if (dependency_count != 1) fail("集成单元 " unit_id " 必须且只能声明一次前置依赖")
      if (order_count != 1 || unit_order_value != unit_index) {
        fail("集成单元 " unit_id " 的集成顺序必须等于声明次序 " unit_index)
      }
      if (risk_count != 1 || (risk != "低" && risk != "高")) {
        fail("集成单元 " unit_id " 的风险等级必须是低或高")
      }
      if (review_count != 1 || (review != "单 Reviewer" && review != "双 Reviewer")) {
        fail("集成单元 " unit_id " 的审查策略必须是单 Reviewer 或双 Reviewer")
      } else if (risk == "低" && review != "单 Reviewer") {
        fail("低风险集成单元 " unit_id " 必须使用单 Reviewer")
      } else if (risk == "高" && review != "双 Reviewer") {
        fail("高风险集成单元 " unit_id " 必须使用双 Reviewer")
      }
      if (ownership_count != 1 || ownership == "") fail("集成单元 " unit_id " 必须声明文件所有权")
      if (delivery_count != 1 || (delivery != "独立任务" && delivery != "原子任务组")) {
        fail("集成单元 " unit_id " 的交付类型必须是独立任务或原子任务组")
      } else if (delivery == "独立任务" && unit_task_count != 1) {
        fail("独立任务单元 " unit_id " 必须且只能包含一个任务")
      } else if (delivery == "原子任务组" && unit_task_count < 2) {
        fail("原子任务组 " unit_id " 必须包含至少两个不可拆分的任务")
      }
      if (atomic_reason_count != 1) {
        fail("集成单元 " unit_id " 必须声明原子组理由或带理由的不适用")
      } else if (delivery == "原子任务组" && atomic_reason ~ /^不适用/) {
        fail("原子任务组 " unit_id " 必须说明不可拆分原因")
      } else if (delivery == "独立任务" && atomic_reason !~ /^不适用（[^）]+）$/) {
        fail("独立任务单元 " unit_id " 的原子组理由必须写带理由的不适用")
      }
      if (verification_count != 1 || verification !~ /`[^`]+`/) {
        fail("集成单元 " unit_id " 必须给出反引号包裹的独立验证命令")
      }
      if (parallel_count != 1 || (parallel !~ /^禁止$/ && parallel !~ /^允许（[^）]+）$/)) {
        fail("集成单元 " unit_id " 必须明确并行实现是禁止还是带理由允许")
      }
      if (isolation_count != 1) {
        fail("集成单元 " unit_id " 必须声明并行隔离证据")
      } else if (parallel ~ /^允许/ &&
                 (isolation ~ /^不适用/ || isolation !~ /worktree/ || isolation !~ /文件/ ||
                  isolation !~ /依赖/ || isolation !~ /集成顺序/)) {
        fail("允许并行实现的集成单元 " unit_id " 必须证明 worktree、文件、依赖和集成顺序隔离")
      }
      if (checkpoint_count != 1 || checkpoint !~ /worktree/ || checkpoint !~ /候选提交/ || checkpoint !~ /独立 Reviewer/ ||
          checkpoint !~ /人工批准.*应用.*候选差异/ || checkpoint !~ /应用.*未暂存/ ||
          checkpoint !~ /人工批准.*当前分支提交/ || checkpoint !~ /当前分支本地提交/) {
        fail("集成单元 " unit_id " 必须声明候选提交、独立 Review、差异应用批准、未暂存差异应用、当前分支提交批准和本地提交检查点")
      }
      unit_id = ""
      reading_included = 0
    }

    /^```/ { in_fence = !in_fence; next }
    !in_fence && /^## 具体实施任务$/ { in_tasks = 1; next }
    !in_fence && in_tasks && /^## / { in_tasks = 0 }
    !in_fence && in_tasks && /^### 任务/ {
      label = $0
      sub(/^### /, "", label)
      if (!valid_task_label(label)) {
        fail("任务标题必须使用任务<n>-<中文动宾短语>，且不得包含 Markdown、路径或状态：" label)
        next
      }
      number = task_number(label)
      task_count++
      if (number != task_count) fail("任务必须从 1 开始连续编号，实际为：" label)
      if (tasks[number]) fail("任务编号重复：任务" number)
      tasks[number] = label
      task_labels[label] = 1
      next
    }

    !in_fence && /^## 集成单元与执行编排$/ { contract_count++; in_contract = 1; next }
    !in_fence && in_contract && /^## / { close_unit(); in_contract = 0 }
    !in_fence && in_contract && has_bare_task_ref($0) {
      fail("集成单元中的任务引用必须使用反引号包裹的完整任务标识：" $0)
    }

    in_contract && /^\*\*默认执行模式：\*\*/ { default_mode_count++; default_mode = field_value($0); next }
    in_contract && /^\*\*可选执行模式：\*\*/ { optional_mode_count++; optional_mode = field_value($0); next }
    in_contract && /^\*\*模式切换条件：\*\*/ { mode_switch_count++; mode_switch = field_value($0); next }
    in_contract && /^\*\*旧 Plan 迁移：\*\*/ { migration_count++; migration = field_value($0); next }

    in_contract && /^### 集成单元 [A-Z][A-Z0-9-]*：/ {
      close_unit()
      unit_id = $0
      sub(/^### 集成单元 /, "", unit_id)
      sub(/：.*$/, "", unit_id)
      if (units[unit_id]) fail("集成单元标识重复：" unit_id)
      units[unit_id] = 1
      unit_index++
      if (unit_id != "U" unit_index) fail("集成单元必须按 U1、U2 顺序编号，实际为 " unit_id)
      included_count = dependency_count = order_count = risk_count = review_count = 0
      ownership_count = delivery_count = atomic_reason_count = verification_count = 0
      parallel_count = isolation_count = checkpoint_count = unit_task_count = 0
      risk = review = ownership = delivery = atomic_reason = verification = parallel = isolation = checkpoint = ""
      reading_included = 0
      next
    }

    in_contract && unit_id != "" && /^- \*\*包含任务：\*\*[[:space:]]*$/ {
      included_count++
      reading_included = 1
      next
    }

    in_contract && unit_id != "" && reading_included && /^  - / {
      value = $0
      if (value !~ /^  - `任务[1-9][0-9]*-[^`]+`[。.]*$/) {
        fail("集成单元 " unit_id " 的包含任务必须一行一个反引号包裹的完整任务标识：" value)
        next
      }
      sub(/^  - `/, "", value)
      sub(/`[。.]*$/, "", value)
      number = task_number(value)
      if (!task_labels[value]) fail("集成单元 " unit_id " 引用了不存在或名称不一致的任务：" value)
      membership[number]++
      unit_task_count++
      next
    }

    in_contract && unit_id != "" && reading_included { reading_included = 0 }
    in_contract && unit_id != "" && /^- \*\*前置依赖：\*\*/ {
      dependency_count++
      value = field_value($0)
      if (value != "无") {
        dependency_found = 0
        while (match(value, /U[0-9]+/)) {
          dependency = substr(value, RSTART, RLENGTH)
          dependency_found++
          if (!units[dependency] || dependency == unit_id) {
            fail("集成单元 " unit_id " 的前置依赖必须引用此前已声明的单元：" dependency)
          }
          value = substr(value, RSTART + RLENGTH)
        }
        if (dependency_found == 0) fail("集成单元 " unit_id " 的前置依赖格式无效")
      }
      next
    }
    in_contract && unit_id != "" && /^- \*\*集成顺序：\*\*/ { order_count++; unit_order_value = field_value($0) + 0; next }
    in_contract && unit_id != "" && /^- \*\*风险等级：\*\*/ { risk_count++; risk = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*审查策略：\*\*/ { review_count++; review = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*文件所有权：\*\*/ { ownership_count++; ownership = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*交付类型：\*\*/ { delivery_count++; delivery = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*原子组理由：\*\*/ { atomic_reason_count++; atomic_reason = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*独立验证：\*\*/ { verification_count++; verification = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*并行实现：\*\*/ { parallel_count++; parallel = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*并行隔离证据：\*\*/ { isolation_count++; isolation = field_value($0); next }
    in_contract && unit_id != "" && /^- \*\*集成检查点：\*\*/ { checkpoint_count++; checkpoint = field_value($0); next }

    END {
      if (in_contract) close_unit()
      if (contract_count != 1) fail("必须且只能包含一个 ## 集成单元与执行编排；旧 Plan 必须显式迁移后重新批准")
      if (default_mode_count != 1 || default_mode != "单集成单元审批") fail("默认执行模式必须是单集成单元审批")
      if (optional_mode_count != 1 || optional_mode != "一次性执行") fail("可选执行模式必须是一次性执行")
      if (mode_switch_count != 1 || mode_switch !~ /安全检查点/ || mode_switch !~ /人工批准/) {
        fail("模式切换条件必须限定安全检查点并重新记录人工批准")
      }
      if (migration_count != 1 || migration !~ /显式迁移/ || migration !~ /重新校验/ || migration !~ /人工批准/) {
        fail("旧 Plan 迁移必须要求显式迁移、重新校验和人工批准")
      }
      if (unit_index == 0) fail("执行编排至少需要一个集成单元")
      if (task_count == 0) fail("计划至少需要一个可执行任务")
      for (number in tasks) {
        if (membership[number] != 1) fail(tasks[number] " 必须且只能归属一个集成单元")
      }
      exit failures > 0 ? 1 : 0
    }
  ' "$contract_plan"
}

validate_review_references() {
  review_plan=$1
  awk '
    function fail(message) {
      print "错误：" message > "/dev/stderr"
      failures++
    }

    function trim(value) {
      sub(/^[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      return value
    }

    function collect_refs(line, section, count, ref) {
      count = 0
      while (match(line, /`任务[1-9][0-9]*-[^`]+`/)) {
        ref = substr(line, RSTART + 1, RLENGTH - 2)
        count++
        if (!tasks[ref]) fail(section " 引用了不存在或名称不一致的任务：" ref)
        else section_refs[section SUBSEP ref]++
        line = substr(line, RSTART + RLENGTH)
      }
      return count
    }

    function has_bare_task_ref(line) {
      gsub(/`任务[1-9][0-9]*-[^`]+`/, "", line)
      return line ~ /任务[1-9][0-9]*/
    }

    function table_data(line) {
      return line ~ /^\|/ && line !~ /^\|[[:space:]]*-+/ &&
        line !~ /^\|[[:space:]]*(需求标识|业务链路|审查维度)[[:space:]]*\|/
    }

    /^```/ { in_fence = !in_fence; next }
    !in_fence && section == "具体实施任务" && /^### 任务[1-9][0-9]*-/ {
      label = $0
      sub(/^### /, "", label)
      tasks[label] = 1
      next
    }
    !in_fence && /^## / { section = $0; sub(/^## /, "", section); next }
    in_fence { next }
    (section == "需求到任务追溯" || section == "跨层验收矩阵" ||
     section == "代码实现质量门禁") && has_bare_task_ref($0) {
      fail(section " 中的任务引用必须使用反引号包裹的完整任务标识：" $0)
    }

    section == "需求到任务追溯" && table_data($0) {
      split($0, columns, "|")
      requirement_id = trim(columns[2])
      requirement_goal = trim(columns[3])
      requirement_tasks = trim(columns[4])
      acceptance = trim(columns[5])
      ref_count = collect_refs(requirement_tasks, section)
      if (ref_count == 0) fail("需求追溯的对应任务列必须引用至少一个完整任务标识：" $0)
      if (requirement_id == "" || requirement_ids[requirement_id]++) fail("需求标识不能为空或重复：" requirement_id)
      if (requirement_goal == "" || acceptance == "") fail("需求追溯的目标和验收标准不能为空：" $0)
      trace_rows++
      next
    }

    section == "跨层验收矩阵" && /^不适用（[^）]+）[。.]*$/ { cross_not_applicable++; next }
    section == "跨层验收矩阵" && table_data($0) {
      split($0, columns, "|")
      business_flow = trim(columns[2])
      layer_boundary = trim(columns[3])
      contract_effect = trim(columns[4])
      acceptance_method = trim(columns[5])
      cross_tasks = trim(columns[6])
      if (business_flow == "" || layer_boundary == "" || contract_effect == "" || acceptance_method == "") {
        fail("跨层验收矩阵的业务链路、边界、契约和验收方式不能为空：" $0)
      }
      if (collect_refs(cross_tasks, section) == 0) fail("跨层验收矩阵的对应任务列必须引用完整任务标识：" $0)
      cross_rows++
      next
    }

    section == "代码实现质量门禁" && table_data($0) {
      split($0, columns, "|")
      dimension = trim(columns[2])
      conclusion = trim(columns[3])
      quality_tasks = trim(columns[4])
      if (dimension != "功能完整性" && dimension != "简洁性与必要性" &&
          dimension != "可读性与业务表达" && dimension != "测试完整性保护" &&
          dimension != "变更范围控制") {
        fail("代码实现质量门禁包含未知审查维度：" dimension)
      } else {
        dimension_count[dimension]++
      }
      if (conclusion == "") fail("代码实现质量门禁的具体结论不能为空：" dimension)
      if (collect_refs(quality_tasks, section) == 0) fail("代码实现质量门禁的对应任务列必须关联完整任务标识：" dimension)
      next
    }

    END {
      if (trace_rows == 0) fail("需求到任务追溯至少需要一条有效映射")
      for (task in tasks) {
        if (section_refs["需求到任务追溯" SUBSEP task] == 0) fail(task " 缺少需求或交付保障来源")
      }
      if (!((cross_rows > 0 && cross_not_applicable == 0) ||
            (cross_rows == 0 && cross_not_applicable == 1))) {
        fail("跨层验收矩阵必须提供业务链路矩阵，或唯一的带理由不适用结论")
      }
      required_dimension[1] = "功能完整性"
      required_dimension[2] = "简洁性与必要性"
      required_dimension[3] = "可读性与业务表达"
      required_dimension[4] = "测试完整性保护"
      required_dimension[5] = "变更范围控制"
      for (dimension_index = 1; dimension_index <= 5; dimension_index++) {
        if (dimension_count[required_dimension[dimension_index]] != 1) {
          fail("代码实现质量门禁必须且只能记录一次：" required_dimension[dimension_index])
        }
      }
      exit failures > 0 ? 1 : 0
    }
  ' "$review_plan"
}

validate_task_tdd_cycles() {
  tdd_plan=$1
  awk '
    function fail(message) {
      print "错误：" message > "/dev/stderr"
      failures++
    }

    function has_value(line, prefix, value) {
      value = line
      sub("^[[:space:]]*" prefix "[[:space:]]*", "", value)
      gsub(/`/, "", value)
      gsub(/[[:space:]。.]/, "", value)
      return value != ""
    }

    function reset_stage() {
      stage_code_lines = 0
      stage_command_count = 0
      stage_expected_count = 0
      stage_body_lines = 0
      stage_table_rows = 0
      in_code_block = 0
    }

    function close_stage() {
      if (cycle_state == 0) return
      if (cycle_state == 1 && stage_code_lines == 0) {
        fail(task_label " 的失败测试步骤必须包含非空代码块")
      } else if (cycle_state == 3 && stage_code_lines == 0 && stage_table_rows < 2) {
        fail(task_label " 的最小实现步骤必须包含非空代码块或完整变更表")
      } else if ((cycle_state == 2 || cycle_state == 4 || cycle_state == 6) &&
                 (stage_command_count != 1 || stage_expected_count != 1)) {
        fail(task_label " 的步骤 " cycle_state " 必须各包含一个非空运行命令和预期结果")
      } else if (cycle_state == 5 && stage_body_lines == 0) {
        fail(task_label " 的重构步骤必须包含明确动作")
      }
      reset_stage()
    }

    function close_task() {
      if (task_label == "") return
      close_stage()
      if (file_section_count != 1 || file_entry_count == 0) {
        fail(task_label " 必须且只能声明一份非空的精确文件清单")
      }
      if (task_type_count != 1 || (task_type != "业务行为" && task_type !~ /^非行为（[^）]+）$/)) {
        fail(task_label " 必须声明业务行为或带理由的非行为任务类型")
      } else if (task_type == "业务行为" && cycle_count == 0) {
        fail(task_label " 是业务行为，但缺少 TDD 周期")
      } else if (task_type ~ /^非行为/ &&
                 (equivalent_command_count != 1 || equivalent_expected_count != 1 ||
                  !equivalent_command_has_value || !equivalent_expected_has_value)) {
        fail(task_label " 是非行为任务，但缺少等价验证命令或预期结果")
      }
      if (cycle_count > 0 && cycle_state != 6) {
        fail(task_label " 的最后一个行为周期未完整执行到再验证")
      }
      cycle_count = 0
      cycle_state = 0
      task_type_count = 0
      equivalent_command_count = 0
      equivalent_expected_count = 0
      equivalent_command_has_value = 0
      equivalent_expected_has_value = 0
      file_section_count = 0
      file_entry_count = 0
      reading_files = 0
      task_label = ""
    }

    function advance(expected, next_state, stage) {
      if (cycle_state != expected) {
        fail(task_label " 的 TDD 阶段顺序错误，当前阶段：" stage)
      }
      cycle_state = next_state
    }

    /^### 任务[1-9][0-9]*-/ {
      close_task()
      task_label = $0
      next
    }

    task_label != "" && /^## / {
      close_task()
      next
    }

    task_label != "" && /^任务类型：/ {
      task_type_count++
      task_type = $0
      sub(/^任务类型：[[:space:]]*/, "", task_type)
      sub(/[。.][[:space:]]*$/, "", task_type)
      next
    }

    task_label != "" && /^\*\*文件[：:]\*\*/ {
      file_section_count++
      file_line = $0
      sub(/^\*\*文件[：:]\*\*[[:space:]]*/, "", file_line)
      if (file_line ~ /`[^`]+`/) file_entry_count++
      reading_files = 1
      next
    }
    task_label != "" && reading_files && /^- / && /`[^`]+`/ {
      file_entry_count++
      next
    }
    task_label != "" && reading_files { reading_files = 0 }

    task_label != "" && /^等价验证命令：/ {
      equivalent_command_count++
      equivalent_command_has_value = has_value($0, "等价验证命令：")
      next
    }
    task_label != "" && /^等价验证预期：/ {
      equivalent_expected_count++
      equivalent_expected_has_value = has_value($0, "等价验证预期：")
      next
    }

    task_label != "" && /^- \[ \] \*\*步骤 [0-9]+：/ {
      close_stage()
      if ($0 ~ /编写失败测试/) {
        if (cycle_count > 0 && cycle_state != 6) {
          fail(task_label " 在上一行为周期闭环前开始了新的失败测试")
        }
        cycle_count++
        cycle_state = 1
      } else if ($0 ~ /验证 RED/) {
        advance(1, 2, "验证 RED")
      } else if ($0 ~ /最小实现/) {
        advance(2, 3, "最小实现")
      } else if ($0 ~ /验证 GREEN/) {
        advance(3, 4, "验证 GREEN")
      } else if ($0 ~ /重构/ && $0 !~ /复验/) {
        advance(4, 5, "重构")
      } else if ($0 ~ /再验证|重构复验/) {
        advance(5, 6, "再验证")
      }
      reset_stage()
      next
    }

    task_label != "" && cycle_state > 0 && /^```/ {
      in_code_block = !in_code_block
      next
    }

    task_label != "" && cycle_state > 0 && in_code_block {
      if ($0 !~ /^[[:space:]]*$/) {
        stage_code_lines++
        stage_body_lines++
      }
      next
    }

    task_label != "" && cycle_state > 0 && /^\|.*\|[[:space:]]*$/ {
      stage_table_rows++
      stage_body_lines++
      next
    }

    task_label != "" && cycle_state > 0 && /^运行：/ {
      if (has_value($0, "运行：")) stage_command_count++
      next
    }

    task_label != "" && cycle_state > 0 && /^预期：/ {
      if (has_value($0, "预期：")) stage_expected_count++
      next
    }

    task_label != "" && cycle_state > 0 && $0 !~ /^[[:space:]]*$/ {
      stage_body_lines++
    }

    END {
      close_task()
      exit failures > 0 ? 1 : 0
    }
  ' "$tdd_plan"
}

run_self_test() {
  test_dir=$(mktemp -d "${TMPDIR:-/tmp}/pretty-writing-plan.XXXXXX") || exit 2
  fixture_dir="$test_dir/docs/pretty/rush-order"
  legacy_dir="$test_dir/docs/superpowers/plans"
  mkdir -p "$fixture_dir" "$legacy_dir"
  legacy_format_plan="$fixture_dir/2026-07-28-rush-order-plan.md"
  bad_plan="$fixture_dir/2026-07-29-rush-order-plan.md"
  auditless_plan="$fixture_dir/2026-07-30-rush-order-plan.md"
  english_plan="$fixture_dir/2026-07-31-rush-order-plan.md"
  coverage_less_plan="$fixture_dir/2026-08-01-rush-order-plan.md"
  threshold_less_plan="$fixture_dir/2026-08-02-rush-order-plan.md"
  command_less_plan="$fixture_dir/2026-08-03-rush-order-plan.md"
  exclusion_less_plan="$fixture_dir/2026-08-04-rush-order-plan.md"
  implementation_quality_less_plan="$fixture_dir/2026-08-05-rush-order-plan.md"
  mixed_label_plan="$fixture_dir/2026-08-06-rush-order-plan.md"
  missing_orchestration_plan="$fixture_dir/2026-08-09-rush-order-plan.md"
  duplicate_assignment_plan="$fixture_dir/2026-08-10-rush-order-plan.md"
  invalid_dependency_plan="$fixture_dir/2026-08-11-rush-order-plan.md"
  reviewer_mismatch_plan="$fixture_dir/2026-08-12-rush-order-plan.md"
  parallel_without_isolation_plan="$fixture_dir/2026-08-13-rush-order-plan.md"
  missing_ownership_plan="$fixture_dir/2026-08-14-rush-order-plan.md"
  invalid_unit_id_plan="$fixture_dir/2026-08-15-rush-order-plan.md"
  missing_green_plan="$fixture_dir/2026-08-16-rush-order-plan.md"
  missing_refactor_recheck_plan="$fixture_dir/2026-08-17-rush-order-plan.md"
  weak_threshold_plan="$fixture_dir/2026-08-18-rush-order-plan.md"
  empty_implementation_plan="$fixture_dir/2026-08-19-rush-order-plan.md"
  empty_red_command_plan="$fixture_dir/2026-08-20-rush-order-plan.md"
  empty_equivalent_plan="$fixture_dir/2026-08-21-rush-order-plan.md"
  table_implementation_plan="$fixture_dir/2026-08-22-rush-order-plan.md"
  good_plan="$fixture_dir/2026-08-23-rush-order-plan.md"
  reordered_sections_plan="$fixture_dir/2026-08-24-rush-order-plan.md"
  stale_unit_task_name_plan="$fixture_dir/2026-08-25-rush-order-plan.md"
  inline_unit_tasks_plan="$fixture_dir/2026-08-26-rush-order-plan.md"
  untraced_second_task_plan="$fixture_dir/2026-08-27-rush-order-plan.md"
  stale_quality_reference_plan="$fixture_dir/2026-08-28-rush-order-plan.md"
  invalid_task_name_plan="$fixture_dir/2026-08-29-rush-order-plan.md"
  cross_not_applicable_plan="$fixture_dir/2026-08-30-rush-order-plan.md"
  missing_handoff_path_plan="$fixture_dir/2026-08-31-rush-order-plan.md"
  empty_quality_conclusion_plan="$fixture_dir/2026-09-01-rush-order-plan.md"
  mixed_task_reference_plan="$fixture_dir/2026-09-02-rush-order-plan.md"
  misplaced_trace_reference_plan="$fixture_dir/2026-09-03-rush-order-plan.md"
  atomic_group_plan="$fixture_dir/2026-09-04-rush-order-plan.md"
  multi_task_independent_plan="$fixture_dir/2026-09-05-rush-order-plan.md"
  single_task_atomic_plan="$fixture_dir/2026-09-06-rush-order-plan.md"
  non_behavior_plan="$fixture_dir/2026-09-07-rush-order-plan.md"
  task_level_commit_plan="$fixture_dir/2026-09-08-rush-order-plan.md"
  legacy_plan="$legacy_dir/2026-07-28-rush-order-plan.md"
  mismatched_topic_plan="$fixture_dir/2026-08-07-other-plan.md"
  missing_plan_suffix="$fixture_dir/2026-08-08-rush-order.md"

  cleanup_self_test() {
    rm -rf -- "$test_dir"
  }
  trap cleanup_self_test EXIT INT TERM

  cat > "$bad_plan" <<'EOF'
# Rush Implementation Plan

TODO: add appropriate validation and write tests for the above.
EOF

  cat > "$good_plan" <<'EOF'
# 加急工单实施计划

> **Agent 执行要求：** REQUIRED SUB-SKILL: 使用 `pretty-executing-plan` 并维护执行报告。
> **必需质量 Skill：** `superpowers:test-driven-development`、
> `clean-code-guard` 和 `superpowers:verification-before-completion`。

## 输入、目标与边界

**Design 输入：** 已批准的加急工单技术设计。

**实现目标：** 新增加急状态表达，并保持既有调用方兼容。

**范围边界：** 只修改加急命令及其直接测试。

**非目标：** 不重构无关工单状态流转。

## 具体实施任务

### 任务1-实现加急命令

任务类型：业务行为。

**文件：**
- 新增：`src/RushCommand.java`
- 测试：`src/RushCommandTest.java`

- [ ] **步骤 1：编写失败测试**

```java
assertTrue(command.isRush());
```

- [ ] **步骤 2：验证 RED**

运行：`mvn -Dtest=RushCommandTest test`

预期：测试因缺少 `RushCommand` 而失败。

- [ ] **步骤 3：最小实现**

```java
public boolean isRush() {
    return true;
}
```

- [ ] **步骤 4：验证 GREEN**

运行：`mvn -Dtest=RushCommandTest test`

预期：定向测试通过。

- [ ] **步骤 5：重构**

保持当前直接实现，不引入额外抽象。

- [ ] **步骤 6：再验证**

运行：`mvn -Dtest=RushCommandTest test`

预期：重构复验通过。

## 集成单元与执行编排

**默认执行模式：** 单集成单元审批

**可选执行模式：** 一次性执行

**模式切换条件：** 仅允许在单元尚未开始或单元已经完成当前分支集成提交的安全检查点切换，并重新记录人工批准。

**旧 Plan 迁移：** 旧格式 Plan 必须显式迁移、重新校验并获得人工批准，禁止执行阶段自动推断。

### 集成单元 U1：新增加急命令

- **包含任务：**
  - `任务1-实现加急命令`
- **前置依赖：** 无
- **集成顺序：** 1
- **风险等级：** 低
- **审查策略：** 单 Reviewer
- **文件所有权：** `src/RushCommand.java`、`src/RushCommandTest.java`
- **交付类型：** 独立任务
- **原子组理由：** 不适用（单任务可独立构建和验证）
- **独立验证：** `mvn -Dtest=RushCommandTest test`
- **并行实现：** 禁止
- **并行隔离证据：** 不适用（默认模式串行实现）
- **集成检查点：** 隔离 worktree 候选提交 -> 独立 Reviewer -> 人工批准应用候选差异 -> 将候选差异应用到当前工作区（保持未暂存） -> 人工批准当前分支提交 -> 当前分支本地提交

## 需求到任务追溯

| 需求标识 | 需求或保障目标 | 对应任务 | 验收标准 |
|---|---|---|---|
| R1 | 新增加急状态表达 | `任务1-实现加急命令` | 加急命令返回真实状态 |

## 跨层验收矩阵

| 业务链路 | 层级与边界转换 | 关键契约或副作用 | 验收方式 | 对应任务 |
|---|---|---|---|---|
| 加急状态读取 | application DTO → domain command | 保持既有调用方兼容 | 定向单元测试 | `任务1-实现加急命令` |

## 代码实现质量门禁

| 审查维度 | 具体设计结论 | 对应任务 |
|---|---|---|
| 功能完整性 | 加急行为与兼容边界均有实现和验收 | `任务1-实现加急命令` |
| 简洁性与必要性 | 直接扩展现有命令，不增加包装层 | `任务1-实现加急命令` |
| 可读性与业务表达 | 使用加急领域术语直接表达业务意图 | `任务1-实现加急命令` |
| 测试完整性保护 | 保留失败测试与重构复验 | `任务1-实现加急命令` |
| 变更范围控制 | 仅修改加急命令及直接测试 | `任务1-实现加急命令` |

## 测试与覆盖率门禁

**覆盖率范围：** 本次新增和修改的业务代码。

**排除项及理由：** 纯 DTO 与 Lombok 生成的 getter/setter，不包含业务行为。

**覆盖率指标：** 行覆盖率与分支覆盖率，核心状态分支全部有行为测试。

**覆盖率阈值：** 行覆盖率不低于 80%，分支覆盖率不低于 70%。

**覆盖率命令：** `mvn test jacoco:report jacoco:check`

**报告位置：** `target/site/jacoco/index.html`

**成功预期：** 测试通过且 JaCoCo 阈值校验成功。

**失败判定：** 测试失败或任一覆盖率低于阈值时返回非零状态。

### 任务级验证

逐任务执行任务正文中的 RED、GREEN 和重构复验命令。

### 集成单元级验证

运行：`mvn -Dtest=RushCommandTest test`

预期：集成单元定向测试通过。

### 最终覆盖率与全量回归

- [ ] **步骤 1：运行全量测试和覆盖率校验**

运行：`mvn test jacoco:report jacoco:check`

预期：全量测试通过，行覆盖率和分支覆盖率达到阈值。

## 计划生成质量审查

### 实际使用的计划生成 Skill

- `121-java-object-oriented-design` — 审查 `RushCommand` 的单一职责。

### 质量发现与计划修正

- 无阻塞问题；`RushCommand` 保持单一命令职责。

### 最终审查结论

通过；全部发现已修正并完成复验。

## 执行交接说明

**Plan 路径：** `docs/pretty/rush-order/2026-08-23-rush-order-plan.md`

**校验状态：** 已通过机械校验与语义审查，等待用户批准。

**未决项：** 无。

**下一步选择：** 批准计划、要求修改、查看任务或选择一次性执行。
EOF

  cat > "$legacy_format_plan" <<'EOF'
# 加急工单实施计划

> **Agent 执行要求：** REQUIRED SUB-SKILL: 使用 `pretty-executing-plan` 并维护执行报告。
> **必需质量 Skill：** `superpowers:test-driven-development`、
> `clean-code-guard` 和 `superpowers:verification-before-completion`。

## 计划生成质量审查

**实际使用的计划生成 Skill：**
- `121-java-object-oriented-design` — 审查 `RushCommand` 的单一职责。

**质量发现与计划修正：**
- 无阻塞问题；`RushCommand` 保持单一命令职责。

**未使用的候选 Skill 及原因：**
- 无。

## 代码实现质量门禁

**功能完整性：** 加急行为、非法状态拒绝和调用失败传播均映射到代码与验收。

**简洁性与必要性：** 直接扩展现有命令，不新增包装层或预留扩展点。

**可读性与业务表达：** 使用加急领域术语命名，命令只承担加急状态表达职责。

**测试完整性保护：** 保留正常、非法状态和失败传播测试，不弱化行为断言与覆盖率要求。

**适用范围：** 仅修改加急命令及其直接测试，不重构无关旧代码。

## 执行编排合同

**默认执行模式：** 单集成单元审批

**可选执行模式：** 一次性执行

**模式切换条件：** 仅允许在单元尚未开始或单元已经完成当前分支集成提交的安全检查点切换，并重新记录人工批准。

**旧 Plan 迁移：** 缺少本合同的旧 Plan 必须由 `pretty-writing-plan` 显式迁移、重新校验并获得人工批准，禁止执行阶段自动推断。

### 集成单元 U1：新增加急命令

- **包含任务：** 任务 1
- **前置依赖：** 无
- **集成顺序：** 1
- **风险等级：** 低
- **审查策略：** 单 Reviewer
- **文件所有权：** `src/RushCommand.java`、`src/RushCommandTest.java`
- **交付类型：** 独立任务
- **原子组理由：** 不适用（单任务可独立构建和验证）
- **独立验证：** `mvn -Dtest=RushCommandTest test`
- **并行实现：** 禁止
- **并行隔离证据：** 不适用（默认模式串行实现）
- **集成检查点：** 隔离 worktree 候选提交 -> 独立 Reviewer -> 人工批准应用候选差异 -> 将候选差异应用到当前工作区（保持未暂存） -> 人工批准当前分支提交 -> 当前分支本地提交

## 测试与覆盖率门禁

**覆盖率范围：** 本次新增和修改的业务代码。

**排除项及理由：** 纯 DTO 与 Lombok 生成的 getter/setter，不包含业务行为。

**覆盖率指标：** 行覆盖率与分支覆盖率，核心状态分支全部有行为测试。

**覆盖率阈值：** 行覆盖率不低于 80%，分支覆盖率不低于 70%。

**覆盖率命令：**

运行：`mvn -Dtest=RushCommandTest test jacoco:report jacoco:check`

报告位置：`target/site/jacoco/index.html`

成功预期：测试通过且 JaCoCo 阈值校验成功。

失败判定：测试失败或任一覆盖率低于阈值时返回非零状态。

### 任务 1：新增加急命令

任务类型：业务行为。

**文件：**
- 新增：`src/RushCommand.java`
- 测试：`src/RushCommandTest.java`

- [ ] **步骤 1：编写失败测试**

```java
assertTrue(command.isRush());
```

- [ ] **步骤 2：验证 RED**

运行：`mvn -Dtest=RushCommandTest test`

预期：测试因缺少 `RushCommand` 而失败。

- [ ] **步骤 3：最小实现**

```java
public boolean isRush() {
    return true;
}
```

- [ ] **步骤 4：验证 GREEN**

运行：`mvn -Dtest=RushCommandTest test`

预期：定向测试通过。

- [ ] **步骤 5：重构**

保持当前直接实现，不引入额外抽象。

- [ ] **步骤 6：再验证**

运行：`mvn -Dtest=RushCommandTest test`

预期：重构复验通过。

## 最终覆盖率与全量回归门禁

- [ ] **步骤 1：运行全量测试和覆盖率校验**

运行：`mvn test jacoco:report jacoco:check`

预期：全量测试通过，行覆盖率和分支覆盖率达到阈值。
EOF

  cat > "$english_plan" <<'EOF'
# Rush Work Order Implementation Plan

> REQUIRED SUB-SKILL: Use `pretty-executing-plan` and `superpowers:test-driven-development`.
> REQUIRED: `clean-code-guard` and `superpowers:verification-before-completion`.

## Plan-generation quality review

### Task 1: Add rush command

**Files:** `src/RushCommand.java`
- [ ] Step 1
Run: `mvn test`
Expected: PASS
```java
assertTrue(true);
```
EOF

  cat > "$coverage_less_plan" <<'EOF'
# 加急工单实施计划

> REQUIRED SUB-SKILL: 使用 `pretty-executing-plan`、`superpowers:test-driven-development`、`clean-code-guard` 和 `superpowers:verification-before-completion`。

## 计划生成质量审查
**实际使用的计划生成 Skill：** `121-java-object-oriented-design`
**质量发现与计划修正：** 无阻塞问题。
**未使用的候选 Skill 及原因：** 无。

### 任务 1：新增加急命令
**文件：** `src/RushCommand.java`
- [ ] **步骤 1：编写失败测试**
运行：`mvn test`
预期：测试失败。
```java
assertTrue(true);
```
EOF

  sed '/覆盖率阈值/d' "$good_plan" > "$threshold_less_plan"
  sed '/覆盖率命令/d;/jacoco:report/d;/报告位置/d' "$good_plan" > "$command_less_plan"
  sed '/排除项及理由/d' "$good_plan" > "$exclusion_less_plan"
  sed '/^## 代码实现质量门禁$/,/^## 测试与覆盖率门禁$/{ /^## 测试与覆盖率门禁$/!d; }' \
    "$good_plan" > "$implementation_quality_less_plan"
  sed 's/步骤 1：编写失败测试/Step 1: Write failing test/' "$good_plan" > "$mixed_label_plan"
  sed '/^## 集成单元与执行编排$/,/^## 需求到任务追溯$/{ /^## 需求到任务追溯$/!d; }' \
    "$good_plan" > "$missing_orchestration_plan"
  awk '
    /^## 需求到任务追溯$/ {
      print "### 集成单元 U2：重复归属"
      print ""
      print "- **包含任务：**"
      print "  - `任务1-实现加急命令`"
      print "- **前置依赖：** U1"
      print "- **集成顺序：** 2"
      print "- **风险等级：** 低"
      print "- **审查策略：** 单 Reviewer"
      print "- **文件所有权：** `src/RushCommand.java`"
      print "- **交付类型：** 独立任务"
      print "- **原子组理由：** 不适用（单任务可独立构建和验证）"
      print "- **独立验证：** `mvn -Dtest=RushCommandTest test`"
      print "- **并行实现：** 禁止"
      print "- **并行隔离证据：** 不适用（默认模式串行实现）"
      print "- **集成检查点：** 隔离 worktree 候选提交 -> 独立 Reviewer -> 人工批准应用候选差异 -> 将候选差异应用到当前工作区（保持未暂存） -> 人工批准当前分支提交 -> 当前分支本地提交"
      print ""
    }
    { print }
  ' "$good_plan" > "$duplicate_assignment_plan"
  sed 's/- \*\*前置依赖：\*\* 无/- **前置依赖：** U2/' "$good_plan" > "$invalid_dependency_plan"
  sed 's/- \*\*风险等级：\*\* 低/- **风险等级：** 高/' "$good_plan" > "$reviewer_mismatch_plan"
  sed 's/- \*\*并行实现：\*\* 禁止/- **并行实现：** 允许（任务文件互不重叠）/' \
    "$good_plan" > "$parallel_without_isolation_plan"
  sed '/- \*\*文件所有权：\*\*/d' "$good_plan" > "$missing_ownership_plan"
  sed 's/^### 集成单元 U1：/### 集成单元 X1：/' "$good_plan" > "$invalid_unit_id_plan"
  sed '/步骤 4：验证 GREEN/,/步骤 5：重构/{ /步骤 5：重构/!d; }' "$good_plan" > "$missing_green_plan"
  sed '/步骤 6：再验证/,/^## 集成单元与执行编排$/{ /^## 集成单元与执行编排$/!d; }' \
    "$good_plan" > "$missing_refactor_recheck_plan"
  awk '
    /^## 集成单元与执行编排$/ {
      print "- [ ] **步骤 7：提交**"
      print ""
      print "运行：`git commit -m '\''feat: task commit'\''`"
      print ""
      print "预期：任务级提交创建成功。"
      print ""
    }
    { print }
  ' "$good_plan" > "$task_level_commit_plan"
  sed 's/行覆盖率不低于 80%/行覆盖率不低于 70%/;s/分支覆盖率不低于 70%/分支覆盖率不低于 60%/' \
    "$good_plan" > "$weak_threshold_plan"
  awk '
    /步骤 3：最小实现/ { target_stage=1 }
    target_stage && /^```java$/ { in_target_code=1; print; next }
    target_stage && in_target_code && /^```$/ { in_target_code=0; target_stage=0; print; next }
    target_stage && in_target_code { next }
    { print }
  ' "$good_plan" > "$empty_implementation_plan"
  awk '
    /步骤 2：验证 RED/ { target_stage=1 }
    target_stage && /^运行：/ { print "运行："; next }
    target_stage && /^预期：/ { print "预期："; target_stage=0; next }
    { print }
  ' "$good_plan" > "$empty_red_command_plan"
  awk '
    /^### 任务1-/ {
      print
      print ""
      print "任务类型：非行为（仅校验文档格式）。"
      print ""
      print "**文件：**"
      print "- 修改：`docs/rush-order.md`"
      print ""
      print "等价验证命令："
      print ""
      print "等价验证预期："
      print ""
      print "```text"
      print "加急工单文档格式"
      print "```"
      skip_task=1
      next
    }
    skip_task && /^## 集成单元与执行编排$/ { skip_task=0 }
    !skip_task { print }
  ' "$good_plan" > "$empty_equivalent_plan"
  awk '
    /步骤 3：最小实现/ { target_stage=1 }
    target_stage && /^```java$/ { in_target_code=1; next }
    target_stage && in_target_code && /^```$/ {
      print "| 文件 | 精确变更 |"
      print "|---|---|"
      print "| `src/RushCommand.java` | 新增 `isRush()` 并固定返回 `true` |"
      in_target_code=0
      target_stage=0
      next
    }
    target_stage && in_target_code { next }
    { print }
  ' "$good_plan" > "$table_implementation_plan"
  sed -e 's/^## 需求到任务追溯$/## 临时章节/' \
    -e 's/^## 跨层验收矩阵$/## 需求到任务追溯/' \
    -e 's/^## 临时章节$/## 跨层验收矩阵/' \
    "$good_plan" > "$reordered_sections_plan"
  sed '/^## 集成单元与执行编排$/,/^## 需求到任务追溯$/ {
    s/`任务1-实现加急命令`/`任务1-实现加急查询`/
  }' "$good_plan" > "$stale_unit_task_name_plan"
  awk '
    /^- \*\*包含任务：\*\*[[:space:]]*$/ {
      getline
      print "- **包含任务：** `任务1-实现加急命令`"
      next
    }
    { print }
  ' "$good_plan" > "$inline_unit_tasks_plan"
  awk '
    /^## 集成单元与执行编排$/ {
      print "### 任务2-补充加急命令文档"
      print ""
      print "任务类型：非行为（仅补充文档）。"
      print ""
      print "**文件：**"
      print "- 修改：`docs/rush-command.md`"
      print ""
      print "等价验证命令：`markdownlint docs/rush-command.md`"
      print ""
      print "等价验证预期：文档格式校验通过。"
      print ""
    }
    /^  - `任务1-实现加急命令`$/ {
      print
      print "  - `任务2-补充加急命令文档`"
      next
    }
    /^- \*\*文件所有权：\*\*/ {
      print "- **文件所有权：** `src/RushCommand.java`、`src/RushCommandTest.java`、`docs/rush-command.md`"
      next
    }
    /^- \*\*交付类型：\*\*/ {
      print "- **交付类型：** 原子任务组"
      next
    }
    /^- \*\*原子组理由：\*\*/ {
      print "- **原子组理由：** 命令行为与用法文档必须同步交付"
      next
    }
    { print }
  ' "$good_plan" > "$untraced_second_task_plan"
  sed '/^## 代码实现质量门禁$/,/^## 测试与覆盖率门禁$/ {
    s/`任务1-实现加急命令`/`任务1-实现加急查询`/
  }' "$good_plan" > "$stale_quality_reference_plan"
  sed 's/^### 任务1-实现加急命令$/### 任务1-实现加急命令-已完成/' \
    "$good_plan" > "$invalid_task_name_plan"
  awk '
    /^## 跨层验收矩阵$/ {
      print
      print ""
      print "不适用（本次仅修改单层文档格式，不涉及跨层边界）"
      skip_cross=1
      next
    }
    skip_cross && /^## 代码实现质量门禁$/ { skip_cross=0 }
    !skip_cross { print }
  ' "$good_plan" > "$cross_not_applicable_plan"
  sed '/^\*\*Plan 路径：\*\*/d' "$good_plan" > "$missing_handoff_path_plan"
  sed 's/| 功能完整性 | 加急行为与兼容边界均有实现和验收 |/| 功能完整性 | |/' \
    "$good_plan" > "$empty_quality_conclusion_plan"
  sed 's/| R1 | 新增加急状态表达 | `任务1-实现加急命令` |/| R1 | 新增加急状态表达 | `任务1-实现加急命令`、任务1 |/' \
    "$good_plan" > "$mixed_task_reference_plan"
  sed 's/| R1 | 新增加急状态表达 | `任务1-实现加急命令` |/| R1 | 新增加急状态表达 `任务1-实现加急命令` | |/' \
    "$good_plan" > "$misplaced_trace_reference_plan"
  awk '
    /^\| R1 \|/ {
      print
      print "| R2 | 补充加急命令交付文档 | `任务2-补充加急命令文档` | 文档格式校验通过 |"
      next
    }
    { print }
  ' "$untraced_second_task_plan" > "$atomic_group_plan"
  sed -e 's/- \*\*交付类型：\*\* 原子任务组/- **交付类型：** 独立任务/' \
    -e 's/- \*\*原子组理由：\*\* 命令行为与用法文档必须同步交付/- **原子组理由：** 不适用（任务可独立构建和验证）/' \
    "$atomic_group_plan" > "$multi_task_independent_plan"
  sed -e 's/- \*\*交付类型：\*\* 独立任务/- **交付类型：** 原子任务组/' \
    -e 's/- \*\*原子组理由：\*\* 不适用（单任务可独立构建和验证）/- **原子组理由：** 命令行为必须原子交付/' \
    "$good_plan" > "$single_task_atomic_plan"
  sed -e 's/等价验证命令：$/等价验证命令：`markdownlint docs\/rush-order.md`/' \
    -e 's/等价验证预期：$/等价验证预期：文档格式校验通过。/' \
    -e '/^```text$/,/^```$/d' \
    "$empty_equivalent_plan" > "$non_behavior_plan"
  cp "$good_plan" "$legacy_plan"
  cp "$good_plan" "$mismatched_topic_plan"
  cp "$good_plan" "$missing_plan_suffix"

  cat > "$auditless_plan" <<'EOF'
# Auditless Work Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `pretty-executing-plan`.
> REQUIRED quality skills: `superpowers:test-driven-development`,
> `clean-code-guard`, and `superpowers:verification-before-completion`.

### Task 1: Add Java service

**Files:**
- Create: `src/RushService.java`
- Test: `src/RushServiceTest.java`

- [ ] **Step 1: Write failing test**

```java
assertTrue(service.isRush());
```

Run: `mvn -Dtest=RushServiceTest test`

Expected: FAIL because `RushService` is missing.
EOF

  for self_test_plan in "$fixture_dir"/*-plan.md; do
    self_test_file_name=${self_test_plan##*/}
    sed "s#docs/pretty/rush-order/2026-08-23-rush-order-plan.md#docs/pretty/rush-order/$self_test_file_name#" \
      "$self_test_plan" > "$self_test_plan.synced"
    mv "$self_test_plan.synced" "$self_test_plan"
  done

  if "$0" "$bad_plan" >/dev/null 2>&1; then
    echo "自测失败：无效计划被错误接受" >&2
    return 1
  fi

  if "$0" "$auditless_plan" >/dev/null 2>&1; then
    echo "自测失败：缺少计划生成质量审查的计划被错误接受" >&2
    return 1
  fi

  if "$0" "$english_plan" >/dev/null 2>&1; then
    echo "自测失败：英文模板计划被错误接受" >&2
    return 1
  fi

  if "$0" "$coverage_less_plan" >/dev/null 2>&1; then
    echo "自测失败：缺少覆盖率门禁的计划被错误接受" >&2
    return 1
  fi

  if "$0" "$threshold_less_plan" >/dev/null 2>&1; then
    echo "自测失败：缺少覆盖率阈值的计划被错误接受" >&2
    return 1
  fi

  if "$0" "$command_less_plan" >/dev/null 2>&1; then
    echo "自测失败：缺少覆盖率命令或报告的计划被错误接受" >&2
    return 1
  fi

  if "$0" "$exclusion_less_plan" >/dev/null 2>&1; then
    echo "自测失败：缺少覆盖率排除项或理由的计划被错误接受" >&2
    return 1
  fi

  if "$0" "$implementation_quality_less_plan" >/dev/null 2>&1; then
    echo "自测失败：缺少代码实现质量门禁的计划被错误接受" >&2
    return 1
  fi

  if "$0" "$mixed_label_plan" >/dev/null 2>&1; then
    echo "自测失败：包含英文模板标签的中文计划被错误接受" >&2
    return 1
  fi

  for invalid_contract_plan in "$legacy_format_plan" "$missing_orchestration_plan" \
    "$duplicate_assignment_plan" "$reordered_sections_plan" "$stale_unit_task_name_plan" \
    "$inline_unit_tasks_plan" "$untraced_second_task_plan" "$stale_quality_reference_plan" \
    "$invalid_task_name_plan" "$missing_handoff_path_plan" "$empty_quality_conclusion_plan" \
    "$mixed_task_reference_plan" "$misplaced_trace_reference_plan" \
    "$multi_task_independent_plan" "$single_task_atomic_plan" \
    "$invalid_dependency_plan" "$reviewer_mismatch_plan" \
    "$parallel_without_isolation_plan" "$missing_ownership_plan" "$invalid_unit_id_plan" \
    "$task_level_commit_plan"; do
    if "$0" "$invalid_contract_plan" >/dev/null 2>&1; then
      echo "自测失败：无效执行编排合同被错误接受：$invalid_contract_plan" >&2
      return 1
    fi
  done

  for incomplete_tdd_plan in "$missing_green_plan" "$missing_refactor_recheck_plan" \
    "$empty_implementation_plan" "$empty_red_command_plan"; do
    if "$0" "$incomplete_tdd_plan" >/dev/null 2>&1; then
      echo "自测失败：行为任务缺少完整 TDD 阶段却被接受：$incomplete_tdd_plan" >&2
      return 1
    fi
  done
  if "$0" "$empty_equivalent_plan" >/dev/null 2>&1; then
    echo "自测失败：非行为任务的空等价验证被错误接受" >&2
    return 1
  fi
  if "$0" "$weak_threshold_plan" >/dev/null 2>&1; then
    echo "自测失败：低于默认覆盖率阈值的计划被接受" >&2
    return 1
  fi

  if "$0" "$legacy_plan" >/dev/null 2>&1; then
    echo "自测失败：旧 docs/superpowers Plan 路径被错误接受" >&2
    return 1
  fi

  if "$0" "$mismatched_topic_plan" >/dev/null 2>&1; then
    echo "自测失败：目录与文件名 topic 不一致的 Plan 被错误接受" >&2
    return 1
  fi

  if "$0" "$missing_plan_suffix" >/dev/null 2>&1; then
    echo "自测失败：缺少 -plan.md 后缀的 Plan 被错误接受" >&2
    return 1
  fi

  for valid_plan in "$good_plan" "$table_implementation_plan" "$cross_not_applicable_plan" \
    "$atomic_group_plan" "$non_behavior_plan"; do
    if ! "$0" "$valid_plan" >/dev/null; then
      echo "自测失败：有效计划被错误拒绝：$valid_plan" >&2
      return 1
    fi
  done

  echo "自测通过：正反例均符合预期"
}

if [ "$#" -eq 1 ] && [ "$1" = "--self-test" ]; then
  run_self_test
  exit $?
fi

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

plan_file=$1
if [ ! -f "$plan_file" ]; then
  echo "错误：计划文件不存在：$plan_file" >&2
  exit 2
fi

if ! validate_plan_path "$plan_file"; then
  echo "错误：Plan 路径必须匹配 docs/pretty/<topic>/YYYY-MM-DD-<topic>-plan.md，且两个 <topic> 必须是相同的小写 kebab-case" >&2
  exit 1
fi

failures=0

if ! validate_document_contract "$plan_file"; then
  failures=$((failures + 1))
fi

if ! validate_handoff_contract "$plan_file"; then
  failures=$((failures + 1))
fi

if ! validate_orchestration_contract "$plan_file"; then
  failures=$((failures + 1))
fi

if ! validate_review_references "$plan_file"; then
  failures=$((failures + 1))
fi

if ! validate_task_tdd_cycles "$plan_file"; then
  failures=$((failures + 1))
fi

require_pattern() {
  pattern=$1
  message=$2
  if ! grep -Eiq -- "$pattern" "$plan_file"; then
    echo "错误：$message" >&2
    failures=$((failures + 1))
  fi
}

reject_pattern() {
  pattern=$1
  message=$2
  if grep -Eiq -- "$pattern" "$plan_file"; then
    echo "错误：$message" >&2
    failures=$((failures + 1))
  fi
}

require_pattern '^# .+实施计划$' '缺少中文实施计划标题'
require_pattern 'REQUIRED (SUB-)?SKILL' '缺少必需 Skill 声明'
require_pattern 'pretty-executing-plan' '缺少项目执行质量 Skill'
require_pattern 'superpowers:test-driven-development' '缺少 TDD 要求'
require_pattern 'clean-code-guard' '缺少集成单元级代码质量审查'
require_pattern 'superpowers:verification-before-completion' '缺少完成前验证 Skill'
require_pattern '^### 实际使用的计划生成 Skill$' '缺少实际使用的计划生成 Skill 证据'
require_pattern '^### 质量发现与计划修正$' '缺少质量发现及计划修正'
require_pattern '^### 最终审查结论$' '缺少计划生成最终审查结论'
require_pattern '^### 任务级验证$' '缺少任务级验证章节'
require_pattern '^### 集成单元级验证$' '缺少集成单元级验证章节'
require_pattern '^### 最终覆盖率与全量回归$' '缺少最终覆盖率与全量回归章节'
require_pattern '覆盖率范围' '缺少覆盖率统计范围'
require_pattern '排除项及理由' '缺少覆盖率排除项及理由'
require_pattern '覆盖率指标' '缺少覆盖率指标'
require_pattern '行覆盖率' '缺少行覆盖率要求'
require_pattern '分支覆盖率' '缺少分支覆盖率要求'
require_pattern '覆盖率阈值' '缺少覆盖率阈值说明'
require_pattern '行覆盖率.*(>=|≥|不低于)[[:space:]]*(8[0-9]|9[0-9]|100)%' '缺少 80%–100% 的行覆盖率阈值'
require_pattern '分支覆盖率.*(>=|≥|不低于)[[:space:]]*(7[0-9]|8[0-9]|9[0-9]|100)%' '缺少 70%–100% 的分支覆盖率阈值'
require_pattern '覆盖率命令' '缺少覆盖率命令说明'
require_pattern '(jacoco|coverage|coverlet|nyc|istanbul|pytest-cov|--cov|lcov|gcov)' '缺少真实覆盖率工具命令'
require_pattern '报告位置' '缺少覆盖率报告位置'
require_pattern '成功预期' '缺少覆盖率成功预期'
require_pattern '失败判定' '缺少覆盖率失败判定'
require_pattern '^- \[ \]' '缺少可执行复选步骤'
require_pattern '运行[：:]' '缺少精确验证命令'
require_pattern '预期[：:]' '缺少预期验证结果'

reject_pattern '(^|[^[:alnum:]_])(TODO|TBD)([^[:alnum:]_]|$)' '包含 TODO 或 TBD 占位符'
reject_pattern 'implement later|fill in (the )?details|similar(ly)? to task|similar changes|add appropriate|handle edge cases|write tests for the above' '包含模糊实施占位说明'
reject_pattern '(^|[[:space:]])\.\.\.([[:space:]]|$)|…' '包含占位省略号；必须列全所需内容'
reject_pattern '^## 执行编排合同$|^## 最终覆盖率与全量回归门禁$|^### 任务 [0-9]+：|^- \*\*包含任务：\*\*.+|未使用的候选 Skill 及原因' '包含必须显式迁移的旧 Plan 结构'
reject_pattern 'git merge --ff-only|ff-only 合并' '仍使用旧的 ff-only 当前分支集成合同'
reject_pattern '等待合并批准|合并批准：|合并前 HEAD：|合并后 HEAD：|合并命令：' '仍使用旧的当前分支合并批准合同'
reject_pattern '^- \[ \] \*\*步骤 [0-9]+：提交\*\*|git commit([[:space:]]|$)' '任务正文不得包含提交步骤；提交只由集成单元检查点产生'
reject_pattern '^# .+ Implementation Plan$|^## Plan-generation quality review$|^### Task[[:space:]]|^- \[ \] \*\*Step[[:space:]]|^(\*\*)?(Goal|Architecture|Tech Stack|Files|Run|Expected):|^> \*\*For agentic workers' '包含英文计划模板标签'

if [ "$failures" -ne 0 ]; then
  echo "失败：$failures 项机械计划质量检查未通过" >&2
  exit 1
fi

echo "通过：机械计划质量门禁已满足"
