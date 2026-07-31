#!/usr/bin/env bash

set -u

usage() {
  echo "Usage: validate-execution.sh <execution-report> [--require-complete] | --self-test" >&2
}

validate_execution_path() {
  report_file=$1
  case "$report_file" in
    docs/pretty/*/*) relative_path=${report_file#docs/pretty/} ;;
    */docs/pretty/*/*) relative_path=${report_file#*/docs/pretty/} ;;
    *) return 1 ;;
  esac

  topic=${relative_path%%/*}
  file_name=${relative_path#*/}
  if [ "$file_name" = "$relative_path" ] || printf '%s\n' "$file_name" | grep -Fq '/'; then
    return 1
  fi
  if ! printf '%s\n' "$topic" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$'; then
    return 1
  fi
  printf '%s\n' "$file_name" | grep -Eq "^[0-9]{4}-[0-9]{2}-[0-9]{2}-${topic}-execution\\.md$"
}

report_root_for() {
  report_path=$1
  case "$report_path" in
    docs/pretty/*) printf '%s\n' '.' ;;
    */docs/pretty/*) printf '%s\n' "${report_path%%/docs/pretty/*}" ;;
    *) return 1 ;;
  esac
}

validate_plan_readonly_contract() {
  contract_report=$1
  contract_root=$(report_root_for "$contract_report") || {
    echo 'ERROR: 无法根据 Execution Report 路径定位仓库根目录' >&2
    return 1
  }
  contract_plan_path=$(awk -F'`' 'index($0, "Plan 路径：`") { print $2; exit }' "$contract_report")
  if [ -z "$contract_plan_path" ]; then
    echo 'ERROR: Plan 路径必须使用反引号包裹，才能校验当前文件哈希' >&2
    return 1
  fi

  case "$contract_plan_path" in
    /*) contract_plan_file=$contract_plan_path ;;
    *) contract_plan_file="$contract_root/$contract_plan_path" ;;
  esac
  if [ ! -f "$contract_plan_file" ]; then
    echo "ERROR: Plan 文件不存在，无法校验只读合同：$contract_plan_file" >&2
    return 1
  fi

  contract_current_hash=$(git hash-object -- "$contract_plan_file") || {
    echo "ERROR: 无法计算 Plan 当前哈希：$contract_plan_file" >&2
    return 1
  }

  awk -v current_plan_hash="$contract_current_hash" '
    function fail(message) {
      print "ERROR: " message > "/dev/stderr"
      failures++
    }

    function parse_hash(line, prefix, value) {
      value = line
      sub("^[[:space:]]*" prefix "[[:space:]]*", "", value)
      gsub("`", "", value)
      sub("[。.][[:space:]]*$", "", value)
      sub("[[:space:]]*$", "", value)
      return value
    }

    function valid_hash(value) {
      return (length(value) == 40 || length(value) == 64) && value !~ /[^0-9a-f]/
    }

    function close_task() {
      if (!in_task) {
        return
      }
      if (!task_hash_seen) {
        fail(task_label " 缺少 Plan 只读复验哈希")
      }
      if (!task_result_seen) {
        fail(task_label " 缺少 Plan 只读复验结论")
      }
      if (task_hash_seen && task_result_seen && task_hash_valid) {
        if (task_hash == batch_hash) {
          if (task_result != "通过") {
            fail(task_label " 的哈希未变化，但 Plan 只读复验结论不是通过")
          }
        } else {
          if (task_result !~ /^失败（[^）]+）$/) {
            fail(task_label " 的哈希与批次基线不一致，但未记录带理由的失败结论")
          }
          batch_plan_mismatch = 1
          batch_plan_mismatch_task = task_label
        }
      }
      in_task = 0
    }

    function close_batch() {
      if (batch_count == 0) {
        return
      }
      if (batch_task_count == 0) {
        fail("执行批次 " batch_count " 没有任务证据")
      }
      if (batch_result_count != 1) {
        fail("执行批次 " batch_count " 必须且只能记录一次批次结论")
      }
      if (batch_approval_count != 1) {
        fail("执行批次 " batch_count " 必须且只能记录一次 Plan 批次批准")
      }
      if (existing_results_review_count != 1) {
        fail("执行批次 " batch_count " 必须且只能记录一次既有成果复核")
      }
      if (batch_count == 1) {
        if (batch_approval !~ /^首次批准（[^）]+）$/) {
          fail("首次执行批次必须记录带证据的首次批准")
        }
        if (existing_results_review !~ /^不适用（[^）]+）$/) {
          fail("首次执行批次的既有成果复核必须记录带理由的不适用")
        }
      } else if (batch_requires_reapproval) {
        if (batch_approval !~ /^重新批准（[^）]+）$/) {
          fail("Plan 变化后的恢复批次必须记录带证据的重新批准")
        }
        if (existing_results_review !~ /^通过（[^）]+）$/) {
          fail("Plan 变化后的恢复批次必须记录带证据的既有成果复核通过")
        }
      } else {
        if (batch_approval !~ /^沿用批准（[^）]+）$/) {
          fail("Plan 未变化的后续执行批次必须记录沿用批准及其证据")
        }
        if (existing_results_review !~ /^通过（[^）]+）$/) {
          fail("后续执行批次必须记录带证据的既有成果复核通过")
        }
      }
      if (batch_plan_mismatch) {
        if (batch_result !~ /^阻塞（[^）]+）$/) {
          fail("执行批次 " batch_count " 检测到 Plan 变化，但批次结论不是带理由的阻塞")
        }
        last_closed_batch_blocked = 1
        last_closed_batch_requires_reapproval = 1
      } else if (batch_result ~ /^阻塞（[^）]+）$/) {
        last_closed_batch_blocked = 1
        last_closed_batch_requires_reapproval = 0
      } else {
        if (batch_result != "通过") {
          fail("执行批次 " batch_count " 的批次结论必须是通过或带理由的阻塞")
        }
        last_closed_batch_blocked = 0
        last_closed_batch_requires_reapproval = 0
      }
    }

    /^[[:space:]]*### 执行批次 / {
      close_task()
      close_batch()
      batch_count++
      batch_requires_reapproval = last_closed_batch_requires_reapproval
      batch_hash = ""
      batch_hash_count = 0
      batch_approval_count = 0
      batch_approval = ""
      existing_results_review_count = 0
      existing_results_review = ""
      batch_task_count = 0
      batch_plan_mismatch = 0
      batch_plan_mismatch_task = ""
      batch_result_count = 0
      batch_result = ""
      next
    }

    /^[[:space:]]*Plan 批次基线哈希：/ {
      if (batch_count == 0) {
        fail("Plan 批次基线哈希必须位于执行批次标题之后")
        next
      }
      batch_hash_count++
      batch_hash = parse_hash($0, "Plan 批次基线哈希：")
      if (batch_hash_count > 1) {
        fail("执行批次 " batch_count " 存在多个 Plan 批次基线哈希")
      }
      if (!valid_hash(batch_hash)) {
        fail("执行批次 " batch_count " 的 Plan 批次基线哈希格式无效")
      }
      last_batch_hash = batch_hash
      next
    }

    /^[[:space:]]*Plan 批次批准：/ {
      if (batch_count == 0) {
        fail("Plan 批次批准必须记录在具体执行批次中")
        next
      }
      batch_approval_count++
      batch_approval = $0
      sub("^[[:space:]]*Plan 批次批准：[[:space:]]*", "", batch_approval)
      sub("[。.][[:space:]]*$", "", batch_approval)
      sub("[[:space:]]*$", "", batch_approval)
      next
    }

    /^[[:space:]]*既有成果复核：/ {
      if (batch_count == 0) {
        fail("既有成果复核必须记录在具体执行批次中")
        next
      }
      existing_results_review_count++
      existing_results_review = $0
      sub("^[[:space:]]*既有成果复核：[[:space:]]*", "", existing_results_review)
      sub("[。.][[:space:]]*$", "", existing_results_review)
      sub("[[:space:]]*$", "", existing_results_review)
      next
    }

    /^[[:space:]]*### 任务 / {
      close_task()
      if (batch_plan_mismatch) {
        fail("Plan 变化后仍在同一执行批次开始后续任务：" $0)
      }
      task_label = $0
      task_count++
      batch_task_count++
      if (batch_count == 0) {
        fail(task_label " 未归属任何执行批次")
      }
      if (batch_hash == "") {
        fail(task_label " 开始前缺少当前 Plan 批次基线哈希")
      }
      if (batch_approval_count == 0) {
        fail(task_label " 开始前缺少当前执行批次的批准记录")
      }
      if (existing_results_review_count == 0) {
        fail(task_label " 开始前缺少既有成果复核")
      }
      in_task = 1
      task_hash_seen = 0
      task_hash_count = 0
      task_hash_valid = 0
      task_result_seen = 0
      task_result_count = 0
      task_result = ""
      next
    }

    /^[[:space:]]*Plan 只读复验哈希：/ {
      if (!in_task) {
        fail("Plan 只读复验哈希必须记录在具体任务下")
        next
      }
      task_hash_seen = 1
      task_hash_count++
      if (task_hash_count > 1) {
        fail(task_label " 存在多个 Plan 只读复验哈希")
      }
      task_hash = parse_hash($0, "Plan 只读复验哈希：")
      if (!valid_hash(task_hash)) {
        fail(task_label " 的 Plan 只读复验哈希格式无效")
        task_hash_valid = 0
      } else {
        task_hash_valid = 1
      }
      next
    }

    /^[[:space:]]*Plan 只读复验结论：/ {
      if (!in_task) {
        fail("Plan 只读复验结论必须记录在具体任务下")
        next
      }
      task_result_seen = 1
      task_result_count++
      if (task_result_count > 1) {
        fail(task_label " 存在多个 Plan 只读复验结论")
      }
      task_result = $0
      sub("^[[:space:]]*Plan 只读复验结论：[[:space:]]*", "", task_result)
      sub("[。.][[:space:]]*$", "", task_result)
      sub("[[:space:]]*$", "", task_result)
      next
    }

    /^[[:space:]]*批次结论：/ {
      if (batch_count == 0) {
        fail("批次结论必须记录在具体执行批次中")
        next
      }
      batch_result_count++
      batch_result = $0
      sub("^[[:space:]]*批次结论：[[:space:]]*", "", batch_result)
      sub("[。.][[:space:]]*$", "", batch_result)
      sub("[[:space:]]*$", "", batch_result)
      next
    }

    /^[[:space:]]*Plan 最终哈希：/ {
      final_hash_count++
      final_hash = parse_hash($0, "Plan 最终哈希：")
      if (final_hash_count > 1) {
        fail("报告存在多个 Plan 最终哈希")
      }
      if (!valid_hash(final_hash)) {
        fail("Plan 最终哈希格式无效")
      }
      next
    }

    /^[[:space:]]*Plan 只读校验：/ {
      final_result_count++
      final_result = $0
      sub("^[[:space:]]*Plan 只读校验：[[:space:]]*", "", final_result)
      sub("[。.][[:space:]]*$", "", final_result)
      sub("[[:space:]]*$", "", final_result)
      next
    }

    END {
      close_task()
      close_batch()
      if (batch_count == 0) {
        fail("缺少执行批次标题和 Plan 批次基线哈希")
      }
      if (task_count == 0) {
        fail("缺少可执行任务及其 Plan 只读复验")
      }
      if (last_closed_batch_blocked) {
        fail("最后一个执行批次仍处于阻塞，缺少后续恢复并完成的批次")
      }
      if (final_hash_count == 0) {
        fail("缺少 Plan 最终哈希")
      } else {
        if (final_hash != last_batch_hash) {
          fail("Plan 最终哈希与最后一个批准批次的基线哈希不一致")
        }
        if (final_hash != current_plan_hash) {
          fail("Plan 最终哈希与校验时 Plan 文件的实际哈希不一致")
        }
      }
      if (final_result_count != 1 || final_result != "通过") {
        fail("Plan 只读校验必须且只能记录一次通过")
      }
      exit failures > 0 ? 1 : 0
    }
  ' "$contract_report"
}

validate_worktree_contract() {
  worktree_report=$1
  report_worktree_root=$(report_root_for "$worktree_report") || {
    echo 'ERROR: 无法根据 Execution Report 路径定位报告所在 Worktree 根目录' >&2
    return 1
  }
  worktree_path=$(awk -F'`' 'index($0, "Worktree 路径：`") { print $2; exit }' "$worktree_report")
  if [ -z "$worktree_path" ]; then
    if grep -Eq 'Worktree 路径：不适用（[^）]+）' "$worktree_report"; then
      return 0
    fi
    echo 'ERROR: Worktree 路径为空或格式无效' >&2
    return 1
  fi

  case "$worktree_path" in
    .worktrees/*|*/.worktrees/*) ;;
    *) return 0 ;;
  esac

  ignore_owner_path=$(awk -F'`' 'index($0, "主工作区路径：`") { print $2; exit }' "$worktree_report")
  if [ -z "$ignore_owner_path" ]; then
    echo 'ERROR: 项目内 Worktree 必须记录承载 .worktrees/ 的主工作区路径' >&2
    return 1
  fi
  case "$ignore_owner_path" in
    /*) ignore_owner_resolved=$ignore_owner_path ;;
    *) ignore_owner_resolved="$report_worktree_root/$ignore_owner_path" ;;
  esac
  ignore_owner_absolute=$(cd "$ignore_owner_resolved" 2>/dev/null && pwd -P) || {
    echo "ERROR: 主工作区路径不存在：$ignore_owner_resolved" >&2
    return 1
  }
  if [ ! -f "$ignore_owner_absolute/.gitignore" ] || \
    ! grep -Fxq '/.worktrees/' "$ignore_owner_absolute/.gitignore"; then
    echo 'ERROR: 项目内 Worktree 缺少仓库根 .gitignore 精确规则 /.worktrees/' >&2
    return 1
  fi
  if ! git -C "$ignore_owner_absolute" check-ignore -q .worktrees/; then
    echo 'ERROR: git check-ignore -q .worktrees/ 未通过' >&2
    return 1
  fi
  if ! grep -Eq 'Worktree 忽略检查：通过' "$worktree_report"; then
    echo 'ERROR: 项目内 Worktree 必须记录忽略检查通过' >&2
    return 1
  fi
  return 0
}

validate_control_contract() {
  control_report=$1
  control_completion_mode=${2:-structure}
  awk -v completion_mode="$control_completion_mode" '
    function fail(message) {
      print "ERROR: " message > "/dev/stderr"
      failures++
    }

    function normalize(line, prefix, value) {
      value = line
      sub("^[[:space:]]*" prefix "[[:space:]]*", "", value)
      sub(/[。.][[:space:]]*$/, "", value)
      sub(/^[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      return value
    }

    function known_state(state) {
      return state == "未开始" || state == "执行中" || state == "等待 Review" ||
        state == "等待当前分支提交批准" || state == "最终验证中" || state == "安全暂停" ||
        state == "立即中断" || state == "已取消" || state == "阻塞" || state == "已完成"
    }

    function stoppable_target(target) {
      return target == "安全暂停" || target == "立即中断" || target == "已取消" || target == "阻塞"
    }

    function legal_transition(from, to) {
      if (from == "未开始") {
        return to == "执行中" || stoppable_target(to)
      }
      if (from == "执行中") {
        return to == "等待 Review" || stoppable_target(to)
      }
      if (from == "等待 Review") {
        return to == "等待当前分支提交批准" || to == "执行中" || stoppable_target(to)
      }
      if (from == "等待当前分支提交批准") {
        return to == "执行中" || to == "最终验证中" || stoppable_target(to)
      }
      if (from == "最终验证中") {
        return to == "已完成" || stoppable_target(to)
      }
      if (from == "安全暂停" || from == "立即中断" || from == "阻塞") {
        return to == "执行中" || to == "等待 Review" || to == "等待当前分支提交批准" ||
          to == "最终验证中" || to == "已取消" || to == "阻塞"
      }
      return 0
    }

    /^执行模式：/ {
      mode_count++
      mode = normalize($0, "执行模式：")
      next
    }

    /^当前状态：/ {
      current_count++
      current_state = normalize($0, "当前状态：")
      next
    }

    /^自动编排状态：/ {
      orchestrator_count++
      orchestrator = normalize($0, "自动编排状态：")
      next
    }

    /^状态转换：/ {
      transition = normalize($0, "状态转换：")
      separator = index(transition, " -> ")
      if (separator == 0) {
        fail("状态转换必须使用 <前状态> -> <后状态> 格式")
        next
      }
      from_state = substr(transition, 1, separator - 1)
      to_state = substr(transition, separator + 4)
      if (!known_state(from_state) || !known_state(to_state)) {
        fail("状态转换包含未知状态：" transition)
      }
      if (transition_count == 0 && from_state != "未开始") {
        fail("首个控制事件必须从未开始状态开始")
      }
      if (transition_count > 0 && from_state != last_state) {
        fail("控制事件状态链断裂，期望前状态 " last_state "，实际为 " from_state)
      }
      if (!legal_transition(from_state, to_state)) {
        fail("非法状态转换：" transition)
      }
      transition_count++
      last_state = to_state
      next
    }

    /^最终结论：/ {
      final_count++
      final_result = normalize($0, "最终结论：")
      next
    }

    END {
      if (mode_count != 1 || (mode != "单集成单元审批" && mode != "一次性执行")) {
        fail("执行模式必须且只能是单集成单元审批或一次性执行")
      }
      if (current_count != 1 || !known_state(current_state)) {
        fail("当前状态必须且只能记录一个合法生命周期状态")
      }
      if (transition_count == 0) {
        fail("至少需要一个可恢复的控制事件")
      } else if (current_state != last_state) {
        fail("当前状态与最后一个控制事件不一致")
      }
      if (orchestrator_count != 1) {
        fail("自动编排状态必须且只能记录一次")
      } else if (current_state != "执行中" && current_state != "最终验证中" && orchestrator !~ /^停止（[^）]+）$/) {
        fail("等待、暂停、中断、取消、阻塞或完成状态必须停止自动编排")
      }
      if (final_count != 1) {
        fail("最终结论必须且只能记录一次")
      } else if (current_state == "已完成" && final_result != "完成") {
        fail("已完成状态必须对应最终结论完成")
      } else if (current_state == "阻塞" && final_result != "阻塞") {
        fail("阻塞状态必须对应最终结论阻塞")
      } else if (current_state != "已完成" && current_state != "阻塞" && final_result != "未完成") {
        fail("非终态、暂停、中断或取消状态必须对应最终结论未完成")
      }
      if (completion_mode == "complete" && current_state != "已完成") {
        fail("完整交付要求当前状态为已完成")
      }
      exit failures > 0 ? 1 : 0
    }
  ' "$control_report"
}

validate_main_workspace_state() {
  workspace_root=$1
  workspace_status=$(git -C "$workspace_root" status --porcelain) || return 1
  if [ -z "$workspace_status" ]; then
    return 0
  fi

  if [ "$workspace_status" != ' M .gitignore' ] || \
    ! git -C "$workspace_root" diff --cached --quiet --exit-code; then
    return 1
  fi
  ignore_numstat=$(git -C "$workspace_root" diff --numstat -- .gitignore) || return 1
  if [ "$ignore_numstat" != "$(printf '1\t0\t.gitignore')" ]; then
    return 1
  fi
  [ "$(git -C "$workspace_root" diff -- .gitignore | grep -Ec '^\+/.worktrees/$')" -eq 1 ]
}

working_tree_tree_except_gitignore() {
  workspace_root=$1
  reference_commit=$2
  temporary_index=$(mktemp "${TMPDIR:-/tmp}/pretty-execution-index.XXXXXX") || return 1
  tree_result=''
  if GIT_INDEX_FILE="$temporary_index" git -C "$workspace_root" read-tree "$reference_commit" &&
    GIT_INDEX_FILE="$temporary_index" git -C "$workspace_root" add -A -- . ':(exclude).gitignore' &&
    tree_result=$(GIT_INDEX_FILE="$temporary_index" git -C "$workspace_root" write-tree); then
    rm -f -- "$temporary_index"
    printf '%s\n' "$tree_result"
    return 0
  fi
  rm -f -- "$temporary_index"
  return 1
}

validate_pending_workspace_contract() {
  pending_report=$1
  pending_root=$(report_root_for "$pending_report") || return 1
  pending_worktree_path=$(awk -F'`' 'index($0, "主工作区路径：`") { print $2; exit }' "$pending_report")
  pending_branch=$(awk -F'`' 'index($0, "主分支：`") { print $2; exit }' "$pending_report")
  pending_expected_head=$(awk -F'`' 'index($0, "预期主分支 HEAD：`") { print $2; exit }' "$pending_report")
  pending_candidate=$(awk -F'`' 'index($0, "任务候选提交：`") { print $2; exit }' "$pending_report")
  pending_candidate_tree=$(awk -F'`' 'index($0, "任务候选树：`") { print $2; exit }' "$pending_report")
  pending_approval_tree=$(awk -F'`' 'index($0, "批准内容指纹：`") { print $2; exit }' "$pending_report")
  pending_apply_command=$(awk -F'`' 'index($0, "候选差异应用命令：`") { print $2; exit }' "$pending_report")
  pending_apply_exit=$(awk '/^候选差异应用退出码：/ { value=$0; sub(/^候选差异应用退出码：/, "", value); sub(/[。.][[:space:]]*$/, "", value); print value; exit }' "$pending_report")
  pending_apply_before=$(awk -F'`' 'index($0, "候选差异应用前 HEAD：`") { print $2; exit }' "$pending_report")
  pending_apply_after=$(awk -F'`' 'index($0, "候选差异应用后 HEAD：`") { print $2; exit }' "$pending_report")
  pending_apply_result=$(awk '/^候选差异应用结论：/ { value=$0; sub(/^候选差异应用结论：/, "", value); sub(/[。.][[:space:]]*$/, "", value); print value; exit }' "$pending_report")
  pending_commit_message=$(awk -F'`' 'index($0, "当前分支提交信息：`") { print $2; exit }' "$pending_report")
  if [ -z "$pending_worktree_path" ] || [ -z "$pending_branch" ] || [ -z "$pending_expected_head" ] ||
    [ -z "$pending_candidate" ] || [ -z "$pending_candidate_tree" ] || [ -z "$pending_approval_tree" ] ||
    [ -z "$pending_apply_command" ] || [ -z "$pending_apply_before" ] || [ -z "$pending_apply_after" ] ||
    [ -z "$pending_commit_message" ]; then
    echo 'ERROR: 等待当前分支提交批准的报告缺少工作区、HEAD、候选、差异应用或拟用提交证据' >&2
    return 1
  fi
  if [ "$pending_apply_exit" != '0' ] || [ "$pending_apply_result" != '通过' ] ||
    ! printf '%s\n' "$pending_apply_command" | grep -Eq 'git apply' ||
    printf '%s\n' "$pending_apply_command" | grep -Eq -- '--(index|cached|3way)' ||
    [ "$pending_apply_before" != "$pending_expected_head" ] ||
    [ "$pending_apply_after" != "$pending_expected_head" ]; then
    echo 'ERROR: 等待当前分支提交批准的差异应用证据无效或应用前后 HEAD 不一致' >&2
    return 1
  fi

  case "$pending_worktree_path" in
    /*) pending_worktree_resolved=$pending_worktree_path ;;
    *) pending_worktree_resolved="$pending_root/$pending_worktree_path" ;;
  esac
  pending_worktree_absolute=$(cd "$pending_worktree_resolved" 2>/dev/null && pwd -P) || return 1
  actual_pending_branch=$(git -C "$pending_worktree_absolute" branch --show-current) || return 1
  actual_pending_head=$(git -C "$pending_worktree_absolute" rev-parse HEAD) || return 1
  if [ "$actual_pending_branch" != "$pending_branch" ] || [ "$actual_pending_head" != "$pending_expected_head" ]; then
    echo 'ERROR: 等待当前分支提交批准时主分支或 HEAD 已漂移' >&2
    return 1
  fi
  if ! git -C "$pending_worktree_absolute" diff --cached --quiet --exit-code; then
    echo 'ERROR: 等待当前分支提交批准时实际索引包含暂存改动' >&2
    return 1
  fi
  pending_status=$(git -C "$pending_worktree_absolute" status --porcelain) || return 1
  if [ -z "$pending_status" ]; then
    echo 'ERROR: 等待当前分支提交批准时当前工作区没有候选未暂存差异' >&2
    return 1
  fi
  pending_gitignore_status=$(printf '%s\n' "$pending_status" | grep -E '(^| )\.gitignore$' || true)
  if [ -n "$pending_gitignore_status" ] && [ "$pending_gitignore_status" != ' M .gitignore' ]; then
    echo 'ERROR: 当前工作区的 .gitignore 状态超出未暂存 /.worktrees/ 单行例外' >&2
    return 1
  fi
  if ! git -C "$pending_worktree_absolute" cat-file -e "${pending_candidate}^{commit}" 2>/dev/null; then
    echo "ERROR: 等待当前分支提交批准时任务候选提交不存在：$pending_candidate" >&2
    return 1
  fi
  actual_pending_tree=$(git -C "$pending_worktree_absolute" rev-parse "${pending_candidate}^{tree}") || return 1
  if [ "$actual_pending_tree" != "$pending_candidate_tree" ] || [ "$pending_approval_tree" != "$pending_candidate_tree" ]; then
    echo 'ERROR: 候选树、批准内容指纹与候选提交实际树不一致' >&2
    return 1
  fi
  pending_working_tree=$(working_tree_tree_except_gitignore "$pending_worktree_absolute" "$pending_candidate") || return 1
  if [ "$pending_working_tree" != "$pending_candidate_tree" ]; then
    echo 'ERROR: 当前工作区未暂存差异不是候选提交的精确内容' >&2
    return 1
  fi
  if printf '%s\n' "$pending_status" | grep -q '^.M \.gitignore\|^ M \.gitignore'; then
    if [ "$(git -C "$pending_worktree_absolute" diff --numstat -- .gitignore)" != "$(printf '1\t0\t.gitignore')" ] ||
      [ "$(git -C "$pending_worktree_absolute" diff -- .gitignore | grep -Ec '^\+/.worktrees/$')" -ne 1 ]; then
      echo 'ERROR: 当前工作区的 .gitignore 改动超出 /.worktrees/ 单行例外' >&2
      return 1
    fi
  fi
  return 0
}

validate_integration_contract() {
  integration_report=$1
  integration_root=$(report_root_for "$integration_report") || {
    echo 'ERROR: 无法根据 Execution Report 路径定位集成证据根目录' >&2
    return 1
  }

  if ! awk '
    function fail(message) {
      print "ERROR: " message > "/dev/stderr"
      failures++
    }

    function value_after(line, prefix, value) {
      value = line
      sub("^[[:space:]]*" prefix "[[:space:]]*", "", value)
      sub(/[。.][[:space:]]*$/, "", value)
      sub(/^[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      return value
    }

    function hash_after(line, prefix, value) {
      value = value_after(line, prefix)
      gsub(/`/, "", value)
      return value
    }

    function valid_hash(value) {
      return (length(value) == 40 || length(value) == 64) && value !~ /[^0-9a-f]/
    }

    function close_unit() {
      if (unit_id == "") {
        return
      }
      if (risk_count != 1 || (risk != "低" && risk != "高")) {
        fail("集成单元 " unit_id " 必须声明低或高风险等级")
      }
      if (review_strategy_count != 1 || (review_strategy != "单 Reviewer" && review_strategy != "双 Reviewer")) {
        fail("集成单元 " unit_id " 必须声明单 Reviewer 或双 Reviewer")
      } else if (risk == "低" && review_strategy != "单 Reviewer") {
        fail("低风险集成单元 " unit_id " 必须使用单 Reviewer")
      } else if (risk == "高" && review_strategy != "双 Reviewer") {
        fail("高风险集成单元 " unit_id " 必须使用双 Reviewer")
      }
      if (base_count != 1 || !valid_hash(unit_base)) {
        fail("集成单元 " unit_id " 缺少有效单元基线提交")
      }
      if (candidate_count != 1 || !valid_hash(candidate)) {
        fail("集成单元 " unit_id " 缺少有效任务候选提交")
      }
      if (mapped_count != 1 || !valid_hash(mapped_commit)) {
        fail("集成单元 " unit_id " 缺少有效集成映射提交")
      }
      if (tree_count != 1 || !valid_hash(candidate_tree)) {
        fail("集成单元 " unit_id " 缺少有效任务候选树")
      }
      if (report_isolation_count != 1 || report_isolation !~ /^通过（[^）]+）$/) {
        fail("集成单元 " unit_id " 必须证明 Execution Report 未进入任务候选提交")
      }
      if (unified_review_count != 1) {
        fail("集成单元 " unit_id " 必须记录统一 Review 证据指纹或带理由的不适用")
      } else if (mode == "单集成单元审批" && unified_review !~ /^不适用（[^）]+）$/) {
        fail("默认模式的集成单元 " unit_id " 必须将统一 Review 证据指纹写为带理由的不适用")
      } else if (mode == "一次性执行" && !valid_hash(unified_review)) {
        fail("一次性模式的集成单元 " unit_id " 必须记录有效统一 Review 证据指纹")
      }
      if (plan_fingerprint_count != 1 || !valid_hash(plan_fingerprint) ||
          code_fingerprint_count != 1 || !valid_hash(code_fingerprint) ||
          command_fingerprint_count != 1 || !valid_hash(command_fingerprint) ||
          dependency_fingerprint_count != 1 || !valid_hash(dependency_fingerprint) ||
          environment_fingerprint_count != 1 || !valid_hash(environment_fingerprint)) {
        fail("集成单元 " unit_id " 必须记录 Plan、代码、命令、依赖和环境五项有效证据指纹")
      }
      if (evidence_disposition_count != 1 ||
          (evidence_disposition != "新鲜运行" && evidence_disposition !~ /^复用（[^）]+五项指纹匹配[^）]*）$/)) {
        fail("集成单元 " unit_id " 的验证证据处置必须是新鲜运行或带来源的五指纹复用")
      }
      if (reviewer1_count != 1 || reviewer1 !~ /^通过（[^）]+）$/) {
        fail("集成单元 " unit_id " 缺少 Reviewer 1 的带证据通过结论")
      }
      if (reviewer2_count != 1) {
        fail("集成单元 " unit_id " 必须记录 Reviewer 2 结论或带理由的不适用")
      } else if (risk == "高" && reviewer2 !~ /^通过（[^）]+）$/) {
        fail("高风险集成单元 " unit_id " 必须有第二位独立 Reviewer 通过")
      } else if (risk == "低" && reviewer2 !~ /^不适用（[^）]+）$/) {
        fail("低风险集成单元 " unit_id " 的 Reviewer 2 必须写带理由的不适用")
      }
      if (rejection_history_count != 1) {
        fail("集成单元 " unit_id " 必须保留 Review 驳回历史或明确写无")
      }
      if (apply_command_count != 1 || apply_command !~ /git apply/ || apply_command ~ /--(index|cached|3way)/) {
        fail("集成单元 " unit_id " 必须记录候选差异应用命令")
      }
      if (apply_exit_count != 1 || apply_exit != "0") {
        fail("集成单元 " unit_id " 的候选差异应用退出码必须为 0")
      }
      if (apply_before_count != 1 || !valid_hash(apply_before) ||
          apply_after_count != 1 || !valid_hash(apply_after) || apply_before != apply_after) {
        fail("集成单元 " unit_id " 的候选差异应用前后 HEAD 必须有效且保持不变")
      }
      if (apply_result_count != 1 || apply_result != "通过") {
        fail("集成单元 " unit_id " 的候选差异应用结论必须通过")
      }
      if (approval_fingerprint_count != 1 || !valid_hash(approval_fingerprint) ||
          (mode == "单集成单元审批" && approval_fingerprint != candidate_tree)) {
        fail("集成单元 " unit_id " 的批准内容指纹无效或未绑定候选/组合树")
      }
      if (commit_message_count != 1 || commit_message == "") {
        fail("集成单元 " unit_id " 必须记录当前分支提交信息")
      }
      if (approval_count != 1) {
        fail("集成单元 " unit_id " 必须且只能记录一次当前分支提交批准")
      } else if (mode == "单集成单元审批" && approval !~ /^已批准（[^）]+）$/) {
        fail("默认模式的集成单元 " unit_id " 必须记录逐单元人工当前分支提交批准")
      } else if (mode == "一次性执行" && approval !~ /^一次性当前分支提交已批准（[^）]+）$/) {
        fail("一次性模式必须记录最终统一当前分支提交批准")
      }
      if (commit_command_count != 1 || commit_command !~ /git commit/ ||
          commit_command ~ /--(no-verify|amend)/ || commit_command ~ /(^|[[:space:]])-n([[:space:]]|$)/) {
        fail("集成单元 " unit_id " 必须记录当前分支本地提交命令")
      }
      if (commit_exit_count != 1 || commit_exit != "0") {
        fail("集成单元 " unit_id " 的当前分支提交退出码必须为 0")
      }
      if (commit_before_count != 1 || !valid_hash(commit_before) ||
          commit_after_count != 1 || !valid_hash(commit_after) ||
          current_commit_count != 1 || !valid_hash(current_commit)) {
        fail("集成单元 " unit_id " 必须记录有效的当前分支提交前后 HEAD 和提交")
      }
      if (commit_after != current_commit) {
        fail("集成单元 " unit_id " 的当前分支提交后 HEAD 必须等于当前分支提交")
      }
      if (commit_result_count != 1 || commit_result != "通过") {
        fail("集成单元 " unit_id " 的当前分支提交结论必须通过")
      }
      if (duration_count != 1 || duration !~ /实现/ || duration !~ /验证/ || duration !~ /Review/ || duration !~ /应用/ || duration !~ /提交/) {
        fail("集成单元 " unit_id " 必须记录实现、验证、Review、差异应用和提交阶段耗时")
      }
      if (unit_result_count != 1 || unit_result != "通过") {
        fail("集成单元 " unit_id " 的单元结论必须通过")
      }
      if (mode == "单集成单元审批") {
        if (mapped_commit != candidate) {
          fail("默认模式的集成映射提交必须等于任务候选提交：" unit_id)
        }
        if (apply_before != unit_base || commit_before != unit_base) {
          fail("默认模式的差异应用前 HEAD 和当前分支提交前 HEAD 必须等于单元基线：" unit_id)
        }
        if (previous_commit_after != "" && unit_base != previous_commit_after) {
          fail("默认模式的相邻当前分支提交 HEAD 链不连续：" unit_id)
        }
        previous_commit_after = commit_after
      } else if (mode == "一次性执行") {
        if (apply_before != commit_before) {
          fail("一次性模式的组合差异应用前 HEAD 必须等于当前分支组合提交前 HEAD：" unit_id)
        }
        if (batch_commit_before == "") {
          batch_apply_before = apply_before
          batch_apply_after = apply_after
          batch_commit_before = commit_before
          batch_commit_after = commit_after
          batch_approval_fingerprint = approval_fingerprint
          batch_approval = approval
          batch_unified_review = unified_review
        } else if (apply_before != batch_apply_before || apply_after != batch_apply_after ||
                   commit_before != batch_commit_before || commit_after != batch_commit_after ||
                   approval_fingerprint != batch_approval_fingerprint || approval != batch_approval ||
                   unified_review != batch_unified_review) {
          fail("一次性模式的所有单元必须引用同一次统一 Review、当前分支提交及批准证据")
        }
      }
      unit_id = ""
    }

    /^执行模式：/ { mode = value_after($0, "执行模式："); next }
    /^## 集成单元检查点$/ { in_units = 1; next }
    in_units && /^## / { close_unit(); in_units = 0 }
    in_units && /^### 集成单元 U[0-9]+：/ {
      close_unit()
      unit_id = $0
      sub(/^### 集成单元 /, "", unit_id)
      sub(/：.*$/, "", unit_id)
      unit_count++
      if (unit_ids[unit_id]) {
        fail("集成单元检查点标识重复：" unit_id)
      }
      if (unit_id != "U" unit_count) {
        fail("集成单元检查点必须按 U1、U2 顺序记录")
      }
      unit_ids[unit_id] = 1
      risk_count = review_strategy_count = base_count = candidate_count = mapped_count = tree_count = 0
      report_isolation_count = unified_review_count = plan_fingerprint_count = code_fingerprint_count = 0
      command_fingerprint_count = dependency_fingerprint_count = environment_fingerprint_count = 0
      evidence_disposition_count = reviewer1_count = reviewer2_count = rejection_history_count = 0
      approval_count = apply_command_count = apply_exit_count = apply_before_count = apply_after_count = 0
      apply_result_count = approval_fingerprint_count = commit_message_count = current_commit_count = 0
      commit_command_count = commit_exit_count = commit_before_count = commit_after_count = 0
      commit_result_count = duration_count = unit_result_count = 0
      next
    }
    in_units && unit_id != "" && /^风险等级：/ { risk_count++; risk = value_after($0, "风险等级："); next }
    in_units && unit_id != "" && /^审查策略：/ { review_strategy_count++; review_strategy = value_after($0, "审查策略："); next }
    in_units && unit_id != "" && /^单元基线提交：/ { base_count++; unit_base = hash_after($0, "单元基线提交："); next }
    in_units && unit_id != "" && /^任务候选提交：/ { candidate_count++; candidate = hash_after($0, "任务候选提交："); next }
    in_units && unit_id != "" && /^集成映射提交：/ { mapped_count++; mapped_commit = hash_after($0, "集成映射提交："); next }
    in_units && unit_id != "" && /^任务候选树：/ { tree_count++; candidate_tree = hash_after($0, "任务候选树："); next }
    in_units && unit_id != "" && /^报告提交隔离：/ { report_isolation_count++; report_isolation = value_after($0, "报告提交隔离："); next }
    in_units && unit_id != "" && /^统一 Review 证据指纹：/ { unified_review_count++; unified_review = hash_after($0, "统一 Review 证据指纹："); next }
    in_units && unit_id != "" && /^Plan 证据指纹：/ { plan_fingerprint_count++; plan_fingerprint = hash_after($0, "Plan 证据指纹："); next }
    in_units && unit_id != "" && /^代码证据指纹：/ { code_fingerprint_count++; code_fingerprint = hash_after($0, "代码证据指纹："); next }
    in_units && unit_id != "" && /^命令证据指纹：/ { command_fingerprint_count++; command_fingerprint = hash_after($0, "命令证据指纹："); next }
    in_units && unit_id != "" && /^依赖证据指纹：/ { dependency_fingerprint_count++; dependency_fingerprint = hash_after($0, "依赖证据指纹："); next }
    in_units && unit_id != "" && /^环境证据指纹：/ { environment_fingerprint_count++; environment_fingerprint = hash_after($0, "环境证据指纹："); next }
    in_units && unit_id != "" && /^验证证据处置：/ { evidence_disposition_count++; evidence_disposition = value_after($0, "验证证据处置："); next }
    in_units && unit_id != "" && /^Reviewer 1 结论：/ { reviewer1_count++; reviewer1 = value_after($0, "Reviewer 1 结论："); next }
    in_units && unit_id != "" && /^Reviewer 2 结论：/ { reviewer2_count++; reviewer2 = value_after($0, "Reviewer 2 结论："); next }
    in_units && unit_id != "" && /^Review 驳回历史：/ { rejection_history_count++; rejection_history = value_after($0, "Review 驳回历史："); next }
    in_units && unit_id != "" && /^候选差异应用命令：/ { apply_command_count++; apply_command = value_after($0, "候选差异应用命令："); gsub(/`/, "", apply_command); next }
    in_units && unit_id != "" && /^候选差异应用退出码：/ { apply_exit_count++; apply_exit = value_after($0, "候选差异应用退出码："); next }
    in_units && unit_id != "" && /^候选差异应用前 HEAD：/ { apply_before_count++; apply_before = hash_after($0, "候选差异应用前 HEAD："); next }
    in_units && unit_id != "" && /^候选差异应用后 HEAD：/ { apply_after_count++; apply_after = hash_after($0, "候选差异应用后 HEAD："); next }
    in_units && unit_id != "" && /^候选差异应用结论：/ { apply_result_count++; apply_result = value_after($0, "候选差异应用结论："); next }
    in_units && unit_id != "" && /^批准内容指纹：/ { approval_fingerprint_count++; approval_fingerprint = hash_after($0, "批准内容指纹："); next }
    in_units && unit_id != "" && /^当前分支提交信息：/ { commit_message_count++; commit_message = value_after($0, "当前分支提交信息："); next }
    in_units && unit_id != "" && /^当前分支提交批准：/ { approval_count++; approval = value_after($0, "当前分支提交批准："); next }
    in_units && unit_id != "" && /^当前分支提交命令：/ { commit_command_count++; commit_command = value_after($0, "当前分支提交命令："); gsub(/`/, "", commit_command); next }
    in_units && unit_id != "" && /^当前分支提交退出码：/ { commit_exit_count++; commit_exit = value_after($0, "当前分支提交退出码："); next }
    in_units && unit_id != "" && /^当前分支提交前 HEAD：/ { commit_before_count++; commit_before = hash_after($0, "当前分支提交前 HEAD："); next }
    in_units && unit_id != "" && /^当前分支提交后 HEAD：/ { commit_after_count++; commit_after = hash_after($0, "当前分支提交后 HEAD："); next }
    in_units && unit_id != "" && /^当前分支提交：/ { current_commit_count++; current_commit = hash_after($0, "当前分支提交："); next }
    in_units && unit_id != "" && /^当前分支提交结论：/ { commit_result_count++; commit_result = value_after($0, "当前分支提交结论："); next }
    in_units && unit_id != "" && /^阶段耗时：/ { duration_count++; duration = value_after($0, "阶段耗时："); next }
    in_units && unit_id != "" && /^单元结论：/ { unit_result_count++; unit_result = value_after($0, "单元结论："); next }

    END {
      if (in_units) {
        close_unit()
      }
      if (unit_count == 0) {
        fail("完整交付至少需要一个集成单元检查点")
      }
      exit failures > 0 ? 1 : 0
    }
  ' "$integration_report"; then
    return 1
  fi

  main_worktree_path=$(awk -F'`' 'index($0, "主工作区路径：`") { print $2; exit }' "$integration_report")
  main_branch=$(awk -F'`' 'index($0, "主分支：`") { print $2; exit }' "$integration_report")
  main_baseline=$(awk -F'`' 'index($0, "主分支基线 HEAD：`") { print $2; exit }' "$integration_report")
  expected_main_head=$(awk -F'`' 'index($0, "预期主分支 HEAD：`") { print $2; exit }' "$integration_report")
  if [ -z "$main_worktree_path" ] || [ -z "$main_branch" ] || [ -z "$main_baseline" ] || [ -z "$expected_main_head" ]; then
    echo 'ERROR: 缺少主工作区、主分支、基线 HEAD 或预期 HEAD' >&2
    return 1
  fi

  case "$main_worktree_path" in
    /*) main_worktree_resolved=$main_worktree_path ;;
    *) main_worktree_resolved="$integration_root/$main_worktree_path" ;;
  esac
  main_worktree_absolute=$(cd "$main_worktree_resolved" 2>/dev/null && pwd -P) || {
    echo "ERROR: 主工作区路径不存在：$main_worktree_resolved" >&2
    return 1
  }
  actual_branch=$(git -C "$main_worktree_absolute" branch --show-current) || return 1
  actual_head=$(git -C "$main_worktree_absolute" rev-parse HEAD) || return 1
  case "$integration_report" in
    docs/pretty/*) report_relative=$integration_report ;;
    */docs/pretty/*) report_relative="docs/pretty/${integration_report#*/docs/pretty/}" ;;
    *) report_relative='' ;;
  esac
  if [ "$actual_branch" != "$main_branch" ]; then
    echo "ERROR: 主分支发生漂移，记录为 ${main_branch}，实际为 ${actual_branch}" >&2
    return 1
  fi
  if [ "$actual_head" != "$expected_main_head" ]; then
    actual_parent_count=$(git -C "$main_worktree_absolute" rev-list --parents -n 1 "$actual_head" | awk '{ print NF - 1 }') || return 1
    actual_parent=$(git -C "$main_worktree_absolute" rev-parse "${actual_head}^" 2>/dev/null) || actual_parent=''
    evidence_paths=$(git -C "$main_worktree_absolute" diff --name-only "$expected_main_head" "$actual_head") || return 1
    if [ -z "$report_relative" ] || [ "$actual_parent_count" != '1' ] || \
      [ "$actual_parent" != "$expected_main_head" ] || [ "$evidence_paths" != "$report_relative" ]; then
      echo "ERROR: 主分支 HEAD 发生未授权漂移，实际 HEAD 既不是预期代码 HEAD，也不是仅包含本 Execution Report 的直接后继证据提交" >&2
      return 1
    fi
  fi
  if ! validate_main_workspace_state "$main_worktree_absolute"; then
    echo 'ERROR: 主工作区包含未授权改动；只允许完全洁净，或仅保留 Harness 自动添加且未暂存的 /.worktrees/ 单行 .gitignore 修复' >&2
    return 1
  fi
  if ! git -C "$main_worktree_absolute" cat-file -e "${main_baseline}^{commit}" 2>/dev/null ||
    ! git -C "$main_worktree_absolute" merge-base --is-ancestor "$main_baseline" "$expected_main_head"; then
    echo 'ERROR: 主分支基线不是预期 HEAD 的祖先' >&2
    return 1
  fi
  last_commit_after=$(awk '/^当前分支提交后 HEAD：/ { value=$0; sub(/^当前分支提交后 HEAD：`/, "", value); sub(/`[。.][[:space:]]*$/, "", value); last=value } END { print last }' "$integration_report")
  if [ "$last_commit_after" != "$expected_main_head" ]; then
    echo 'ERROR: 最后一个当前分支提交后 HEAD 与预期主分支 HEAD 不一致' >&2
    return 1
  fi

  candidate_file=$(mktemp "${TMPDIR:-/tmp}/pretty-execution-candidates.XXXXXX") || return 1
  awk '
    /^任务候选提交：/ { candidate=$0; sub(/^任务候选提交：`/, "", candidate); sub(/`[。.][[:space:]]*$/, "", candidate) }
    /^集成映射提交：/ { mapped=$0; sub(/^集成映射提交：`/, "", mapped); sub(/`[。.][[:space:]]*$/, "", mapped) }
    /^任务候选树：/ { tree=$0; sub(/^任务候选树：`/, "", tree); sub(/`[。.][[:space:]]*$/, "", tree) }
    /^当前分支提交：/ { current=$0; sub(/^当前分支提交：`/, "", current); sub(/`[。.][[:space:]]*$/, "", current) }
    /^当前分支提交前 HEAD：/ { before=$0; sub(/^当前分支提交前 HEAD：`/, "", before); sub(/`[。.][[:space:]]*$/, "", before) }
    /^当前分支提交后 HEAD：/ {
      after=$0
      sub(/^当前分支提交后 HEAD：`/, "", after)
      sub(/`[。.][[:space:]]*$/, "", after)
    }
    /^当前分支提交结论：/ { print candidate, mapped, tree, current, before, after }
  ' "$integration_report" > "$candidate_file"

  execution_mode=$(awk '/^执行模式：/ { value=$0; sub(/^执行模式：/, "", value); sub(/[。.][[:space:]]*$/, "", value); print value; exit }' "$integration_report")
  batch_commit_before=$(awk '/^候选差异应用前 HEAD：/ { value=$0; sub(/^候选差异应用前 HEAD：`/, "", value); sub(/`[。.][[:space:]]*$/, "", value); print value; exit }' "$integration_report")
  candidate_failure=0
  seen_candidates='|'
  seen_mapped_commits='|'
  previous_mapped_commit=''
  last_current_commit=''
  last_current_tree=''
  while IFS=' ' read -r candidate mapped_commit candidate_tree current_commit commit_before commit_after; do
    if ! git -C "$main_worktree_absolute" cat-file -e "${candidate}^{commit}" 2>/dev/null; then
      echo "ERROR: 任务候选提交不存在：$candidate" >&2
      candidate_failure=1
      continue
    fi
    actual_tree=$(git -C "$main_worktree_absolute" rev-parse "${candidate}^{tree}") || {
      candidate_failure=1
      continue
    }
    if [ "$actual_tree" != "$candidate_tree" ]; then
      echo "ERROR: 任务候选树与提交实际树不一致：$candidate" >&2
      candidate_failure=1
    fi
    if ! git -C "$main_worktree_absolute" cat-file -e "${mapped_commit}^{commit}" 2>/dev/null; then
      echo "ERROR: 集成映射提交不存在：$mapped_commit" >&2
      candidate_failure=1
    fi
    if ! git -C "$main_worktree_absolute" cat-file -e "${current_commit}^{commit}" 2>/dev/null; then
      echo "ERROR: 当前分支提交不存在：$current_commit" >&2
      candidate_failure=1
      continue
    fi
    actual_current_tree=$(git -C "$main_worktree_absolute" rev-parse "${current_commit}^{tree}") || {
      candidate_failure=1
      continue
    }
    actual_current_parent=$(git -C "$main_worktree_absolute" rev-parse "${current_commit}^" 2>/dev/null) || actual_current_parent=''
    if [ "$actual_current_parent" != "$commit_before" ] || [ "$commit_after" != "$current_commit" ]; then
      echo "ERROR: 当前分支提交前后 HEAD 与提交对象不一致：$current_commit" >&2
      candidate_failure=1
    fi
    if [ "$execution_mode" = '单集成单元审批' ] && [ "$actual_current_tree" != "$candidate_tree" ]; then
      echo "ERROR: 当前分支提交树与候选树不一致：$candidate -> $current_commit" >&2
      candidate_failure=1
    fi
    last_current_commit=$current_commit
    last_current_tree=$actual_current_tree
    case "$seen_candidates" in
      *"|$candidate|"*)
        echo "ERROR: 任务候选提交必须与集成单元一一对应：$candidate" >&2
        candidate_failure=1
        ;;
      *) seen_candidates="${seen_candidates}${candidate}|" ;;
    esac
    case "$seen_mapped_commits" in
      *"|$mapped_commit|"*)
        echo "ERROR: 集成映射提交必须与任务候选一一对应：$mapped_commit" >&2
        candidate_failure=1
        ;;
      *) seen_mapped_commits="${seen_mapped_commits}${mapped_commit}|" ;;
    esac
    if [ "$execution_mode" = '一次性执行' ]; then
      expected_mapped_parent=${previous_mapped_commit:-$batch_commit_before}
      mapped_parent_count=$(git -C "$main_worktree_absolute" rev-list --parents -n 1 "$mapped_commit" | awk '{ print NF - 1 }')
      mapped_parent=$(git -C "$main_worktree_absolute" rev-parse "${mapped_commit}^" 2>/dev/null) || mapped_parent=''
      if [ "$mapped_parent_count" != '1' ] || [ "$mapped_parent" != "$expected_mapped_parent" ]; then
        echo "ERROR: 一次性模式的集成映射提交必须按单元声明顺序形成无夹带的线性提交链：$mapped_commit" >&2
        candidate_failure=1
      fi
      previous_mapped_commit=$mapped_commit
      if [ "$candidate" != "$mapped_commit" ]; then
        candidate_patch_id=$(git -C "$main_worktree_absolute" diff-tree --root --no-commit-id -p --binary "$candidate" | git patch-id --stable | awk '{ print $1 }')
        mapped_patch_id=$(git -C "$main_worktree_absolute" diff-tree --root --no-commit-id -p --binary "$mapped_commit" | git patch-id --stable | awk '{ print $1 }')
        if [ -z "$candidate_patch_id" ] || [ "$candidate_patch_id" != "$mapped_patch_id" ]; then
          echo "ERROR: 任务候选与集成映射提交的补丁内容不一致：$candidate -> $mapped_commit" >&2
          candidate_failure=1
        fi
      fi
    fi
    if [ -n "$report_relative" ] &&
      git -C "$main_worktree_absolute" show --format= --name-only "$candidate" | grep -Fxq "$report_relative"; then
      echo "ERROR: Execution Report 被混入任务候选提交：$candidate" >&2
      candidate_failure=1
    fi
  done < "$candidate_file"
  rm -f -- "$candidate_file"

  if [ "$execution_mode" = '一次性执行' ]; then
    final_mapped_tree=$(git -C "$main_worktree_absolute" rev-parse "${previous_mapped_commit}^{tree}" 2>/dev/null) || final_mapped_tree=''
    batch_approval_fingerprint=$(awk '/^批准内容指纹：/ { value=$0; sub(/^批准内容指纹：`/, "", value); sub(/`[。.][[:space:]]*$/, "", value); print value; exit }' "$integration_report")
    if [ -z "$final_mapped_tree" ] || [ "$last_current_tree" != "$final_mapped_tree" ] ||
      [ "$batch_approval_fingerprint" != "$final_mapped_tree" ]; then
      echo 'ERROR: 一次性模式的当前分支组合提交树和批准内容指纹必须等于最终集成映射树' >&2
      candidate_failure=1
    fi
  fi

  if [ "$candidate_failure" -ne 0 ]; then
    return 1
  fi
  return 0
}

validate_task_evidence() {
  evidence_report=$1
  awk '
    function fail(message) {
      print "ERROR: " message > "/dev/stderr"
      failures++
    }

    function value_after(line, prefix, value) {
      value = line
      sub("^[[:space:]]*" prefix "[[:space:]]*", "", value)
      sub(/[。.][[:space:]]*$/, "", value)
      return value
    }

    function close_task() {
      if (task_label == "") return
      if (task_type_count != 1 || (task_type !~ /^业务行为/ && task_type !~ /^非行为/)) {
        fail(task_label " 必须且只能记录一次业务行为或非行为任务类型")
      } else if (task_type ~ /^业务行为/) {
        if (red_command_count != 1 || red_exit_count != 1 || red_exit !~ /^[1-9][0-9]*$/ ||
            red_expected_count != 1 || red_actual_count != 1) {
          fail(task_label " 缺少可信的 RED 命令、非零退出码、预期失败或实际摘要")
        }
        if (green_command_count != 1 || green_exit_count != 1 || green_exit != "0") {
          fail(task_label " 缺少 GREEN 命令或成功退出码")
        }
        if (refactor_command_count != 1 || refactor_exit_count != 1 || refactor_exit != "0") {
          fail(task_label " 缺少重构复验命令或成功退出码")
        }
        if (!(red_command_line < red_exit_line && red_exit_line < green_command_line &&
              green_command_line < green_exit_line && green_exit_line < refactor_command_line &&
              refactor_command_line < refactor_exit_line)) {
          fail(task_label " 的 RED、GREEN、重构复验证据顺序错误")
        }
      } else {
        if (not_applicable_count != 1 || equivalent_command_count != 1 ||
            equivalent_exit_count != 1 || equivalent_exit != "0") {
          fail(task_label " 的非行为任务缺少不适用理由或成功等价验证")
        }
      }
      task_label = ""
    }

    /^## 任务执行证据$/ { in_evidence=1; next }
    in_evidence && /^## / { close_task(); in_evidence=0 }
    in_evidence && /^### 任务 / {
      close_task()
      task_label = $0
      task_count++
      task_type_count = red_command_count = red_exit_count = 0
      red_expected_count = red_actual_count = green_command_count = green_exit_count = 0
      refactor_command_count = refactor_exit_count = not_applicable_count = 0
      equivalent_command_count = equivalent_exit_count = 0
      red_command_line = red_exit_line = green_command_line = green_exit_line = 0
      refactor_command_line = refactor_exit_line = 0
      next
    }
    in_evidence && task_label != "" && /^任务类型：/ { task_type_count++; task_type=value_after($0, "任务类型："); next }
    in_evidence && task_label != "" && /^RED 命令：/ { red_command_count++; red_command_line=NR; next }
    in_evidence && task_label != "" && /^RED 退出码：/ { red_exit_count++; red_exit=value_after($0, "RED 退出码："); red_exit_line=NR; next }
    in_evidence && task_label != "" && /^RED 预期失败：/ { red_expected_count++; next }
    in_evidence && task_label != "" && /^RED 实际摘要：/ { red_actual_count++; next }
    in_evidence && task_label != "" && /^GREEN 命令：/ { green_command_count++; green_command_line=NR; next }
    in_evidence && task_label != "" && /^GREEN 退出码：/ { green_exit_count++; green_exit=value_after($0, "GREEN 退出码："); green_exit_line=NR; next }
    in_evidence && task_label != "" && /^重构复验命令：/ { refactor_command_count++; refactor_command_line=NR; next }
    in_evidence && task_label != "" && /^重构复验退出码：/ { refactor_exit_count++; refactor_exit=value_after($0, "重构复验退出码："); refactor_exit_line=NR; next }
    in_evidence && task_label != "" && /^不适用理由：/ { not_applicable_count++; next }
    in_evidence && task_label != "" && /^等价验证命令：/ { equivalent_command_count++; next }
    in_evidence && task_label != "" && /^等价验证退出码：/ { equivalent_exit_count++; equivalent_exit=value_after($0, "等价验证退出码："); next }

    END {
      close_task()
      if (task_count == 0) fail("缺少可执行任务证据")
      exit failures > 0 ? 1 : 0
    }
  ' "$evidence_report"
}

validate_coverage_results() {
  coverage_report=$1
  awk '
    function percentage(line, value) {
      if (!match(line, /[0-9]+([.][0-9]+)?%/)) return -1
      value = substr(line, RSTART, RLENGTH - 1)
      return value + 0
    }
    /^行覆盖率阈值：/ { line_threshold=percentage($0); line_threshold_count++ }
    /^分支覆盖率阈值：/ { branch_threshold=percentage($0); branch_threshold_count++ }
    /^行覆盖率结果：/ { line_result=percentage($0); line_result_count++ }
    /^分支覆盖率结果：/ { branch_result=percentage($0); branch_result_count++ }
    END {
      valid = line_threshold_count == 1 && branch_threshold_count == 1 &&
        line_result_count == 1 && branch_result_count == 1 &&
        line_threshold >= 0 && line_threshold <= 100 &&
        branch_threshold >= 0 && branch_threshold <= 100 &&
        line_result >= line_threshold && line_result <= 100 &&
        branch_result >= branch_threshold && branch_result <= 100
      exit valid ? 0 : 1
    }
  ' "$coverage_report"
}

validate_report() {
  report_file=$1
  completion_mode=${2:-structure}
  failures=0

  if ! validate_execution_path "$report_file"; then
    echo "ERROR: Execution Report 路径必须匹配 docs/pretty/<topic>/YYYY-MM-DD-<topic>-execution.md，且两个 <topic> 必须是相同的小写 kebab-case" >&2
    failures=$((failures + 1))
  fi

  require_pattern() {
    if ! grep -Eiq -- "$1" "$report_file"; then
      echo "ERROR: $2" >&2
      failures=$((failures + 1))
    fi
  }

  reject_pattern() {
    if grep -Eiq -- "$1" "$report_file"; then
      echo "ERROR: $2" >&2
      failures=$((failures + 1))
    fi
  }

  require_pattern '^# .+执行报告$' '缺少中文执行报告标题'
  for section in 执行概览 输入与批准 执行控制 工作区与质量基线 执行引擎 任务执行证据 集成单元检查点 业务切片质量门禁 测试覆盖率 代码质量审查 偏差与阻塞 最终全量验证 '授权与 Git 操作' 最终质量结论; do
    require_pattern "^## ${section}$" "缺少章节：${section}"
  done

  require_pattern 'Plan 路径：' '缺少 Plan 路径'
  require_pattern '执行批次：' '缺少执行批次'
  require_pattern '执行模式：(单集成单元审批|一次性执行)' '缺少合法执行模式'
  require_pattern '当前状态：' '缺少当前生命周期状态'
  require_pattern '当前集成单元：' '缺少当前集成单元'
  require_pattern '主工作区路径：' '缺少主工作区路径'
  require_pattern '主分支：' '缺少主分支'
  require_pattern '主分支基线 HEAD：' '缺少主分支基线 HEAD'
  require_pattern '预期主分支 HEAD：' '缺少预期主分支 HEAD'
  require_pattern '工作区洁净检查：' '缺少主工作区洁净检查'
  require_pattern '自动编排状态：' '缺少自动编排状态'
  require_pattern '^### 控制事件 [0-9]+：' '缺少可恢复控制事件'
  require_pattern '状态转换：' '缺少生命周期状态转换'
  require_pattern 'Worktree 路径：' '缺少 Worktree 路径'
  require_pattern 'Worktree 忽略检查：' '缺少 Worktree 忽略检查'
  require_pattern 'Worktree 忽略修复：' '缺少 Worktree 忽略修复记录'
  require_pattern '基线命令：' '缺少实施前基线命令'
  require_pattern '基线退出码：' '缺少实施前基线退出码'
  require_pattern '基线结论：' '缺少实施前基线结论'
  require_pattern '执行引擎：' '缺少执行引擎证据'
  require_pattern 'Git 操作：' '缺少 Git 授权与操作记录'
  require_pattern '最终结论：(完成|未完成|阻塞)' '最终结论必须是完成、未完成或阻塞'
  reject_pattern 'TODO|TBD|待补充|稍后补充|\.\.\.|……' '存在占位符或省略内容'
  reject_pattern 'Bearer[[:space:]]+[A-Za-z0-9._~+/-]+=*' '疑似记录了 Bearer Token'

  if ! validate_control_contract "$report_file" "$completion_mode"; then
    failures=$((failures + 1))
  fi

  if [ "$completion_mode" = 'structure' ] && grep -Eq '^Plan 最终哈希：' "$report_file"; then
    if ! validate_plan_readonly_contract "$report_file"; then
      failures=$((failures + 1))
    fi
  fi

  if [ "$completion_mode" = 'structure' ] && grep -Eq '^当前状态：等待当前分支提交批准。?$' "$report_file"; then
    require_pattern '任务候选提交：`([0-9a-f]{40}|[0-9a-f]{64})`' '等待当前分支提交批准时缺少任务候选提交'
    require_pattern '任务候选树：`([0-9a-f]{40}|[0-9a-f]{64})`' '等待当前分支提交批准时缺少任务候选树'
    require_pattern '批准内容指纹：`([0-9a-f]{40}|[0-9a-f]{64})`' '等待当前分支提交批准时缺少批准内容指纹'
    require_pattern '当前分支提交信息：' '等待当前分支提交批准时缺少拟用提交信息'
    require_pattern '候选差异应用命令：' '等待当前分支提交批准时缺少候选差异应用命令'
    require_pattern '候选差异应用退出码：0' '等待当前分支提交批准时缺少成功的差异应用退出码'
    require_pattern '候选差异应用前 HEAD：`([0-9a-f]{40}|[0-9a-f]{64})`' '等待当前分支提交批准时缺少差异应用前 HEAD'
    require_pattern '候选差异应用后 HEAD：`([0-9a-f]{40}|[0-9a-f]{64})`' '等待当前分支提交批准时缺少差异应用后 HEAD'
    reject_pattern '^当前分支提交批准：|^当前分支提交命令：|^当前分支提交退出码：|^当前分支提交前 HEAD：|^当前分支提交后 HEAD：|^当前分支提交：|^当前分支提交结论：' '等待当前分支提交批准时不得记录已创建的当前分支提交'
    if ! validate_pending_workspace_contract "$report_file"; then
      failures=$((failures + 1))
    fi
  fi

  if [ "$completion_mode" = 'complete' ]; then
    require_pattern 'Plan 批次基线哈希：`([0-9a-f]{40}|[0-9a-f]{64})`' '缺少有效的 Plan 批次基线哈希'
    require_pattern 'Plan 批次批准：' '缺少 Plan 批次批准记录'
    require_pattern '既有成果复核：' '缺少既有成果复核记录'
    require_pattern '批次结论：' '缺少执行批次结论'
    require_pattern '^### 任务 [^[:space:]].*$' '缺少任务执行证据'
    require_pattern '质量审查范围：' '缺少代码质量审查范围'
    require_pattern '质量发现与修复：' '缺少质量发现与修复记录'
    require_pattern '质量复查结果：' '缺少质量复查结果'
    require_pattern '功能完整性核对：' '缺少功能完整性核对'
    require_pattern '简洁性与必要性审查：' '缺少简洁性与必要性审查'
    require_pattern '可读性与业务表达审查：' '缺少可读性与业务表达审查'
    require_pattern '测试完整性保护：' '缺少测试完整性保护'
    require_pattern '变更范围控制：' '缺少变更范围控制'
    require_pattern '覆盖率适用性：' '缺少覆盖率适用性'
    require_pattern '覆盖率范围：' '缺少覆盖率统计范围'
    require_pattern '行覆盖率阈值：' '缺少行覆盖率阈值'
    require_pattern '分支覆盖率阈值：' '缺少分支覆盖率阈值'
    require_pattern '行覆盖率结果：' '缺少行覆盖率结果'
    require_pattern '分支覆盖率结果：' '缺少分支覆盖率结果'
    require_pattern '覆盖率报告位置：' '缺少覆盖率报告位置'
    require_pattern '排除项一致性：' '缺少覆盖率排除项一致性声明'
    require_pattern '最终回归命令：' '缺少最终全量回归命令'
    require_pattern '最终回归退出码：' '缺少最终全量回归退出码'
    require_pattern '覆盖率门禁退出码：' '缺少最终覆盖率门禁退出码'
    require_pattern '最终验证退出码：' '缺少 completion verification 退出码'
    require_pattern 'finish-work 结论：' '缺少 finish-work 结论'
    require_pattern '最终结论：完成' '完整交付的最终结论不是完成'
    require_pattern '质量复查结果：通过' '代码质量复查未通过'
    require_pattern '功能完整性核对：通过' '功能完整性核对未通过'
    require_pattern '简洁性与必要性审查：通过' '简洁性与必要性审查未通过'
    require_pattern '可读性与业务表达审查：通过' '可读性与业务表达审查未通过'
    require_pattern '测试完整性保护：通过' '测试完整性保护未通过'
    require_pattern '变更范围控制：通过' '变更范围控制未通过'
    require_pattern '业务切片结论：通过|业务切片结论：不适用（[^）]+）' '业务切片门禁未通过且无不适用理由'
    require_pattern '最终回归退出码：0' '最终全量回归未通过'
    require_pattern '最终验证退出码：0' 'completion verification 未通过'
    require_pattern 'finish-work 结论：通过' 'finish-work 未通过'
    require_pattern 'Plan 最终哈希：`([0-9a-f]{40}|[0-9a-f]{64})`' '缺少有效的 Plan 最终哈希'
    require_pattern 'Plan 只读校验：通过' 'Plan 最终只读校验未通过'
    require_pattern 'Worktree 路径：`[^`]+`|Worktree 路径：不适用（[^）]+）' 'Worktree 路径为空或格式无效'
    require_pattern 'Worktree 忽略检查：通过|Worktree 忽略检查：不适用（[^）]+）' 'Worktree 忽略检查未通过且无不适用理由'
    require_pattern 'Worktree 忽略修复：已添加 `/.worktrees/`|Worktree 忽略修复：不需要' 'Worktree 忽略修复记录无效'

    if grep -Eq -- '覆盖率适用性：适用' "$report_file"; then
      require_pattern '覆盖率门禁退出码：0' '覆盖率门禁未通过'
      require_pattern '排除项一致性：是' '覆盖率排除项与 Plan 不一致'
      require_pattern '最终覆盖率结论：通过' '最终覆盖率结论未通过'
      if ! validate_coverage_results "$report_file"; then
        echo 'ERROR: 覆盖率结果低于阈值或阈值/结果字段不唯一' >&2
        failures=$((failures + 1))
      fi
    else
      require_pattern '覆盖率适用性：不适用（[^）]+）' '覆盖率不适用时必须写明理由'
      require_pattern '最终覆盖率结论：不适用（[^）]+）' '最终覆盖率不适用时必须写明理由'
    fi

    if ! validate_task_evidence "$report_file"; then
      failures=$((failures + 1))
    fi

    if ! validate_plan_readonly_contract "$report_file"; then
      failures=$((failures + 1))
    fi
    if ! validate_worktree_contract "$report_file"; then
      failures=$((failures + 1))
    fi
    if ! validate_integration_contract "$report_file"; then
      failures=$((failures + 1))
    fi
  fi

  if [ "$failures" -ne 0 ]; then
    return 1
  fi
  return 0
}

run_self_test() {
  test_dir=$(mktemp -d "${TMPDIR:-/tmp}/pretty-executing-plan.XXXXXX") || exit 2
  fixture_dir="$test_dir/docs/pretty/rush-order"
  stale_fixture_dir="$test_dir/stale/docs/pretty/rush-order"
  global_only_fixture_dir="$test_dir/global-only/docs/pretty/rush-order"
  pending_main="$test_dir/pending-main"
  legacy_dir="$test_dir/docs/superpowers/executions"
  mkdir -p "$fixture_dir" "$stale_fixture_dir" "$global_only_fixture_dir" "$legacy_dir"
  plan_file="$fixture_dir/2026-07-27-rush-order-plan.md"
  old_plan_file="$fixture_dir/2026-07-26-rush-order-plan.md"
  good_report="$fixture_dir/2026-07-28-rush-order-execution.md"
  no_baseline="$fixture_dir/2026-07-29-rush-order-execution.md"
  no_red="$fixture_dir/2026-07-30-rush-order-execution.md"
  no_coverage="$fixture_dir/2026-07-31-rush-order-execution.md"
  no_review="$fixture_dir/2026-08-01-rush-order-execution.md"
  no_implementation_quality="$fixture_dir/2026-08-02-rush-order-execution.md"
  no_final="$fixture_dir/2026-08-03-rush-order-execution.md"
  exclusion_changed="$fixture_dir/2026-08-04-rush-order-execution.md"
  placeholder="$fixture_dir/2026-08-05-rush-order-execution.md"
  no_plan_batch_baseline="$fixture_dir/2026-08-06-rush-order-execution.md"
  no_task_plan_recheck="$fixture_dir/2026-08-07-rush-order-execution.md"
  mismatched_task_plan_hash="$fixture_dir/2026-08-08-rush-order-execution.md"
  mismatched_final_plan_hash="$fixture_dir/2026-08-09-rush-order-execution.md"
  no_worktree_evidence="$fixture_dir/2026-08-10-rush-order-execution.md"
  empty_worktree_path="$fixture_dir/2026-08-11-rush-order-execution.md"
  continued_after_plan_mismatch="$fixture_dir/2026-08-13-rush-order-execution.md"
  missing_blocked_batch_conclusion="$fixture_dir/2026-08-14-rush-order-execution.md"
  reapproval_not_confirmed="$fixture_dir/2026-08-15-rush-order-execution.md"
  existing_results_review_failed="$fixture_dir/2026-08-16-rush-order-execution.md"
  global_ignore_only_report="$global_only_fixture_dir/2026-08-17-rush-order-execution.md"
  stale_current_plan_report="$stale_fixture_dir/2026-08-11-rush-order-execution.md"
  legacy_report="$legacy_dir/2026-07-28-rush-order-execution.md"
  mismatched_topic_report="$fixture_dir/2026-08-12-other-execution.md"
  contradictory_status_report="$fixture_dir/2026-08-18-rush-order-execution.md"
  illegal_transition_report="$fixture_dir/2026-08-19-rush-order-execution.md"
  missing_unit_review_report="$fixture_dir/2026-08-20-rush-order-execution.md"
  missing_commit_approval_report="$fixture_dir/2026-08-21-rush-order-execution.md"
  missing_evidence_fingerprint_report="$fixture_dir/2026-08-22-rush-order-execution.md"
  mismatched_main_head_report="$fixture_dir/2026-08-23-rush-order-execution.md"
  paused_report="$fixture_dir/2026-08-24-rush-order-execution.md"
  pending_report="$fixture_dir/2026-08-32-rush-order-execution.md"
  pending_head_drift_report="$fixture_dir/2026-09-04-rush-order-execution.md"
  pending_fingerprint_mismatch_report="$fixture_dir/2026-09-05-rush-order-execution.md"
  no_verify_commit_report="$fixture_dir/2026-09-06-rush-order-execution.md"
  batch_report="$fixture_dir/2026-08-25-rush-order-execution.md"
  batch_review_mismatch_report="$fixture_dir/2026-09-02-rush-order-execution.md"
  batch_mapping_drift_report="$fixture_dir/2026-09-03-rush-order-execution.md"
  high_risk_report="$fixture_dir/2026-08-26-rush-order-execution.md"
  early_pause_report="$fixture_dir/2026-08-27-rush-order-execution.md"
  non_plan_block_recovered_report="$fixture_dir/2026-08-29-rush-order-execution.md"
  second_behavior_missing_tdd_report="$fixture_dir/2026-08-30-rush-order-execution.md"
  below_threshold_report="$fixture_dir/2026-08-31-rush-order-execution.md"
  paused_stale_hash_report="$fixture_dir/2026-09-01-rush-order-execution.md"
  linked_worktree_report="$test_dir/report-worktree/docs/pretty/rush-order/2026-08-28-rush-order-execution.md"

  cleanup_self_test() {
    rm -rf -- "$test_dir"
  }
  trap cleanup_self_test EXIT INT TERM

  printf '%s\n' '# 工单加急 Plan' '版本：重新批准版本。' > "$plan_file"
  printf '%s\n' '# 工单加急 Plan' '版本：首次批准版本。' > "$old_plan_file"
  git -C "$test_dir" init -q || return 1
  git -C "$test_dir/stale" init -q || return 1
  git -C "$test_dir/global-only" init -q || return 1
  mkdir -p "$test_dir/.worktrees" "$test_dir/stale/.worktrees" "$test_dir/global-only/.worktrees" \
    "$(dirname "$linked_worktree_report")"
  printf '%s\n' 'target/' > "$test_dir/.gitignore"
  printf '%s\n' '/.worktrees/' > "$test_dir/stale/.gitignore"
  printf '%s\n' 'target/' > "$test_dir/global-only/.gitignore"
  printf '%s\n' '/.worktrees/' > "$test_dir/global-only/.git/info/exclude"
  plan_hash=$(git hash-object -- "$plan_file") || return 1
  old_plan_hash=$(git hash-object -- "$old_plan_file") || return 1
  git -C "$test_dir" add .gitignore docs/pretty/rush-order/2026-07-27-rush-order-plan.md \
    docs/pretty/rush-order/2026-07-26-rush-order-plan.md || return 1
  git -C "$test_dir" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'test: establish execution baseline' || return 1
  base_commit=$(git -C "$test_dir" rev-parse HEAD) || return 1
  main_branch=$(git -C "$test_dir" branch --show-current) || return 1
  git -C "$test_dir" switch -q -c batch-candidates || return 1
  printf '%s\n' 'unit one' > "$test_dir/unit-one.txt"
  git -C "$test_dir" add unit-one.txt || return 1
  git -C "$test_dir" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'feat: complete unit U1' || return 1
  unit_commit=$(git -C "$test_dir" rev-parse HEAD) || return 1
  printf '%s\n' 'unit two' > "$test_dir/unit-two.txt"
  git -C "$test_dir" add unit-two.txt || return 1
  git -C "$test_dir" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'feat: complete unit U2' || return 1
  unit2_commit=$(git -C "$test_dir" rev-parse HEAD) || return 1
  unit2_tree=$(git -C "$test_dir" rev-parse "${unit2_commit}^{tree}") || return 1
  printf '%s\n' 'unrelated mapped content' > "$test_dir/drift.txt"
  git -C "$test_dir" add drift.txt || return 1
  git -C "$test_dir" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'test: create mismatched candidate' || return 1
  drift_candidate=$(git -C "$test_dir" rev-parse HEAD) || return 1
  drift_tree=$(git -C "$test_dir" rev-parse "${drift_candidate}^{tree}") || return 1
  git -C "$test_dir" switch -q "$main_branch" || return 1
  git -C "$test_dir" diff --binary "$base_commit" "$unit_commit" | git -C "$test_dir" apply || return 1
  git -C "$test_dir" add unit-one.txt || return 1
  git -C "$test_dir" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'feat: integrate unit U1' || return 1
  current_commit=$(git -C "$test_dir" rev-parse HEAD) || return 1
  git -C "$test_dir" worktree add -q -b batch-main "$test_dir/batch-main" "$base_commit" || return 1
  git -C "$test_dir" diff --binary "$base_commit" "$unit2_commit" | git -C "$test_dir/batch-main" apply || return 1
  git -C "$test_dir/batch-main" add -A || return 1
  git -C "$test_dir/batch-main" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'feat: integrate batch units' || return 1
  batch_commit=$(git -C "$test_dir/batch-main" rev-parse HEAD) || return 1
  git -C "$test_dir" worktree add -q -b pending-main "$pending_main" "$base_commit" || return 1
  git -C "$pending_main" diff --binary "$base_commit" "$unit_commit" | git -C "$pending_main" apply || return 1
  printf '%s\n' '/.worktrees/' >> "$test_dir/.gitignore"
  unit_tree=$(git -C "$test_dir" rev-parse "${unit_commit}^{tree}") || return 1
  command_fingerprint=$(printf '%s\n' 'mvn -Dtest=RushServiceTest test|0' | git hash-object --stdin) || return 1
  dependency_fingerprint=$(printf '%s\n' 'pom.xml|unchanged' | git hash-object --stdin) || return 1
  environment_fingerprint=$(printf '%s\n' 'jdk8|maven|self-test' | git hash-object --stdin) || return 1
  unified_review_fingerprint=$(printf '%s\n' 'unified-review|U1,U2|passed' | git hash-object --stdin) || return 1

  cat > "$good_report" <<'EOF'
# 工单加急执行报告
## 执行概览
执行批次：2026-07-29 第一次。
## 输入与批准
Plan 路径：`docs/pretty/rush-order/2026-07-27-rush-order-plan.md`。Design 路径：不适用，Plan 已包含批准的技术输入。PRD 路径：不适用，纯技术任务。
## 执行控制
执行模式：单集成单元审批。
当前状态：已完成。
当前集成单元：无（全部完成）。
主工作区路径：`__MAIN_ROOT__`。
主分支：`__MAIN_BRANCH__`。
主分支基线 HEAD：`__BASE_COMMIT__`。
预期主分支 HEAD：`__CURRENT_COMMIT__`。
工作区洁净检查：通过（仅保留 Harness 自动添加且未暂存的 `/.worktrees/` 单行 `.gitignore` 修复）。
自动编排状态：停止（执行完成）。
### 控制事件 1：开始执行
状态转换：未开始 -> 执行中。
触发来源：用户批准执行。
恢复入口：不适用（正常启动）。
### 控制事件 2：等待代码审查
状态转换：执行中 -> 等待 Review。
触发来源：集成单元 U1 完成任务提交和单元门禁。
恢复入口：人工 Review 结论。
### 控制事件 3：等待当前分支提交批准
状态转换：等待 Review -> 等待当前分支提交批准。
触发来源：Reviewer 1 审查通过并已应用候选差异。
恢复入口：人工批准当前分支提交。
### 控制事件 4：执行最终门禁
状态转换：等待当前分支提交批准 -> 最终验证中。
触发来源：人工批准并完成 U1 的当前分支本地提交。
恢复入口：最终全量门禁结果。
### 控制事件 5：完成
状态转换：最终验证中 -> 已完成。
触发来源：最终全量门禁通过。
恢复入口：不适用（执行完成）。
## 工作区与质量基线
Worktree 路径：`.worktrees/feature-rush-order`。
Worktree 忽略检查：通过。
Worktree 忽略修复：已添加 `/.worktrees/`。
基线命令：`mvn -pl work-order-application test`。
基线退出码：0。
基线结论：通过。
## 执行引擎
执行引擎：`superpowers:executing-plans`，当前任务强耦合。
## 任务执行证据
### 执行批次 1：首次批准版本
Plan 批次基线哈希：`__OLD_PLAN_HASH__`。
Plan 批次批准：首次批准（用户批准记录 A）。
既有成果复核：不适用（首次执行批次）。
### 任务 1：增加工单加急行为
任务类型：业务行为。
RED 命令：`mvn -Dtest=RushServiceTest test`。
RED 退出码：1。
RED 预期失败：尚未发送加急消息。
RED 实际摘要：断言期望一次，实际零次。
GREEN 命令：`mvn -Dtest=RushServiceTest test`。
GREEN 退出码：0。
重构复验命令：`mvn -Dtest=RushServiceTest test`。
重构复验退出码：0。
Plan 只读复验哈希：`__PLAN_HASH__`。
Plan 只读复验结论：失败（检测到 Plan 内容变化）。
批次结论：阻塞（Plan 内容变化）。
### 执行批次 2：重新批准版本
Plan 批次基线哈希：`__PLAN_HASH__`。
Plan 批次批准：重新批准（用户批准记录 B）。
既有成果复核：通过（任务 1 的代码、测试和报告证据仍符合新 Plan）。
### 任务 2：复核既有成果后继续
任务类型：非行为验证。
不适用理由：只复核已完成成果与新 Plan 的一致性，不修改业务行为。
等价验证命令：`git diff --check`。
等价验证退出码：0。
Plan 只读复验哈希：`__PLAN_HASH__`。
Plan 只读复验结论：通过。
批次结论：通过。
## 集成单元检查点
### 集成单元 U1：增加工单加急行为
风险等级：低。
审查策略：单 Reviewer。
单元基线提交：`__BASE_COMMIT__`。
任务候选提交：`__UNIT_COMMIT__`。
集成映射提交：`__UNIT_COMMIT__`。
任务候选树：`__UNIT_TREE__`。
报告提交隔离：通过（Execution Report 未进入任务候选提交）。
统一 Review 证据指纹：不适用（默认模式逐单元审查）。
Plan 证据指纹：`__PLAN_HASH__`。
代码证据指纹：`__UNIT_COMMIT__`。
命令证据指纹：`__COMMAND_FINGERPRINT__`。
依赖证据指纹：`__DEPENDENCY_FINGERPRINT__`。
环境证据指纹：`__ENVIRONMENT_FINGERPRINT__`。
验证证据处置：新鲜运行。
Reviewer 1 结论：通过（独立完成 Plan 符合性与代码质量审查）。
Reviewer 2 结论：不适用（低风险单元只需一个独立 Reviewer）。
Review 驳回历史：无。
候选差异应用命令：`git diff --binary __BASE_COMMIT__ __UNIT_COMMIT__ | git apply`。
候选差异应用退出码：0。
候选差异应用前 HEAD：`__BASE_COMMIT__`。
候选差异应用后 HEAD：`__BASE_COMMIT__`。
候选差异应用结论：通过。
批准内容指纹：`__UNIT_TREE__`。
当前分支提交信息：`feat: complete unit U1`。
当前分支提交批准：已批准（用户批准记录 C，包含上述提交信息）。
当前分支提交命令：`git add -- unit-one.txt && git commit -m 'feat: complete unit U1'`。
当前分支提交退出码：0。
当前分支提交前 HEAD：`__BASE_COMMIT__`。
当前分支提交后 HEAD：`__CURRENT_COMMIT__`。
当前分支提交：`__CURRENT_COMMIT__`。
当前分支提交结论：通过。
阶段耗时：实现 6 分钟；验证 2 分钟；Review 等待 1 分钟；差异应用 1 分钟；提交 1 分钟。
单元结论：通过。
## 业务切片质量门禁
业务切片结论：通过。
## 测试覆盖率
覆盖率适用性：适用。
覆盖率范围：本次新增和修改的业务代码。
行覆盖率阈值：80%。
分支覆盖率阈值：70%。
行覆盖率结果：90%。
分支覆盖率结果：80%。
覆盖率报告位置：`target/site/jacoco/index.html`。
排除项一致性：是。
最终覆盖率结论：通过。
## 代码质量审查
质量审查范围：本次生产代码差异、分层和测试语义。
质量发现与修复：发现重复判断，已提取为现有领域规则调用。
质量复查结果：通过。
功能完整性核对：通过；加急行为、非法状态拒绝和失败传播均已实现。
简洁性与必要性审查：通过；直接复用现有领域规则，没有新增包装层或预留扩展点。
可读性与业务表达审查：通过；命名使用加急领域术语，控制流直接表达状态判断。
测试完整性保护：通过；保留正常、非法状态和失败传播测试，未弱化断言或覆盖率要求。
变更范围控制：通过；仅修改加急行为及直接测试，没有无关旧代码重构。
## 偏差与阻塞
无。
## 最终全量验证
最终回归命令：`mvn test jacoco:report jacoco:check`。
最终回归退出码：0。
覆盖率门禁退出码：0。
最终验证退出码：0。
finish-work 结论：通过。
Plan 最终哈希：`__PLAN_HASH__`。
Plan 只读校验：通过。
## 授权与 Git 操作
Git 操作：已创建 worktree 候选提交，Review 通过后应用未暂存差异，并在人工批准后创建当前分支本地提交；未 push、未创建 MR、未执行远端合并。
Execution Report 提交策略：完整校验后只应用独立未暂存证据差异，人工批准后创建当前分支独立证据提交。
## 最终质量结论
最终结论：完成。
未闭环项：无。
EOF

  sed "s|__OLD_PLAN_HASH__|$old_plan_hash|g;s|__PLAN_HASH__|$plan_hash|g;s|__MAIN_ROOT__|$test_dir|g;s|__MAIN_BRANCH__|$main_branch|g;s|__BASE_COMMIT__|$base_commit|g;s|__UNIT_COMMIT__|$unit_commit|g;s|__CURRENT_COMMIT__|$current_commit|g;s|__UNIT_TREE__|$unit_tree|g;s|__COMMAND_FINGERPRINT__|$command_fingerprint|g;s|__DEPENDENCY_FINGERPRINT__|$dependency_fingerprint|g;s|__ENVIRONMENT_FINGERPRINT__|$environment_fingerprint|g" "$good_report" > "$good_report.rendered"
  mv "$good_report.rendered" "$good_report"
  sed -e "s|^主工作区路径：.*|主工作区路径：\`$pending_main\`。|" \
    -e 's/^主分支：.*$/主分支：`pending-main`。/' \
    -e "s|^预期主分支 HEAD：.*|预期主分支 HEAD：\`$base_commit\`。|" \
    -e '/^当前分支提交批准：/d;/^当前分支提交命令：/d;/^当前分支提交退出码：/d;/^当前分支提交前 HEAD：/d;/^当前分支提交后 HEAD：/d;/^当前分支提交：/d;/^当前分支提交结论：/d' \
    "$good_report" |
  awk '
    /^### 控制事件 4：/ { skip=1 }
    /^## 工作区与质量基线$/ { skip=0 }
    !skip { print }
  ' |
    sed -e 's/^当前状态：已完成。$/当前状态：等待当前分支提交批准。/' \
      -e 's/^最终结论：完成。$/最终结论：未完成。/' \
      -e 's/^触发来源：Reviewer 1 审查通过。$/触发来源：Reviewer 1 审查通过并已应用候选差异。/' \
    > "$pending_report"
  sed "s|^预期主分支 HEAD：.*$|预期主分支 HEAD：\`$current_commit\`。|" \
    "$pending_report" > "$pending_head_drift_report"
  sed 's/^批准内容指纹：.*/批准内容指纹：`0000000000000000000000000000000000000000`。/' \
    "$pending_report" > "$pending_fingerprint_mismatch_report"
  printf '%s\n' 'docs/pretty/rush-order/*-execution.md' \
    'docs/superpowers/executions/*' 'stale/' 'global-only/' 'report-worktree/' \
    'batch-main/' 'pending-main/' >> "$test_dir/.git/info/exclude"

  sed '/基线命令：/d;/基线退出码：/d;/基线结论：/d' "$good_report" > "$no_baseline"
  sed '/RED 命令：/d;/RED 退出码：/d;/RED 预期失败：/d;/RED 实际摘要：/d;/等价验证命令：/d;/等价验证退出码：/d' "$good_report" > "$no_red"
  sed '/覆盖率范围：/d;/行覆盖率阈值：/d;/分支覆盖率阈值：/d;/行覆盖率结果：/d;/分支覆盖率结果：/d;/覆盖率报告位置：/d' "$good_report" > "$no_coverage"
  sed '/质量审查范围：/d;/质量发现与修复：/d;/质量复查结果：/d' "$good_report" > "$no_review"
  sed '/功能完整性核对：/d;/简洁性与必要性审查：/d;/可读性与业务表达审查：/d;/测试完整性保护：/d;/变更范围控制：/d' "$good_report" > "$no_implementation_quality"
  sed '/最终回归命令：/d;/最终回归退出码：/d' "$good_report" > "$no_final"
  sed 's/排除项一致性：是/排除项一致性：否/' "$good_report" > "$exclusion_changed"
  sed 's/未闭环项：无/未闭环项：TODO/' "$good_report" > "$placeholder"
  sed '/Plan 批次基线哈希：/d' "$good_report" > "$no_plan_batch_baseline"
  awk '
    /^### 任务 / { task_count++ }
    task_count == 1 && /^Plan 只读复验哈希：/ { next }
    task_count == 1 && /^Plan 只读复验结论：/ { next }
    { print }
  ' "$good_report" > "$no_task_plan_recheck"
  awk '
    /^### 任务 / { task_count++ }
    task_count == 2 && /^Plan 只读复验哈希：/ {
      print "Plan 只读复验哈希：`0000000000000000000000000000000000000000`。"
      next
    }
    { print }
  ' "$good_report" > "$mismatched_task_plan_hash"
  sed 's/^Plan 最终哈希：.*/Plan 最终哈希：`1111111111111111111111111111111111111111`。/' "$good_report" > "$mismatched_final_plan_hash"
  sed '/Worktree 路径：/d;/Worktree 忽略检查：/d;/Worktree 忽略修复：/d' "$good_report" > "$no_worktree_evidence"
  sed 's/^Worktree 路径：.*/Worktree 路径：/' "$good_report" > "$empty_worktree_path"
  awk '
    /^### 执行批次 2：/ {
      print "### 任务 1.1：Plan 变化后错误继续"
      print "任务类型：非行为验证。"
      print "等价验证命令：`git diff --check`。"
      print "等价验证退出码：0。"
      print "Plan 只读复验哈希：`__OLD_PLAN_HASH__`。"
      print "Plan 只读复验结论：通过。"
    }
    { print }
  ' "$good_report" | sed "s/__OLD_PLAN_HASH__/$old_plan_hash/g" > "$continued_after_plan_mismatch"
  sed '/批次结论：阻塞（Plan 内容变化）/d' "$good_report" > "$missing_blocked_batch_conclusion"
  sed 's/Plan 批次批准：重新批准（用户批准记录 B）/Plan 批次批准：未重新批准（用户尚未确认）/' "$good_report" > "$reapproval_not_confirmed"
  sed 's/既有成果复核：通过（任务 1 的代码、测试和报告证据仍符合新 Plan）/既有成果复核：未通过（既有成果尚未复核）/' "$good_report" > "$existing_results_review_failed"
  cp "$good_report" "$stale_current_plan_report"
  mkdir -p "$test_dir/stale/docs/pretty/rush-order"
  printf '%s\n' '# 工单加急 Plan' '版本：报告生成后被擅自修改。' > "$test_dir/stale/docs/pretty/rush-order/2026-07-27-rush-order-plan.md"
  sed "s|^主工作区路径：.*|主工作区路径：\`$test_dir/global-only\`。|" \
    "$good_report" > "$global_ignore_only_report"
  cp "$plan_file" "$global_only_fixture_dir/2026-07-27-rush-order-plan.md"
  cp "$good_report" "$legacy_report"
  cp "$good_report" "$mismatched_topic_report"
  sed 's/^当前状态：已完成。$/当前状态：安全暂停。/' "$good_report" > "$contradictory_status_report"
  sed 's/^状态转换：等待 Review -> 等待当前分支提交批准。$/状态转换：执行中 -> 已完成。/' \
    "$good_report" > "$illegal_transition_report"
  sed '/^Reviewer 1 结论：/d' "$good_report" > "$missing_unit_review_report"
  sed '/^当前分支提交批准：/d' "$good_report" > "$missing_commit_approval_report"
  sed 's/&& git commit -m/\&\& git commit --no-verify -m/' "$good_report" > "$no_verify_commit_report"
  sed '/^环境证据指纹：/d' "$good_report" > "$missing_evidence_fingerprint_report"
  awk -v expected_head="$base_commit" '
    /^预期主分支 HEAD：/ {
      print "预期主分支 HEAD：`" expected_head "`。"
      next
    }
    { print }
  ' "$good_report" > "$mismatched_main_head_report"
  sed -e 's/^当前状态：已完成。$/当前状态：安全暂停。/' \
    -e 's/^当前集成单元：无（全部完成）。$/当前集成单元：U1。/' \
    -e 's/^自动编排状态：停止（执行完成）。$/自动编排状态：停止（安全暂停）。/' \
    -e 's/^状态转换：最终验证中 -> 已完成。$/状态转换：最终验证中 -> 安全暂停。/' \
    -e 's/^最终结论：完成。$/最终结论：未完成。/' \
    -e 's/^未闭环项：无。$/未闭环项：恢复后重新运行最终全量门禁。/' \
    "$good_report" > "$paused_report"
  sed -e 's/^执行模式：单集成单元审批。$/执行模式：一次性执行。/' \
    -e "s|^主工作区路径：.*|主工作区路径：\`$test_dir/batch-main\`。|" \
    -e 's/^主分支：.*$/主分支：`batch-main`。/' \
    -e "s/^预期主分支 HEAD：.*$/预期主分支 HEAD：\`$batch_commit\`。/" \
    -e 's|^Worktree 路径：.*$|Worktree 路径：不适用（一次性模式自测使用独立主工作区）。|' \
    -e "s/^统一 Review 证据指纹：不适用（默认模式逐单元审查）。$/统一 Review 证据指纹：\`$unified_review_fingerprint\`。/" \
    -e 's/^Reviewer 1 结论：通过（独立完成 Plan 符合性与代码质量审查）。$/Reviewer 1 结论：通过（最终统一 Review 已覆盖 Plan 符合性与代码质量）。/' \
    -e 's/^当前分支提交批准：已批准（用户批准记录 C，包含上述提交信息）。$/当前分支提交批准：一次性当前分支提交已批准（用户批准记录 C，包含上述提交信息）。/' \
    -e "s|^候选差异应用前 HEAD：.*$|候选差异应用前 HEAD：\`$base_commit\`。|" \
    -e "s|^候选差异应用后 HEAD：.*$|候选差异应用后 HEAD：\`$base_commit\`。|" \
    -e "s|^批准内容指纹：.*$|批准内容指纹：\`$unit2_tree\`。|" \
    -e "s|^当前分支提交信息：.*$|当前分支提交信息：\`feat: integrate batch units\`。|" \
    -e "s|^当前分支提交命令：.*$|当前分支提交命令：\`git add -- unit-one.txt unit-two.txt && git commit -m 'feat: integrate batch units'\`。|" \
    -e "s|^当前分支提交前 HEAD：.*$|当前分支提交前 HEAD：\`$base_commit\`。|" \
    -e "s|^当前分支提交后 HEAD：.*$|当前分支提交后 HEAD：\`$batch_commit\`。|" \
    -e "s|^当前分支提交：.*$|当前分支提交：\`$batch_commit\`。|" \
    "$good_report" | awk -v base="$base_commit" -v unit_base="$unit_commit" \
      -v candidate="$unit2_commit" -v tree="$unit2_tree" -v mapped_head="$unit2_commit" -v final_head="$batch_commit" \
      -v plan_hash="$plan_hash" -v command_fingerprint="$command_fingerprint" \
      -v dependency_fingerprint="$dependency_fingerprint" -v environment_fingerprint="$environment_fingerprint" \
      -v unified_review="$unified_review_fingerprint" '
      /^## 业务切片质量门禁$/ {
        print "### 集成单元 U2：完成第二个独立单元"
        print "风险等级：低。"
        print "审查策略：单 Reviewer。"
        print "单元基线提交：`" unit_base "`。"
        print "任务候选提交：`" candidate "`。"
        print "集成映射提交：`" candidate "`。"
        print "任务候选树：`" tree "`。"
        print "报告提交隔离：通过（Execution Report 未进入任务候选提交）。"
        print "统一 Review 证据指纹：`" unified_review "`。"
        print "Plan 证据指纹：`" plan_hash "`。"
        print "代码证据指纹：`" candidate "`。"
        print "命令证据指纹：`" command_fingerprint "`。"
        print "依赖证据指纹：`" dependency_fingerprint "`。"
        print "环境证据指纹：`" environment_fingerprint "`。"
        print "验证证据处置：新鲜运行。"
        print "Reviewer 1 结论：通过（最终统一 Review 已覆盖 Plan 符合性与代码质量）。"
        print "Reviewer 2 结论：不适用（低风险单元只需一个独立 Reviewer）。"
        print "Review 驳回历史：无。"
        print "候选差异应用命令：`git diff --binary " base " " mapped_head " | git apply`。"
        print "候选差异应用退出码：0。"
        print "候选差异应用前 HEAD：`" base "`。"
        print "候选差异应用后 HEAD：`" base "`。"
        print "候选差异应用结论：通过。"
        print "批准内容指纹：`" tree "`。"
        print "当前分支提交信息：`feat: integrate batch units`。"
        print "当前分支提交批准：一次性当前分支提交已批准（用户批准记录 C，包含上述提交信息）。"
        print "当前分支提交命令：`git add -- unit-one.txt unit-two.txt && git commit -m feat-integrate-batch-units`。"
        print "当前分支提交退出码：0。"
        print "当前分支提交前 HEAD：`" base "`。"
        print "当前分支提交后 HEAD：`" final_head "`。"
        print "当前分支提交：`" final_head "`。"
        print "当前分支提交结论：通过。"
        print "阶段耗时：实现 4 分钟；验证 1 分钟；Review 等待 1 分钟；差异应用 1 分钟；提交 1 分钟。"
        print "单元结论：通过。"
      }
      { print }
    ' > "$batch_report"
  awk -v mismatch="$dependency_fingerprint" '
    /^统一 Review 证据指纹：/ {
      review_count++
      if (review_count == 2) {
        print "统一 Review 证据指纹：`" mismatch "`。"
        next
      }
    }
    { print }
  ' "$batch_report" > "$batch_review_mismatch_report"
  awk -v drift="$drift_candidate" -v drift_tree="$drift_tree" '
    /^### 集成单元 U2：/ { in_u2=1 }
    in_u2 && /^任务候选提交：/ { print "任务候选提交：`" drift "`。"; next }
    in_u2 && /^任务候选树：/ { print "任务候选树：`" drift_tree "`。"; next }
    { print }
  ' "$batch_report" > "$batch_mapping_drift_report"
  sed -e 's/^风险等级：低。$/风险等级：高。/' \
    -e 's/^审查策略：单 Reviewer。$/审查策略：双 Reviewer。/' \
    -e 's/^Reviewer 2 结论：不适用（低风险单元只需一个独立 Reviewer）。$/Reviewer 2 结论：通过（第二位独立 Reviewer 完成高风险专项审查）。/' \
    "$good_report" > "$high_risk_report"
  awk -v plan_hash="$plan_hash" '
    /^### 执行批次 1：/ { first_batch=1 }
    /^### 执行批次 2：/ { first_batch=0 }
    first_batch && /^Plan 批次基线哈希：/ { print "Plan 批次基线哈希：`" plan_hash "`。"; next }
    first_batch && /^Plan 只读复验哈希：/ { print "Plan 只读复验哈希：`" plan_hash "`。"; next }
    first_batch && /^Plan 只读复验结论：/ { print "Plan 只读复验结论：通过。"; next }
    first_batch && /^批次结论：/ { print "批次结论：阻塞（外部依赖暂时不可用）。"; next }
    /^Plan 批次批准：重新批准（用户批准记录 B）。$/ { print "Plan 批次批准：沿用批准（外部依赖恢复后继续执行）。"; next }
    { print }
  ' "$good_report" > "$non_plan_block_recovered_report"
  sed 's/任务类型：非行为验证。/任务类型：业务行为。/' "$good_report" > "$second_behavior_missing_tdd_report"
  sed 's/行覆盖率结果：90%。/行覆盖率结果：10%。/;s/分支覆盖率结果：80%。/分支覆盖率结果：5%。/' \
    "$good_report" > "$below_threshold_report"
  awk '
    /^### 任务 / { task_count++ }
    task_count == 2 && /^Plan 只读复验哈希：/ {
      print "Plan 只读复验哈希：`0000000000000000000000000000000000000000`。"
      next
    }
    { print }
  ' "$paused_report" > "$paused_stale_hash_report"

  cat > "$early_pause_report" <<EOF
# 工单加急执行报告
## 执行概览
执行批次：首次执行，尚未开始实施。
## 输入与批准
Plan 路径：\`docs/pretty/rush-order/2026-07-27-rush-order-plan.md\`。
## 执行控制
执行模式：单集成单元审批。
当前状态：安全暂停。
当前集成单元：无（尚未开始）。
主工作区路径：\`$test_dir\`。
主分支：\`$main_branch\`。
主分支基线 HEAD：\`$unit_commit\`。
预期主分支 HEAD：\`$unit_commit\`。
工作区洁净检查：通过。
自动编排状态：停止（安全暂停）。
### 控制事件 1：启动前暂停
状态转换：未开始 -> 安全暂停。
触发来源：用户自然语言要求暂停。
恢复入口：重新核对 Plan、主分支和 worktree 后从首个单元开始。
## 工作区与质量基线
Worktree 路径：不适用（暂停发生在创建 worktree 前）。
Worktree 忽略检查：不适用（尚未创建项目内 worktree）。
Worktree 忽略修复：不需要。
基线命令：未运行（暂停发生在基线验证前）。
基线退出码：不适用（命令未运行）。
基线结论：未完成（等待恢复）。
## 执行引擎
执行引擎：不适用（尚未进入实施）。
## 任务执行证据
无（尚未开始任务）。
## 集成单元检查点
无（尚未形成候选提交）。
## 业务切片质量门禁
无（尚未开始实施）。
## 测试覆盖率
无（尚未开始实施）。
## 代码质量审查
无（尚未形成代码差异）。
## 偏差与阻塞
安全暂停不是阻塞；现有文件与 Git 状态均保留。
## 最终全量验证
未运行（执行尚未完成）。
## 授权与 Git 操作
Git 操作：无；未创建提交、未合并、未 push、未创建 MR。
## 最终质量结论
最终结论：未完成。
未闭环项：恢复后执行全部 Plan 集成单元和质量门禁。
EOF

  cat > "$linked_worktree_report" <<EOF
主工作区路径：\`$test_dir\`。
Worktree 路径：\`.worktrees/feature-rush-order\`。
Worktree 忽略检查：通过。
EOF

  for bad_report in "$no_baseline" "$no_red" "$no_coverage" "$no_review" \
    "$no_implementation_quality" "$no_final" "$exclusion_changed" "$placeholder" \
    "$no_plan_batch_baseline" "$no_task_plan_recheck" "$mismatched_task_plan_hash" \
    "$mismatched_final_plan_hash" "$no_worktree_evidence" "$empty_worktree_path" \
    "$continued_after_plan_mismatch" "$missing_blocked_batch_conclusion" \
    "$reapproval_not_confirmed" "$existing_results_review_failed" "$global_ignore_only_report" \
    "$stale_current_plan_report" "$contradictory_status_report" "$illegal_transition_report" \
    "$missing_unit_review_report" "$missing_commit_approval_report" "$no_verify_commit_report" \
    "$missing_evidence_fingerprint_report" "$mismatched_main_head_report"; do
    if validate_report "$bad_report" complete >/dev/null 2>&1; then
      echo "SELF-TEST FAILED: invalid report was accepted: $bad_report" >&2
      return 1
    else
      :
    fi
  done

  if validate_report "$legacy_report" complete >/dev/null 2>&1; then
    echo 'SELF-TEST FAILED: legacy docs/superpowers Execution Report path was accepted' >&2
    return 1
  fi

  if validate_report "$mismatched_topic_report" complete >/dev/null 2>&1; then
    echo 'SELF-TEST FAILED: mismatched Execution Report topic path was accepted' >&2
    return 1
  fi

  if ! validate_report "$good_report" complete; then
    echo 'SELF-TEST FAILED: valid complete report was rejected' >&2
    return 1
  fi
  if ! validate_report "$pending_report" structure; then
    echo 'SELF-TEST FAILED: valid pending current-branch commit report was rejected' >&2
    return 1
  fi
  for invalid_pending_report in "$pending_head_drift_report" "$pending_fingerprint_mismatch_report"; do
    if validate_report "$invalid_pending_report" structure >/dev/null 2>&1; then
      echo "SELF-TEST FAILED: invalid pending current-branch commit report was accepted: $invalid_pending_report" >&2
      return 1
    fi
  done
  git -C "$pending_main" add unit-one.txt || return 1
  if validate_report "$pending_report" structure >/dev/null 2>&1; then
    echo 'SELF-TEST FAILED: staged pending current-branch workspace was accepted' >&2
    return 1
  fi
  git -C "$pending_main" reset -q || return 1

  if ! validate_report "$paused_report" structure; then
    echo 'SELF-TEST FAILED: valid safe-pause report was rejected' >&2
    return 1
  fi
  if ! validate_report "$early_pause_report" structure; then
    echo 'SELF-TEST FAILED: valid pre-task safe-pause report was rejected' >&2
    return 1
  fi
  if validate_report "$paused_report" complete >/dev/null 2>&1; then
    echo 'SELF-TEST FAILED: safe-pause report was accepted as complete' >&2
    return 1
  fi
  if validate_report "$paused_stale_hash_report" structure >/dev/null 2>&1; then
    echo 'SELF-TEST FAILED: stale Plan evidence in a paused report was accepted' >&2
    return 1
  fi

  for valid_complete_report in "$batch_report" "$high_risk_report"; do
    if ! validate_report "$valid_complete_report" complete; then
      echo "SELF-TEST FAILED: valid execution mode or risk review was rejected: $valid_complete_report" >&2
      return 1
    fi
  done
  if ! validate_report "$non_plan_block_recovered_report" complete; then
    echo 'SELF-TEST FAILED: a recovered non-Plan blocking batch was rejected' >&2
    return 1
  fi
  for invalid_semantic_report in "$second_behavior_missing_tdd_report" "$below_threshold_report" \
    "$batch_review_mismatch_report" "$batch_mapping_drift_report"; do
    if validate_report "$invalid_semantic_report" complete >/dev/null 2>&1; then
      echo "SELF-TEST FAILED: invalid per-task or coverage evidence was accepted: $invalid_semantic_report" >&2
      return 1
    fi
  done

  if ! validate_worktree_contract "$linked_worktree_report"; then
    echo 'SELF-TEST FAILED: report in a linked worktree did not use the main workspace ignore contract' >&2
    return 1
  fi
  if validate_main_workspace_state "$test_dir/global-only"; then
    echo 'SELF-TEST FAILED: unrelated dirty workspace state was accepted' >&2
    return 1
  fi

  git -C "$test_dir" add -f docs/pretty/rush-order/2026-07-28-rush-order-execution.md || return 1
  git -C "$test_dir" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'docs: archive execution evidence' || return 1
  if ! validate_report "$good_report" complete; then
    echo 'SELF-TEST FAILED: archived report-only evidence commit could not be revalidated' >&2
    return 1
  fi
  printf '%s\n' 'unrelated evidence drift' > "$test_dir/unrelated.txt"
  git -C "$test_dir" add unrelated.txt || return 1
  git -C "$test_dir" -c user.name='Pretty Self Test' -c user.email='pretty@example.invalid' \
    commit -q -m 'test: add unrelated drift' || return 1
  if validate_report "$good_report" complete >/dev/null 2>&1; then
    echo 'SELF-TEST FAILED: unrelated commit after report evidence was accepted' >&2
    return 1
  fi

  echo 'SELF-TEST PASS: positive and negative execution reports behaved as expected'
}

if [ "$#" -eq 1 ] && [ "$1" = '--self-test' ]; then
  run_self_test
  exit $?
fi

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  usage
  exit 2
fi

report_file=$1
completion_mode=structure
if [ "$#" -eq 2 ]; then
  if [ "$2" != '--require-complete' ]; then
    usage
    exit 2
  fi
  completion_mode=complete
fi

if [ ! -f "$report_file" ]; then
  echo "ERROR: execution report does not exist: $report_file" >&2
  exit 2
fi

validate_report "$report_file" "$completion_mode"
