#!/bin/bash

echo "🚀 Running orchestrated stress analysis pipeline..."
echo "=================================================="

# Single call that does everything: ingest emails → ingest calendar → analyze → notify
RESULT=$(curl -s -X POST \
  "https://idtxsrrhbjmdsbagzgqy.supabase.co/functions/v1/trigger-realtime-features" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkdHhzcnJoYmptZHNiYWd6Z3F5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Nzc3NzIyOSwiZXhwIjoyMDczMzUzMjI5fQ.M-VpYMV_CX49lgGHpwWoJ4blwCUbJ7RvvsJMgGo1NNk" \
  -H "Content-Type: application/json" \
  -d '{"event_kind": "calendar", "source_id": "manual-check", "change_type": "stress_check"}')

echo "📊 Pipeline Results:"
echo "$RESULT" | jq '{
  processing_time: .processing_time_ms,
  data_ingested: .data_ingested,
  new_emails: .gmail_result.debug.inserted,
  calendar_updated: .gcal_result,
  features_computed: .features_computed,
  stress_alert: .inference_triggered,
  features: .features
}'

if echo "$RESULT" | jq -r '.inference_triggered' | grep -q "true"; then
  echo ""
  echo "🚨 STRESS ALERT TRIGGERED!"
  echo "📱 Latest notification:"
  curl -s -X GET \
    "https://idtxsrrhbjmdsbagzgqy.supabase.co/rest/v1/notifications?order=created_at.desc&limit=1&select=message,severity,created_at" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkdHhzcnJoYmptZHNiYWd6Z3F5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Nzc3NzIyOSwiZXhwIjoyMDczMzUzMjI5fQ.M-VpYMV_CX49lgGHpwWoJ4blwCUbJ7RvvsJMgGo1NNk" \
    -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkdHhzcnJoYmptZHNiYWd6Z3F5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Nzc3NzIyOSwiZXhwIjoyMDczMzUzMjI5fQ.M-VpYMV_CX49lgGHpwWoJ4blwCUbJ7RvvsJMgGo1NNk" | jq '.[0]'
else
  echo ""
  echo "�� No stress detected - you're all good!"
fi

echo ""
echo "✅ Stress check complete!"
