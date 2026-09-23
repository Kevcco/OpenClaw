#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:${WEB_PORT:-8080}}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

wait_health() {
  for _ in $(seq 1 30); do
    body="$(curl -fsS "$BASE_URL/health" 2>/dev/null || true)"
    if [[ "$body" == *'"status":"ok"'* ]]; then
      echo "PASS health: $body"
      return 0
    fi
    sleep 2
  done
  echo "FAIL health: $BASE_URL/health" >&2
  exit 1
}

login_and_check() {
  local username="$1"
  local password="$2"
  local jar="$WORK_DIR/${username}.cookies"
  curl -fsS -o /dev/null -c "$jar" \
    --data-urlencode "username=$username" \
    --data-urlencode "password=$password" \
    "$BASE_URL/login"
  local me
  me="$(curl -fsS -b "$jar" "$BASE_URL/api/me")"
  python3 -c 'import json,sys; assert json.load(sys.stdin)["username"] == sys.argv[1]' "$username" <<<"$me"
  echo "PASS login: $me"
}

wait_health
login_and_check teacher_a teacher_a_pass
login_and_check student_a1 student_a1_pass
login_and_check student_b1 student_b1_pass

teacher_jar="$WORK_DIR/teacher_a.cookies"
student_a_jar="$WORK_DIR/student_a1.cookies"
student_b_jar="$WORK_DIR/student_b1.cookies"
teacher_materials="$(curl -fsS -b "$teacher_jar" "$BASE_URL/api/materials")"
student_a_materials="$(curl -fsS -b "$student_a_jar" "$BASE_URL/api/materials")"
student_b_materials="$(curl -fsS -b "$student_b_jar" "$BASE_URL/api/materials")"
python3 -c 'import json,sys; assert any("A班" in x["title"] for x in json.load(sys.stdin)["materials"])' <<<"$teacher_materials"
python3 -c 'import json,sys; assert any("A班" in x["title"] for x in json.load(sys.stdin)["materials"])' <<<"$student_a_materials"
python3 -c 'import json,sys; assert any("B班" in x["title"] for x in json.load(sys.stdin)["materials"])' <<<"$student_b_materials"
echo "PASS class isolation: A and B lists contain their own seed materials"

title="Compose验收-$(date +%s)"
printf '# Compose verification\nThis material verifies upload and persistence.\n' > "$WORK_DIR/compose-check.md"
upload="$(curl -fsS -b "$teacher_jar" \
  -F "title=$title" \
  -F "file=@$WORK_DIR/compose-check.md;type=text/markdown" \
  "$BASE_URL/api/materials/upload")"
material_id="$(printf '%s' "$upload" | python3 -c 'import json,sys; print(json.load(sys.stdin)["material_id"])')"
echo "PASS teacher upload: material_id=$material_id"

student_upload_status="$(curl -sS -o "$WORK_DIR/student-upload.json" -w '%{http_code}' \
  -b "$student_a_jar" \
  -F "file=@$WORK_DIR/compose-check.md;type=text/markdown" \
  "$BASE_URL/api/materials/upload")"
[[ "$student_upload_status" == "403" ]]
echo "PASS student upload rejected: HTTP 403"

b_material_id="$(printf '%s' "$student_b_materials" | python3 -c 'import json,sys; print(next(item["id"] for item in json.load(sys.stdin)["materials"] if "B班" in item["title"]))')"
cross_status="$(curl -sS -o "$WORK_DIR/cross-class.json" -w '%{http_code}' -b "$teacher_jar" "$BASE_URL/api/materials/$b_material_id")"
[[ "$cross_status" == "404" ]]
echo "PASS cross-class access rejected: HTTP 404"

echo "INFO restarting Compose without removing volumes"
docker compose down
docker compose up -d
wait_health
login_and_check teacher_a teacher_a_pass
teacher_jar="$WORK_DIR/teacher_a.cookies"
after_restart="$(curl -fsS -b "$teacher_jar" "$BASE_URL/api/materials")"
python3 -c 'import json,sys; assert any(sys.argv[1] == x["title"] for x in json.load(sys.stdin)["materials"])' "$title" <<<"$after_restart"
echo "PASS persistence: uploaded material remains after down/up"

echo "Compose verification completed successfully."
