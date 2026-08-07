#!/usr/bin/env sh
set -eu

usage() {
  echo "Usage: run-coverage.sh --project-dir <path>" >&2
  exit 2
}

project_dir=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-dir)
      [ "$#" -ge 2 ] || usage
      project_dir=$2
      shift 2
      ;;
    *) usage ;;
  esac
done

[ -n "$project_dir" ] || usage
[ -d "$project_dir" ] || {
  echo "ERROR: project directory not found: $project_dir" >&2
  exit 2
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$project_dir" && pwd)
jacoco_version=0.8.13

if [ -f "$project_dir/pom.xml" ]; then
  if [ -x "$project_dir/mvnw" ]; then
    maven_command=./mvnw
  elif command -v mvn >/dev/null 2>&1; then
    maven_command=mvn
  else
    echo "ERROR: Maven project found but neither ./mvnw nor mvn is available" >&2
    exit 2
  fi
  (
    cd "$project_dir"
    "$maven_command" \
      "org.jacoco:jacoco-maven-plugin:$jacoco_version:prepare-agent" \
      test \
      "org.jacoco:jacoco-maven-plugin:$jacoco_version:report"
  )
elif [ -f "$project_dir/build.gradle" ] || [ -f "$project_dir/build.gradle.kts" ]; then
  if [ -x "$project_dir/gradlew" ]; then
    gradle_command=./gradlew
  elif command -v gradle >/dev/null 2>&1; then
    gradle_command=gradle
  else
    echo "ERROR: Gradle project found but neither ./gradlew nor gradle is available" >&2
    exit 2
  fi
  (
    cd "$project_dir"
    "$gradle_command" -I "$script_dir/../assets/jacoco.init.gradle" \
      test jacocoTestReport
  )
else
  echo "ERROR: no Maven or Gradle build found in $project_dir" >&2
  exit 2
fi

reports=$(find "$project_dir" -type f \
  \( -path '*/target/site/jacoco/jacoco.xml' \
     -o -path '*/build/reports/jacoco/test/jacocoTestReport.xml' \) \
  -print | sort)

[ -n "$reports" ] || {
  echo "ERROR: coverage command completed but no JaCoCo XML report was found" >&2
  exit 2
}

echo "$reports"
