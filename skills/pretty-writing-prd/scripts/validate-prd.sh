#!/usr/bin/env bash

set -u

usage() {
  echo "用法: validate-prd.sh <prd-file> | --self-test" >&2
}

validate_prd_path() {
  prd_file=$1
  case "$prd_file" in
    docs/pretty/*/*) relative_path=${prd_file#docs/pretty/} ;;
    */docs/pretty/*/*) relative_path=${prd_file#*/docs/pretty/} ;;
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
  printf '%s\n' "$file_name" | grep -Eq "^[0-9]{4}-[0-9]{2}-[0-9]{2}-${topic}-prd\\.md$"
}

validate_document_contract() {
  document_prd=$1
  awk '
    function fail(message) {
      print "ERROR: " message > "/dev/stderr"
      failures++
    }

    BEGIN {
      section_order = "问题陈述|解决方案|用户故事|实施决策|测试决策|非目标|补充说明|验收标准"
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
        fail("PRD 必须且只能包含约定的 " expected_count " 个顶级章节")
      }
      exit failures > 0 ? 1 : 0
    }
  ' "$document_prd"
}

validate_prd() {
  prd_file=$1

  if [ ! -f "$prd_file" ]; then
    echo "ERROR: PRD 文件不存在: $prd_file" >&2
    return 2
  fi

  if ! validate_prd_path "$prd_file"; then
    echo "ERROR: PRD 路径必须匹配 docs/pretty/<topic>/YYYY-MM-DD-<topic>-prd.md，且两个 <topic> 必须是相同的小写 kebab-case" >&2
    return 1
  fi

  failures=0

  if ! validate_document_contract "$prd_file"; then
    failures=$((failures + 1))
  fi

  require_heading() {
    heading=$1
    if ! grep -Fqx -- "## $heading" "$prd_file"; then
      echo "ERROR: 缺少必需章节: $heading" >&2
      failures=$((failures + 1))
      return
    fi

    if ! awk -v target="## $heading" '
      $0 == target { in_section=1; next }
      /^## / && in_section { exit }
      in_section && $0 !~ /^[[:space:]]*$/ { found=1 }
      END { exit(found ? 0 : 1) }
    ' "$prd_file"; then
      echo "ERROR: 必需章节为空: $heading" >&2
      failures=$((failures + 1))
    fi
  }

  for heading in \
    "问题陈述" \
    "解决方案" \
    "用户故事" \
    "实施决策" \
    "测试决策" \
    "非目标" \
    "补充说明" \
    "验收标准"
  do
    require_heading "$heading"
  done

  if ! awk '
    /^## 补充说明$/ { in_supplement=1; next }
    /^## / && in_supplement { exit }
    in_supplement && /^### 领域上下文同步$/ { found=1 }
    END { exit(found ? 0 : 1) }
  ' "$prd_file"; then
    echo "ERROR: 补充说明缺少“领域上下文同步”记录" >&2
    failures=$((failures + 1))
  fi

  require_context_field() {
    field_name=$1
    if ! awk -v field="$field_name" '
      /^## 补充说明$/ { in_supplement=1; next }
      /^## / && in_supplement { exit }
      in_supplement && /^### 领域上下文同步$/ { in_context=1; next }
      /^### / && in_context { exit }
      in_context && $0 ~ "^[[:space:]]*-[[:space:]]*" field "[：:][[:space:]]*[^[:space:]].*$" { found=1 }
      END { exit(found ? 0 : 1) }
    ' "$prd_file"; then
      echo "ERROR: 领域上下文同步缺少有效字段: $field_name" >&2
      failures=$((failures + 1))
    fi
  }

  require_context_field "Context 文件"
  require_context_field "新增或修订术语"
  require_context_field "用户批准记录"
  require_context_field "ADR"

  if grep -Eq -- '^[[:space:]]*-[[:space:]]*用户批准记录[：:][[:space:]]*(无|不适用)([，,。.]|[[:space:]]|$)' "$prd_file"; then
    echo "ERROR: 领域上下文同步的用户批准记录不能为无或不适用" >&2
    failures=$((failures + 1))
  fi

  if awk '
    /^[[:space:]]*-[[:space:]]*Context 文件[：:][[:space:]]*不适用/ && $0 !~ /原因[：:][[:space:]]*[^[:space:]]/ { invalid=1 }
    END { exit(invalid ? 0 : 1) }
  ' "$prd_file"; then
    echo "ERROR: Context 文件不适用时必须写明原因" >&2
    failures=$((failures + 1))
  fi

  if awk '
    /^[[:space:]]*-[[:space:]]*ADR[：:][[:space:]]*无/ && $0 !~ /原因[：:][[:space:]]*[^[:space:]]/ { invalid=1 }
    END { exit(invalid ? 0 : 1) }
  ' "$prd_file"; then
    echo "ERROR: ADR 为无时必须写明原因" >&2
    failures=$((failures + 1))
  fi

  if grep -Eiq -- '(^|[^[:alnum:]_])(TODO|TBD|FIXME|PLACEHOLDER)([^[:alnum:]_]|$)' "$prd_file"; then
    echo "ERROR: 包含未解决的占位符" >&2
    failures=$((failures + 1))
  fi

  if grep -Fq -- 'ready-for-agent' "$prd_file"; then
    echo "ERROR: 包含外部 Issue Tracker 标签指令" >&2
    failures=$((failures + 1))
  fi

  if ! awk '
    /^## 用户故事$/ { in_section=1; next }
    /^## / && in_section { exit }
    in_section && /^[[:space:]]*[0-9]+\.[[:space:]]+/ {
      story_count++
      if ($0 !~ /^[[:space:]]*[0-9]+\.[[:space:]]+作为(一名|一位|一个)?[^，]+，我希望.+，以便.+[。.]$/) {
        invalid=1
      }
    }
    in_section {
      lower=tolower($0)
      if (lower ~ /as an? / || lower ~ /i want/ || lower ~ /so that/) invalid=1
    }
    END { exit(story_count > 0 && !invalid ? 0 : 1) }
  ' "$prd_file"; then
    echo "ERROR: 用户故事章节中的每个编号条目都必须采用完整中文“角色—能力—收益”格式" >&2
    failures=$((failures + 1))
  fi

  if ! awk '
    /^## 验收标准$/ { in_section=1; next }
    /^## / && in_section { exit }
    in_section && /^[[:space:]]*[0-9]+\.[[:space:]]+[^[:space:]]/ { found=1 }
    END { exit(found ? 0 : 1) }
  ' "$prd_file"; then
    echo "ERROR: 验收标准必须包含编号条目" >&2
    failures=$((failures + 1))
  fi

  if [ "$failures" -ne 0 ]; then
    echo "FAILED: $failures 项机械 PRD 质量检查失败" >&2
    return 1
  fi

  echo "PASS: 中文 PRD 机械质量门禁通过"
}

run_self_test() {
  test_dir=$(mktemp -d "${TMPDIR:-/tmp}/pretty-writing-prd.XXXXXX") || exit 2
  fixture_dir="$test_dir/docs/pretty/sample"
  legacy_dir="$test_dir/docs/superpowers/prd"
  good_prd="$fixture_dir/2026-07-28-sample-prd.md"
  english_story_prd="$fixture_dir/2026-07-29-sample-prd.md"
  incomplete_story_prd="$fixture_dir/2026-07-30-sample-prd.md"
  mixed_story_prd="$fixture_dir/2026-08-07-sample-prd.md"
  placeholder_prd="$fixture_dir/2026-07-31-sample-prd.md"
  missing_context_sync_prd="$fixture_dir/2026-08-01-sample-prd.md"
  missing_context_file_prd="$fixture_dir/2026-08-02-sample-prd.md"
  missing_context_terms_prd="$fixture_dir/2026-08-03-sample-prd.md"
  missing_context_approval_prd="$fixture_dir/2026-08-04-sample-prd.md"
  missing_adr_prd="$fixture_dir/2026-08-05-sample-prd.md"
  legacy_prd="$legacy_dir/2026-07-28-sample-prd.md"
  mismatched_topic_prd="$fixture_dir/2026-08-06-other-prd.md"
  wrong_order_prd="$fixture_dir/2026-08-08-sample-prd.md"
  duplicate_section_prd="$fixture_dir/2026-08-09-sample-prd.md"
  extra_section_prd="$fixture_dir/2026-08-10-sample-prd.md"
  mkdir -p "$fixture_dir" "$legacy_dir"

  cleanup_self_test() {
    rm -rf -- "$test_dir"
  }
  trap cleanup_self_test EXIT INT TERM

  write_fixture() {
    target_file=$1
    story=$2
    problem=$3
    cat > "$target_file" <<EOF
# 示例 PRD

## 问题陈述
$problem
## 解决方案
提供已批准的稳定结果。
## 用户故事
$story
## 实施决策
- 保持公开契约不变。
## 测试决策
- 通过公开入口验证行为。
## 非目标
- 不相关的变更。
## 补充说明
### 领域上下文同步

- Context 文件：\`CONTEXT.md\`
- 新增或修订术语：无
- 用户批准记录：用户已批准完整需求方案，并确认无领域语言变化。
- ADR：无，原因：不存在难以逆转且具有真实权衡的决策。
## 验收标准
1. 公开入口返回已批准的结果。
EOF
  }

  write_fixture "$good_prd" \
    "1. 作为一名用户，我希望获得稳定结果，以便完成工作。" \
    "用户当前无法获得稳定结果。"
  write_fixture "$english_story_prd" \
    "1. As a user, I want a stable result, so that I can finish my work." \
    "用户当前无法获得稳定结果。"
  write_fixture "$incomplete_story_prd" \
    "1. 作为一名用户，我希望获得稳定结果。" \
    "用户当前无法获得稳定结果。"
  write_fixture "$mixed_story_prd" \
    "1. 作为一名用户，我希望获得稳定结果，以便完成工作。
2. 作为管理员，我希望查看结果。" \
    "用户当前无法获得稳定结果。"
  write_fixture "$placeholder_prd" \
    "1. 作为一名用户，我希望获得稳定结果，以便完成工作。" \
    "TODO: 稍后确定。"

  cp "$good_prd" "$legacy_prd"
  cp "$good_prd" "$mismatched_topic_prd"
  cp "$good_prd" "$wrong_order_prd"
  sed -i.bak -e 's/^## 问题陈述$/## 临时章节/' \
    -e 's/^## 解决方案$/## 问题陈述/' \
    -e 's/^## 临时章节$/## 解决方案/' "$wrong_order_prd"
  cp "$good_prd" "$duplicate_section_prd"
  printf '\n## 问题陈述\n重复章节。\n' >> "$duplicate_section_prd"
  cp "$good_prd" "$extra_section_prd"
  printf '\n## 临时章节\n不应出现的顶级章节。\n' >> "$extra_section_prd"

  awk '
    $0 == "### 领域上下文同步" { skip=1; next }
    skip && /^## / { skip=0 }
    !skip { print }
  ' "$good_prd" > "$missing_context_sync_prd"
  sed '/Context 文件：/d' "$good_prd" > "$missing_context_file_prd"
  sed '/新增或修订术语：/d' "$good_prd" > "$missing_context_terms_prd"
  sed '/用户批准记录：/d' "$good_prd" > "$missing_context_approval_prd"
  sed '/ADR：/d' "$good_prd" > "$missing_adr_prd"

  if ! validate_prd "$good_prd" >/dev/null; then
    echo "SELF-TEST FAILED: 合法中文 PRD 被拒绝" >&2
    return 1
  fi
  if validate_prd "$legacy_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 旧 docs/superpowers PRD 路径被接受" >&2
    return 1
  fi
  if validate_prd "$mismatched_topic_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 目录与文件名 topic 不一致的 PRD 被接受" >&2
    return 1
  fi
  if validate_prd "$english_story_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 英文用户故事被接受" >&2
    return 1
  fi
  if validate_prd "$incomplete_story_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 缺少收益的用户故事被接受" >&2
    return 1
  fi
  if validate_prd "$mixed_story_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 合法故事掩盖了同章节中的残缺故事" >&2
    return 1
  fi
  if validate_prd "$placeholder_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 含占位符的 PRD 被接受" >&2
    return 1
  fi
  for invalid_structure_prd in "$wrong_order_prd" "$duplicate_section_prd" "$extra_section_prd"; do
    if validate_prd "$invalid_structure_prd" >/dev/null 2>&1; then
      echo "SELF-TEST FAILED: 章节顺序、重复或额外章节错误的 PRD 被接受: $invalid_structure_prd" >&2
      return 1
    fi
  done

  if validate_prd "$missing_context_sync_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 缺少领域上下文同步记录的 PRD 被接受" >&2
    return 1
  fi
  if validate_prd "$missing_context_file_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 缺少 Context 文件记录的 PRD 被接受" >&2
    return 1
  fi
  if validate_prd "$missing_context_terms_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 缺少领域术语变化记录的 PRD 被接受" >&2
    return 1
  fi
  if validate_prd "$missing_context_approval_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 缺少领域上下文批准记录的 PRD 被接受" >&2
    return 1
  fi
  if validate_prd "$missing_adr_prd" >/dev/null 2>&1; then
    echo "SELF-TEST FAILED: 缺少 ADR 结论的 PRD 被接受" >&2
    return 1
  fi

  echo "SELF-TEST PASS: 中文正例与故事、占位符、领域上下文记录反例均符合预期"
}

if [ "$#" -eq 1 ] && [ "$1" = "--self-test" ]; then
  run_self_test
  exit $?
fi

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

validate_prd "$1"
