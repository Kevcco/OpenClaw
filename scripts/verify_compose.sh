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

token_file() {
  printf '%s/%s.token' "$WORK_DIR" "$1"
}

auth_header() {
  local token
  token="$(cat "$(token_file "$1")")"
  printf 'Authorization: Bearer %s' "$token"
}

login_and_check() {
  local username="$1"
  local password="$2"
  local header_file="$WORK_DIR/${username}.headers"
  local response
  response="$(curl -fsS -D "$header_file" \
    -H 'Content-Type: application/json' \
    --data "{\"username\":\"$username\",\"password\":\"$password\"}" \
    "$BASE_URL/login")"
  if grep -qi '^Set-Cookie:' "$header_file"; then
    echo "FAIL login set an authentication cookie" >&2
    exit 1
  fi
  local token
  token="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
  printf '%s' "$token" > "$(token_file "$username")"
  local me
  me="$(curl -fsS -H "$(auth_header "$username")" "$BASE_URL/api/me")"
  python3 -c 'import json,sys; assert json.load(sys.stdin)["username"] == sys.argv[1]' "$username" <<<"$me"
  echo "PASS login: $me"
}

assert_search() {
  local username="$1"
  local query="$2"
  local mode="$3"
  local expected_title="$4"
  local response
  response="$(curl -fsS -G -H "$(auth_header "$username")" \
    --data-urlencode "q=$query" \
    --data-urlencode "mode=$mode" \
    --data-urlencode "limit=10" \
    "$BASE_URL/api/knowledge/search")"
  python3 -c 'import json,sys
payload=json.load(sys.stdin)
assert payload["mode"] == sys.argv[1]
assert payload["hits"], payload
assert any(sys.argv[2] in hit["source"]["title"] for hit in payload["hits"]), payload
for hit in payload["hits"]:
    source=hit["source"]
    assert source["preview_url"].startswith("/api/materials/")
    assert source["download_url"].startswith("/api/materials/")
    assert hit["snippet"]
if sys.argv[1] == "vector":
    assert all(hit.get("score", 0) >= 0.35 for hit in payload["hits"])
' "$mode" "$expected_title" <<<"$response"
  echo "PASS search $mode: $query"
}

wait_health
login_and_check teacher_a teacher_a_pass
login_and_check student_a1 student_a1_pass
login_and_check student_b1 student_b1_pass

teacher_materials="$(curl -fsS -H "$(auth_header teacher_a)" "$BASE_URL/api/materials")"
student_a_materials="$(curl -fsS -H "$(auth_header student_a1)" "$BASE_URL/api/materials")"
student_b_materials="$(curl -fsS -H "$(auth_header student_b1)" "$BASE_URL/api/materials")"
python3 -c 'import json,sys; assert any("A班" in x["title"] for x in json.load(sys.stdin)["materials"])' <<<"$teacher_materials"
python3 -c 'import json,sys; assert any("A班" in x["title"] for x in json.load(sys.stdin)["materials"])' <<<"$student_a_materials"
python3 -c 'import json,sys; assert any("B班" in x["title"] for x in json.load(sys.stdin)["materials"])' <<<"$student_b_materials"
echo "PASS class isolation: A and B lists contain their own seed materials"

assert_search student_a1 "一次函数" keyword "A班"
assert_search student_a1 "一次函数" vector "A班"
assert_search student_a1 "一次函数" hybrid "A班"

cross_search="$(curl -fsS -G -H "$(auth_header student_a1)" \
  --data-urlencode 'q=几何图形' \
  --data-urlencode 'mode=keyword' \
  "$BASE_URL/api/knowledge/search")"
python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload["hits"] == []; assert "B班" not in json.dumps(payload, ensure_ascii=False)' <<<"$cross_search"
echo "PASS retrieval isolation: A cannot search B material"

ask_response="$(curl -fsS -H "$(auth_header student_a1)" \
  -H 'Content-Type: application/json' \
  --data '{"question":"一次函数基础"}' \
  "$BASE_URL/api/ask")"
python3 -c 'import json,sys; payload=json.load(sys.stdin); assert "[1]" in payload["answer"]; assert payload["citations"]; assert payload["citations"][0]["index"] == 1' <<<"$ask_response"
echo "PASS traceable answer: citation [1] maps to source"

empty_ask="$(curl -fsS -H "$(auth_header student_a1)" \
  -H 'Content-Type: application/json' \
  --data '{"question":"zxqv-no-material-9f2a8c7e"}' \
  "$BASE_URL/api/ask")"
python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload["citations"] == []; assert "未找到" in payload["answer"]' <<<"$empty_ask"
echo "PASS no-evidence answer: empty citations"

title="Compose验收-$(date +%s)"
printf '# Compose verification\nThis material verifies upload and persistence.\n' > "$WORK_DIR/compose-check.md"
upload="$(curl -fsS -H "$(auth_header teacher_a)" \
  -F "title=$title" \
  -F "file=@$WORK_DIR/compose-check.md;type=text/markdown" \
  "$BASE_URL/api/materials/upload")"
material_id="$(printf '%s' "$upload" | python3 -c 'import json,sys; print(json.load(sys.stdin)["material_id"])')"
echo "PASS teacher upload: material_id=$material_id"

student_upload_status="$(curl -sS -o "$WORK_DIR/student-upload.json" -w '%{http_code}' \
  -H "$(auth_header student_a1)" \
  -F "file=@$WORK_DIR/compose-check.md;type=text/markdown" \
  "$BASE_URL/api/materials/upload")"
[[ "$student_upload_status" == "403" ]]
echo "PASS student upload rejected: HTTP 403"

b_material_id="$(printf '%s' "$student_b_materials" | python3 -c 'import json,sys; print(next(item["id"] for item in json.load(sys.stdin)["materials"] if "B班" in item["title"]))')"
cross_status="$(curl -sS -o "$WORK_DIR/cross-class.json" -w '%{http_code}' -H "$(auth_header teacher_a)" "$BASE_URL/api/materials/$b_material_id")"
[[ "$cross_status" == "404" ]]
echo "PASS cross-class access rejected: HTTP 404"

logout_status="$(curl -sS -o "$WORK_DIR/logout.json" -w '%{http_code}' -X POST -H "$(auth_header teacher_a)" "$BASE_URL/logout")"
[[ "$logout_status" == "200" ]]
old_token_status="$(curl -sS -o "$WORK_DIR/revoked.json" -w '%{http_code}' -H "$(auth_header teacher_a)" "$BASE_URL/api/me")"
[[ "$old_token_status" == "401" ]]
echo "PASS logout: old teacher token is rejected"

legacy_cookie_status="$(curl -sS -o "$WORK_DIR/legacy-cookie.json" -w '%{http_code}' -H 'Cookie: session=legacy-signed-cookie' "$BASE_URL/api/me")"
[[ "$legacy_cookie_status" == "401" ]]
echo "PASS legacy cookie: HTTP 401"

shell="$(curl -fsS "$BASE_URL/materials")"
student_token="$(cat "$(token_file student_a1)")"
if [[ "$shell" == *"$student_token"* ]]; then
  echo "FAIL page shell contains a Bearer token" >&2
  exit 1
fi
echo "PASS page shell: no Token in HTML"

qdrant_compose_ports="$(docker compose config --format json | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["services"]["qdrant"].get("ports", [])))')"
if [[ "$qdrant_compose_ports" != "[]" ]]; then
  echo "FAIL Qdrant Compose config publishes host ports: $qdrant_compose_ports" >&2
  exit 1
fi
qdrant_container_id="$(docker compose ps -q qdrant)"
if [[ -z "$qdrant_container_id" ]]; then
  echo "FAIL Qdrant container is not running" >&2
  exit 1
fi
qdrant_host_bindings="$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$qdrant_container_id" | python3 -c 'import json,sys; bindings=json.load(sys.stdin) or {}; print(json.dumps([{"port":port,"bindings":items} for port,items in bindings.items() if items]))')"
if [[ "$qdrant_host_bindings" != "[]" ]]; then
  echo "FAIL Qdrant container has host port bindings: $qdrant_host_bindings" >&2
  exit 1
fi
echo "PASS Qdrant: no host port exposed"

echo "INFO restarting Compose without removing volumes"
docker compose down
docker compose up -d
wait_health
student_after_restart="$(curl -fsS -H "$(auth_header student_a1)" "$BASE_URL/api/me")"
python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload["username"] == "student_a1"; assert payload["class_id"] == 1' <<<"$student_after_restart"
echo "PASS persistence: pre-restart student token remains valid"
login_and_check teacher_a teacher_a_pass
after_restart="$(curl -fsS -H "$(auth_header teacher_a)" "$BASE_URL/api/materials")"
python3 -c 'import json,sys; assert any(sys.argv[1] == x["title"] for x in json.load(sys.stdin)["materials"])' "$title" <<<"$after_restart"
echo "PASS persistence: uploaded material remains after down/up"
docker compose exec -T app python -c 'import sqlite3; c=sqlite3.connect("/app/data/app.db"); assert c.execute("select 1 from sqlite_master where type=\"table\" and name=\"auth_tokens\"").fetchone(); assert c.execute("select count(*) from auth_tokens").fetchone()[0] >= 1'
echo "PASS persistence: auth_tokens table and rows remain after down/up"
assert_search teacher_a "Compose verification" keyword "Compose验收"
assert_search teacher_a "Compose verification" hybrid "Compose验收"

echo "Compose verification completed successfully."
