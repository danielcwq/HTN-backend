// Option 1: VERY LIMITED (recommended for testing)
base.searchParams.set("maxResults","50");  // Only 50 events max
const timeMin = new Date(Date.now() - 3*86400_000).toISOString();  // 3 days back  
const timeMax = new Date(Date.now() + 14*86400_000).toISOString(); // 14 days forward

// Option 2: MINIMAL (for performance)
base.searchParams.set("maxResults","25");   // Only 25 events max
const timeMin = new Date(Date.now() - 1*86400_000).toISOString();  // 1 day back
const timeMax = new Date(Date.now() + 7*86400_000).toISOString();  // 7 days forward

// Option 3: CURRENT WEEK ONLY
base.searchParams.set("maxResults","100");  // 100 events max
const timeMin = new Date(Date.now() - 0*86400_000).toISOString();  // Today only
const timeMax = new Date(Date.now() + 7*86400_000).toISOString();  // Next 7 days
