// supabase/functions/trigger-realtime-features/index.ts
import { serve } from "https://deno.land/std/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const sb = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SERVICE_ROLE_KEY")!
);

serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const startTime = Date.now();
  
  try {
    const { event_kind, source_id, change_type } = await req.json();
    
    console.log(`🚀 Starting real-time pipeline: ${change_type} on ${source_id}`);

    // ---- STEP 1: Ingest fresh data from both sources ----
    console.log("📧 Step 1: Ingesting Gmail data...");
    const gmailResponse = await fetch(`${Deno.env.get("SUPABASE_URL")}/functions/v1/ingest-gmail`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${Deno.env.get("SERVICE_ROLE_KEY")}`,
        "Content-Type": "application/json"
      }
    });

    let gmailResult = null;
    if (gmailResponse.ok) {
      gmailResult = await gmailResponse.json();
      console.log(`✅ Gmail ingestion: ${gmailResult.debug?.inserted || 0} new emails`);
    } else {
      console.warn(`⚠️ Gmail ingestion failed: ${gmailResponse.status}`);
    }

    console.log("📅 Step 2: Ingesting Google Calendar data...");
    const gcalResponse = await fetch(`${Deno.env.get("SUPABASE_URL")}/functions/v1/ingest-gcal`, {
      method: "POST", 
      headers: {
        "Authorization": `Bearer ${Deno.env.get("SERVICE_ROLE_KEY")}`,
        "Content-Type": "application/json"
      }
    });

    let gcalResult = null;
    if (gcalResponse.ok) {
      const gcalText = await gcalResponse.text();
      gcalResult = gcalText;
      console.log(`✅ Calendar ingestion: ${gcalText}`);
    } else {
      console.warn(`⚠️ Calendar ingestion failed: ${gcalResponse.status}`);
    }

    // ---- STEP 2: Get data counts before and after to detect changes ----
    const { data: emailCount } = await sb
      .from("events")
      .select("*", { count: "exact", head: true })
      .eq("kind", "email")
      .gte("ingested_at", new Date(Date.now() - 60 * 60 * 1000).toISOString()); // Last hour

    const { data: calendarCount } = await sb
      .from("events") 
      .select("*", { count: "exact", head: true })
      .eq("kind", "calendar")
      .gte("ingested_at", new Date(Date.now() - 60 * 60 * 1000).toISOString()); // Last hour

    const newEmailsCount = emailCount || 0;
    const newCalendarCount = calendarCount || 0;

    console.log(`📊 Data summary: ${newEmailsCount} recent emails, ${newCalendarCount} recent calendar events`);

    // ---- STEP 3: Only proceed with analysis if we have fresh data ----
    const hasNewData = (gmailResult && gmailResult.debug?.inserted > 0) || gcalResult === "ok";
    
    if (!hasNewData && newEmailsCount === 0 && newCalendarCount === 0) {
      console.log("⏸️ No new data detected, skipping analysis");
      return new Response(JSON.stringify({
        ok: true,
        message: "No new data to analyze",
        data_ingested: false,
        features_computed: false,
        inference_triggered: false
      }), {
        headers: { "content-type": "application/json" }
      });
    }

    // ---- STEP 4: Trigger feature computation with fresh data ----
    console.log("🧠 Step 3: Computing features with fresh data...");
    const featureResponse = await fetch(`${Deno.env.get("SUPABASE_URL")}/functions/v1/compute-features-snapshot`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${Deno.env.get("SERVICE_ROLE_KEY")}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        sleep_minutes: 480, // Default values - these would come from your actual sleep data
        sleep_score: 75,
        spec_version: "v1-realtime-orchestrated"
      })
    });

    if (!featureResponse.ok) {
      throw new Error(`Feature computation failed: ${featureResponse.status}`);
    }

    const featureResult = await featureResponse.json();
    console.log("✅ Features computed:", featureResult.features_written?.features);

    // ---- STEP 5: Check if we should trigger real-time inference ----
    const shouldTriggerInference = await checkStressIndicators();
    
    if (shouldTriggerInference) {
      console.log("🚨 High stress indicators detected, triggering notification");
      await notifyHighStressSchedule(featureResult);
    } else {
      console.log("😌 Stress levels normal, no alerts needed");
    }

    const processingTime = Date.now() - startTime;
    console.log(`⚡ Pipeline completed in ${processingTime}ms`);

    return new Response(JSON.stringify({ 
      ok: true,
      processing_time_ms: processingTime,
      data_ingested: true,
      gmail_result: gmailResult,
      gcal_result: gcalResult === "ok",
      features_computed: true,
      inference_triggered: shouldTriggerInference,
      features: featureResult.features_written?.features
    }), {
      headers: { "content-type": "application/json" }
    });

  } catch (error) {
    console.error("❌ Pipeline error:", error);
    return new Response(JSON.stringify({ 
      ok: false, 
      error: error.message,
      processing_time_ms: Date.now() - startTime
    }), {
      status: 500,
      headers: { "content-type": "application/json" }
    });
  }
});

async function checkStressIndicators(): Promise<boolean> {
  try {
    // Query recent calendar events to check for stress patterns
    const { data: recentEvents } = await sb
      .from("events")
      .select("*")
      .eq("kind", "calendar")
      .gte("ts_range", `[${new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()},)`)
      .order("ts_range");

    if (!recentEvents || recentEvents.length === 0) return false;

    // Look at upcoming events for stress analysis (not past events)
    const now = new Date();
    const next24Hours = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    
    const upcomingEvents = recentEvents.filter(event => {
      const eventStart = new Date(event.ts_range.split(',')[0].substring(1));
      return eventStart >= now && eventStart <= next24Hours;
    });

    console.log(`📅 Found ${upcomingEvents.length} upcoming events in next 24h`);

    // Trigger if:
    // 1. More than 5 events in next 24 hours  
    // 2. Events with less than 30 min gaps
    // 3. Events with stress-related keywords
    const highDensity = upcomingEvents.length > 5;
    
    const hasBackToBackMeetings = upcomingEvents.some((event, i) => {
      if (i === upcomingEvents.length - 1) return false;
      const currentEnd = new Date(event.ts_range.split(',')[1].substring(0, event.ts_range.split(',')[1].length - 1));
      const nextStart = new Date(upcomingEvents[i + 1].ts_range.split(',')[0].substring(1));
      return (nextStart.getTime() - currentEnd.getTime()) < 30 * 60 * 1000; // 30 minutes
    });

    const hasStressKeywords = upcomingEvents.some(event => {
      const summary = event.details?.summary?.toLowerCase() || "";
      return summary.includes("deadline") || 
             summary.includes("urgent") || 
             summary.includes("crisis") ||
             summary.includes("interview") ||
             summary.includes("presentation") ||
             summary.includes("review") ||
             summary.includes("exam") ||
             summary.includes("test");
    });

    const stressDetected = highDensity || hasBackToBackMeetings || hasStressKeywords;
    
    if (stressDetected) {
      console.log(`🚨 Stress factors: density=${highDensity}, back-to-back=${hasBackToBackMeetings}, keywords=${hasStressKeywords}`);
    }

    return stressDetected;

  } catch (error) {
    console.error("Error checking stress indicators:", error);
    return false;
  }
}

async function notifyHighStressSchedule(featureResult: any): Promise<void> {
  try {
    console.log("🔔 Creating stress notification");
    
    // Store notification in database
    await sb.from("notifications").insert({
      type: "high_stress_schedule",
      severity: "warning", 
      message: "High stress calendar pattern detected in upcoming 24 hours",
      data: {
        ...featureResult,
        detected_at: new Date().toISOString(),
        trigger: "real-time-orchestrated"
      },
      created_at: new Date().toISOString()
    });

    console.log("✅ Notification created successfully");

  } catch (error) {
    console.error("Error sending notification:", error);
  }
}
