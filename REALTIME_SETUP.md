# Real-time Calendar Webhook Setup Guide

You've successfully implemented real-time Google Calendar webhook ingestion! This guide will help you deploy and test the complete real-time stress analysis pipeline.

## 🚀 What You've Built

1. **Real-time Calendar Webhook** (`ingest-gcal/index.ts`) - Processes Google Calendar changes instantly
2. **Feature Computation Trigger** (`trigger-realtime-features/index.ts`) - Computes features when calendar changes
3. **Real-time Inference Engine** (`local-worker/realtime_inference.py`) - Generates immediate stress insights
4. **Notification System** - Alerts for high-stress calendar patterns
5. **Testing Infrastructure** (`test_webhook_flow.py`) - Comprehensive testing suite

## 📋 Next Steps

### 1. Deploy Supabase Functions

```bash
# Deploy the new functions
cd supabase/functions

# Deploy the real-time trigger
supabase functions deploy trigger-realtime-features

# Re-deploy the updated calendar ingestion function
supabase functions deploy ingest-gcal

# Check deployment status
supabase functions list
```

### 2. Set Up Database Schema

```bash
# Run the migration to create notifications table
supabase db push

# Or manually run the SQL migration
psql -h your-supabase-host -U postgres -d postgres -f supabase/migrations/create_notifications_table.sql
```

### 3. Configure Google Calendar Webhook Subscription

You need to set up a Google Calendar webhook subscription to receive real-time notifications:

```bash
# Use Google Calendar API to create a watch request
curl -X POST \
  'https://www.googleapis.com/calendar/v3/calendars/primary/events/watch' \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "unique-channel-id",
    "type": "web_hook",
    "address": "https://your-supabase-project.supabase.co/functions/v1/ingest-gcal",
    "token": "your-gcal-channel-token"
  }'
```

### 4. Test the Complete Flow

```bash
# Run the comprehensive test suite
cd /Users/danielching/DevProjects/endurance-tool-exploration
python test_webhook_flow.py

# Test real-time inference directly
cd local-worker
python realtime_inference.py
```

### 5. Monitor and Validate

```bash
# Check Supabase logs for webhook processing
supabase functions logs ingest-gcal

# Check feature computation
supabase functions logs trigger-realtime-features

# Monitor notifications table
echo "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10;" | supabase db sql
```

## 🔧 Configuration

### Environment Variables

Make sure these are set in your Supabase project:

```env
# Google OAuth (already configured)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token

# New webhook-specific variables
GCAL_CHANNEL_TOKEN=your_unique_channel_token
REALTIME_STRESS_THRESHOLD=0.7
MIN_EVENTS_FOR_INFERENCE=3
```

### Local Worker Configuration

Update your local `.env` file:

```env
# Add these new settings
REALTIME_STRESS_THRESHOLD=0.7
MIN_EVENTS_FOR_INFERENCE=3
MULTIDAY_LOOKBACK_DAYS=3
```

## 📊 How It Works

1. **Calendar Change** → Google sends webhook to `ingest-gcal`
2. **Event Processing** → Calendar events are upserted to events table
3. **Feature Trigger** → `trigger-realtime-features` is called automatically
4. **Stress Analysis** → Features are computed and stress indicators calculated
5. **Notification** → If high stress detected, notification is created
6. **Real-time Inference** → Local worker can generate detailed analysis

## 🚨 Stress Detection Logic

The system automatically detects high-stress patterns:

- **Calendar Density**: >6 events in 24 hours
- **Back-to-back Meetings**: <30 minutes between events
- **Stress Keywords**: "deadline", "urgent", "crisis", "interview", "review"
- **Off-hours Events**: Before 7:30 AM or after 8:30 PM
- **Long Events**: >2 hours without breaks

## 📱 Integration Options

### Real-time Notifications
- **Database**: Check `notifications` table
- **Webhooks**: Add webhook endpoints to the notification system
- **Push Notifications**: Integrate with mobile push services
- **Email/SMS**: Add notification channels

### Dashboard Integration
```javascript
// Example: Real-time dashboard updates
const { data: notifications } = await supabase
  .from('notifications')
  .select('*')
  .eq('read_at', null)
  .order('created_at', { ascending: false });
```

### API Endpoints
```bash
# Get recent stress analysis
GET /rest/v1/features?spec_version=like.*realtime*&order=created_at.desc

# Get notifications
GET /rest/v1/notifications?read_at=is.null&order=created_at.desc

# Mark notification as read
PATCH /rest/v1/notifications?id=eq.notification_id
Content-Type: application/json
{"read_at": "2024-01-01T12:00:00Z"}
```

## 🐛 Troubleshooting

### Common Issues

1. **Webhook not receiving events**
   - Check Google Calendar webhook subscription is active
   - Verify `GCAL_CHANNEL_TOKEN` matches in environment and subscription
   - Check Supabase function logs

2. **Features not computing**
   - Verify events are being inserted into events table
   - Check `trigger-realtime-features` function logs
   - Ensure `compute-features-snapshot` function is working

3. **No notifications created**
   - Check stress threshold settings
   - Verify notification table exists
   - Test with high-stress calendar patterns

### Debugging Commands

```bash
# Check recent events
echo "SELECT COUNT(*), kind FROM events WHERE ingested_at > NOW() - INTERVAL '1 hour' GROUP BY kind;" | supabase db sql

# Check recent features
echo "SELECT * FROM features WHERE spec_version LIKE '%realtime%' ORDER BY created_at DESC LIMIT 5;" | supabase db sql

# Check notifications
echo "SELECT type, severity, message, created_at FROM notifications ORDER BY created_at DESC LIMIT 10;" | supabase db sql
```

## 📈 Next Enhancement Ideas

1. **Machine Learning**: Train models on your stress patterns
2. **Predictive Alerts**: Warn about stress patterns before they happen
3. **Integration**: Connect with health apps, Slack, Microsoft Teams
4. **Advanced Analytics**: Weekly/monthly stress trend analysis
5. **Personalization**: Learn individual stress thresholds and patterns

## 🎯 Success Metrics

Your real-time system is working when:
- ✅ Calendar changes trigger webhooks within seconds
- ✅ High-stress patterns generate notifications
- ✅ Features are computed with <2 second latency
- ✅ Test suite passes all scenarios
- ✅ Notifications provide actionable recommendations

Great work building this real-time stress analysis system! 🎉
