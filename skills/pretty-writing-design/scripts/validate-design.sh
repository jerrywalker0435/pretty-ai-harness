#!/usr/bin/env bash

set -u

usage() { echo "Usage: validate-design.sh <design-file> | --self-test" >&2; }

validate_design_path() {
  design_file=$1
  case "$design_file" in
    docs/pretty/*/*) relative_path=${design_file#docs/pretty/} ;;
    */docs/pretty/*/*) relative_path=${design_file#*/docs/pretty/} ;;
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
  printf '%s\n' "$file_name" | grep -Eq "^[0-9]{4}-[0-9]{2}-[0-9]{2}-${topic}-design\\.md$"
}

validate_document_contract() {
  document_design=$1
  awk '
    function fail(message) {
      print "ERROR: " message > "/dev/stderr"
      failures++
    }

    BEGIN {
      section_order = "设计目标与范围|仓库现状与约束|方案比较与决策|领域模型与业务规则|" \
        "架构与职责边界|数据流与边界契约|数据模型与持久化|异常、一致性与并发|" \
        "兼容性、迁移与回滚|安全、性能与可观测性|测试策略|风险与非目标|" \
        "计划交接约束|需求追溯|设计生成质量审查|设计批准记录"
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
      if (section_count != expected_count) fail("Design 必须且只能包含约定的 " expected_count " 个顶级章节")
      exit failures > 0 ? 1 : 0
    }
  ' "$document_design"
}

validate() {
  design_file=$1
  failures=0
  require() { if ! grep -Eiq -- "$1" "$design_file"; then echo "ERROR: $2" >&2; failures=$((failures + 1)); fi; }
  reject() { if grep -Eiq -- "$1" "$design_file"; then echo "ERROR: $2" >&2; failures=$((failures + 1)); fi; }
  require_min_threshold() {
    metric=$1
    minimum=$2
    if ! awk -v metric="$metric" -v minimum="$minimum" '
      {
        segment_count = split($0, segments, /[，,；;。]/)
        for (i = 1; i <= segment_count; i++) {
          if (index(segments[i], metric) && match(segments[i], /[0-9]+%/)) {
            threshold = substr(segments[i], RSTART, RLENGTH - 1) + 0
            if (threshold >= minimum && threshold <= 100) found = 1
          }
        }
      }
      END { exit(found ? 0 : 1) }
    ' "$design_file"; then
      echo "ERROR: 缺少不低于 ${minimum}% 的${metric}阈值" >&2
      failures=$((failures + 1))
    fi
  }

  if ! validate_design_path "$design_file"; then
    echo "ERROR: Design 路径必须匹配 docs/pretty/<topic>/YYYY-MM-DD-<topic>-design.md，且两个 <topic> 必须是相同的小写 kebab-case" >&2
    failures=$((failures + 1))
  fi
  if ! validate_document_contract "$design_file"; then
    failures=$((failures + 1))
  fi

  require '^# .+设计$' '缺少中文设计标题'
  require '需求/验收编号.*需求摘要.*设计决策.*涉及边界.*验证方式' '需求追溯表字段不完整'
  require '方案一|方案 1|方案 A' '缺少第一个候选方案'
  require '方案二|方案 2|方案 B' '缺少第二个候选方案'
  require '推荐|决策理由|权衡' '缺少方案推荐或权衡依据'
  require '单元测试|集成测试|契约测试|端到端测试' '缺少测试分层策略'
  require '核心行为|行为矩阵' '缺少核心行为矩阵'
  require_min_threshold '行覆盖率' 80
  require_min_threshold '分支覆盖率' 70
  require '排除' '缺少覆盖率排除原则'
  require '分节批准|章节批准' '缺少分节批准记录'
  require '整体批准' '缺少整体批准记录'
  reject 'TODO|TBD|待补充|待定|\.\.\.|……' '存在占位符或省略内容'
  reject '未使用的候选 Skill 及原因' '包含无信息量的未使用 Skill 清单'
  reject '^# .*\b(Design|Technical Design)\b|^## (Goal|Architecture|Testing Strategy|Approval)' '存在英文设计模板标题'
  return "$failures"
}

self_test() {
  test_dir=$(mktemp -d "${TMPDIR:-/tmp}/pretty-writing-design.XXXXXX") || exit 2
  trap 'rm -rf -- "$test_dir"' EXIT INT TERM
  fixture_dir="$test_dir/docs/pretty/rush-order"
  legacy_dir="$test_dir/docs/superpowers/specs"
  mkdir -p "$fixture_dir" "$legacy_dir"
  good="$fixture_dir/2026-07-28-rush-order-design.md"
  english="$fixture_dir/2026-07-29-rush-order-design.md"
  trace="$fixture_dir/2026-07-30-rush-order-design.md"
  options="$fixture_dir/2026-07-31-rush-order-design.md"
  testing="$fixture_dir/2026-08-01-rush-order-design.md"
  approval="$fixture_dir/2026-08-02-rush-order-design.md"
  todo="$fixture_dir/2026-08-03-rush-order-design.md"
  stricter_threshold="$fixture_dir/2026-08-05-rush-order-design.md"
  weak_threshold="$fixture_dir/2026-08-06-rush-order-design.md"
  wrong_order="$fixture_dir/2026-08-07-rush-order-design.md"
  unused_skill_list="$fixture_dir/2026-08-08-rush-order-design.md"
  legacy="$legacy_dir/2026-07-28-rush-order-design.md"
  mismatched_topic="$fixture_dir/2026-08-04-other-design.md"
  cat > "$good" <<'EOF'
# 工单加急设计
## 设计目标与范围
支持既有工单加急。
## 仓库现状与约束
沿用既有端口。
## 方案比较与决策
方案一：同步编排。方案二：异步编排。权衡后推荐方案一，决策理由是契约稳定。
## 领域模型与业务规则
不改变工单状态。
## 架构与职责边界
应用层编排，领域层定义规则。
## 数据流与边界契约
事件进入应用层后调用端口。
## 数据模型与持久化
不新增表。
## 异常、一致性与并发
按事件编号幂等。
## 兼容性、迁移与回滚
保持原流程兼容。
## 安全、性能与可观测性
记录事件编号和状态。
## 测试策略
单元测试覆盖规则，集成测试覆盖端口，契约测试覆盖消息，端到端测试不适用。核心行为矩阵覆盖主流程、异常和幂等。变更业务代码行覆盖率不低于 80%，分支覆盖率不低于 70%。排除无行为 DTO 和生成访问器。
## 风险与非目标
不改造原状态机。
## 计划交接约束
计划需给出具体命令和报告位置。
## 需求追溯
| 需求/验收编号 | 需求摘要 | 设计决策 | 涉及边界 | 验证方式 |
|---|---|---|---|---|
| R1 | 工单加急 | 附加编排 | 应用与适配层 | 行为测试 |
## 设计生成质量审查
已使用架构审查，未发现阻塞问题。
## 设计批准记录
章节批准：全部章节已确认。整体批准：用户已确认。
EOF
  cp "$good" "$english"; sed -i.bak '1s/.*/# Rush Technical Design/' "$english"
  cp "$good" "$trace"; sed -i.bak '/需求\/验收编号/d' "$trace"
  cp "$good" "$options"; sed -i.bak 's/方案二/备选/' "$options"
  cp "$good" "$testing"; sed -i.bak '/单元测试覆盖规则/d' "$testing"
  cp "$good" "$approval"; sed -i.bak '/章节批准/d' "$approval"
  cp "$good" "$todo"; printf '\nTODO\n' >> "$todo"
  cp "$good" "$stricter_threshold"
  sed -i.bak 's/行覆盖率不低于 80%/行覆盖率不低于 90%/;s/分支覆盖率不低于 70%/分支覆盖率不低于 80%/' "$stricter_threshold"
  cp "$good" "$weak_threshold"
  sed -i.bak 's/行覆盖率不低于 80%/行覆盖率不低于 70%/;s/分支覆盖率不低于 70%/分支覆盖率不低于 60%/' "$weak_threshold"
  cp "$good" "$wrong_order"
  sed -i.bak -e 's/^## 设计目标与范围$/## 临时章节/' \
    -e 's/^## 仓库现状与约束$/## 设计目标与范围/' \
    -e 's/^## 临时章节$/## 仓库现状与约束/' "$wrong_order"
  cp "$good" "$unused_skill_list"
  sed -i.bak '/^## 设计批准记录$/i\
**未使用的候选 Skill 及原因：** 无。' "$unused_skill_list"
  cp "$good" "$legacy"
  cp "$good" "$mismatched_topic"
  for bad in "$english" "$trace" "$options" "$testing" "$approval" "$todo" "$weak_threshold" "$wrong_order" "$unused_skill_list"; do
    if validate "$bad" >/dev/null 2>&1; then echo "SELF-TEST FAILED: invalid content fixture was accepted: $bad" >&2; return 1; fi
  done
  if validate "$legacy" >/dev/null 2>&1; then echo 'SELF-TEST FAILED: legacy docs/superpowers Design path was accepted' >&2; return 1; fi
  if validate "$mismatched_topic" >/dev/null 2>&1; then echo 'SELF-TEST FAILED: mismatched Design topic path was accepted' >&2; return 1; fi
  if ! validate "$stricter_threshold" >/dev/null; then echo 'SELF-TEST FAILED: stricter coverage thresholds were rejected' >&2; return 1; fi
  validate "$good" || { echo 'SELF-TEST FAILED: valid fixture was rejected' >&2; return 1; }
  echo 'SELF-TEST PASS: positive and negative fixtures behaved as expected'
}

if [ "$#" -eq 1 ] && [ "$1" = '--self-test' ]; then self_test; exit $?; fi
if [ "$#" -ne 1 ]; then usage; exit 2; fi
if [ ! -f "$1" ]; then echo "ERROR: design file does not exist: $1" >&2; exit 2; fi
validate "$1"
