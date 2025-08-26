# verify_token.sh
#!/usr/bin/env bash
set -euo pipefail

API_ROOT="https://api.line.me"
TOKEN="${LINE_CHANNEL_ACCESS_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  echo "❌ LINE_CHANNEL_ACCESS_TOKEN ไม่ถูกตั้งค่าใน environment"
  echo "   วิธีตั้งชั่วคราว (bash/zsh): export LINE_CHANNEL_ACCESS_TOKEN='YOUR_TOKEN'"
  exit 1
fi

echo "🔎 Verifying access token with /v2/oauth/verify ..."
# ต้อง POST และมี body (แม้จะว่าง)
VERIFY_RESP=$(curl -sS -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "$API_ROOT/v2/oauth/verify") || { echo "❌ curl ล้มเหลว"; exit 1; }

# แยก body กับ http code
HTTP_BODY="$(echo "$VERIFY_RESP" | sed '$d')"
HTTP_CODE="$(echo "$VERIFY_RESP" | tail -n1)"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "❌ Verify ไม่ผ่าน (HTTP $HTTP_CODE)"
  echo "$HTTP_BODY"
  exit 2
fi

# พยายามสรุปผลลัพธ์แบบอ่านง่าย (ถ้ามี jq)
if command -v jq >/dev/null 2>&1; then
  CLIENT_ID=$(echo "$HTTP_BODY" | jq -r '.client_id // empty')
  EXPIRES_IN=$(echo "$HTTP_BODY" | jq -r '.expires_in // empty')
  SCOPE=$(echo "$HTTP_BODY" | jq -r '.scope // empty')

  echo "✅ Token ใช้ได้"
  [[ -n "$CLIENT_ID" ]] && echo "   client_id: $CLIENT_ID"
  [[ -n "$EXPIRES_IN" ]] && echo "   expires_in (secs): $EXPIRES_IN"
  [[ -n "$SCOPE" ]] && echo "   scope: $SCOPE"
else
  echo "✅ Token ใช้ได้ (ติดตั้ง jq เพื่อแสดงผลสวยขึ้น)"
  echo "$HTTP_BODY"
fi

# ออปชัน: ดึงข้อมูลบอท เพื่อยืนยันสิทธิ์ Messaging API
echo
echo "🔎 Checking /v2/bot/info ..."
INFO_RESP=$(curl -sS -w "\n%{http_code}" -X GET \
  -H "Authorization: Bearer $TOKEN" \
  "$API_ROOT/v2/bot/info") || { echo "❌ curl ล้มเหลว"; exit 1; }

INFO_BODY="$(echo "$INFO_RESP" | sed '$d')"
INFO_CODE="$(echo "$INFO_RESP" | tail -n1)"

if [[ "$INFO_CODE" == "200" ]]; then
  echo "✅ /v2/bot/info OK"
  if command -v jq >/dev/null 2>&1; then
    echo "$INFO_BODY" | jq .
  else
    echo "$INFO_BODY"
  fi
else
  echo "⚠️  /v2/bot/info ไม่ผ่าน (HTTP $INFO_CODE)"
  echo "    หมายเหตุ: ถ้าได้ 401 invalid_token ให้เช็คว่า token ถูก/เป็น long-lived"
  echo "$INFO_BODY"
fi
