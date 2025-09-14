# Local Worker for Endurance Tool Exploration

A Python worker that runs locally to compute features and generate AI-powered stress propensity inferences from calendar and physiological data.

## Setup

### 1. Environment Configuration

Copy the environment template and fill in your credentials:

```bash
cp env.template .env
```

Edit `.env` with your actual values:
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key for database access
- `COHERE_API_KEY`: Your Cohere API key for AI inference

### 2. Dependencies

Dependencies are already installed in the project's `.venv`. To activate:

```bash
cd /Users/danielching/DevProjects/endurance-tool-exploration
source .venv/bin/activate
```

## Usage

### Multiday Inference

Run multiday stress propensity analysis (analyzes 3 days back, forecasts 4 days ahead):

```bash
cd local-worker
python run.py multiday
```

### Dry Run Mode

Test the system without writing to the database:

```bash
python run.py multiday --dry-run
```

This will:
1. Query historical and forecast events from Supabase
2. Compute features (event density, scheduling patterns, trends)
3. Generate AI inference using Cohere
4. Print results without saving to database

## Architecture

### Directory Structure

```
local-worker/
├── lib/
│   ├── supa.py          # Supabase client with retry logic
│   ├── logging.py       # Structured logging and metrics
│   ├── windows.py       # Time window calculations
│   ├── features.py      # Feature engineering (Layer 1)
│   ├── cohere_client.py # AI inference client (Layer 2)
│   └── prompts.py       # Versioned system prompts
├── run.py               # Main entrypoint
├── env.template         # Environment variable template
└── logs/                # Generated log files
```

### Data Flow

1. **Read (Layer 0)**: Query events and source health from Supabase
2. **Compute (Layer 1)**: Generate features from raw data
3. **Infer (Layer 2)**: Call Cohere for AI-powered analysis
4. **Write**: Store features and inferences back to Supabase

### Features Computed

**Historical Analysis (3 days back):**
- Average daily event count and scheduled minutes
- Back-to-back event frequency
- Late evening/early morning scheduling patterns
- Event type distribution and trends

**Forecast Analysis (4 days ahead):**
- Upcoming event density and peak days
- Total scheduled hours
- Potential stress risk windows

**Quality Metrics:**
- Data freshness and completeness
- Source health indicators
- Confidence scoring

### AI Inference

The system uses Cohere's Command model to analyze computed features and generate:

- **Daily stress propensity scores** (0-100 scale)
- **Risk windows** with specific time ranges and descriptions
- **Actionable recommendations** for schedule optimization
- **Confidence scores** based on data quality

## Monitoring

### Logs

All activity is logged to `logs/local-worker.log` with rotation. Key events include:
- Job start/completion with duration
- Data quality assessments
- Feature computation stats
- AI inference performance
- Error details and stack traces

### Metrics

Performance metrics are tracked in `logs/metrics.jsonl`:
- Source lag times and data freshness
- Feature computation statistics
- AI model latency and token usage
- Job success/failure rates

## Scheduling

For production use, schedule the worker with cron:

```bash
# Run multiday inference every 4 hours
0 */4 * * * cd /path/to/local-worker && python run.py multiday >> logs/cron.log 2>&1
```

## Error Handling

The system includes robust error handling:
- **Retry logic** for network calls with exponential backoff
- **Graceful degradation** when data is stale or incomplete
- **Idempotent operations** - safe to re-run jobs
- **Structured error logging** for debugging

## Configuration

Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_SOURCE_LAG_SECONDS` | 300 | Max acceptable data staleness |
| `MULTIDAY_LOOKBACK_DAYS` | 3 | Historical analysis window |
| `MULTIDAY_LOOKAHEAD_DAYS` | 4 | Forecast window |
| `FEATURE_SPEC_VERSION` | v1 | Feature schema version |
| `LOG_LEVEL` | INFO | Logging verbosity |

## Troubleshooting

### Common Issues

1. **Missing environment variables**: Check `.env` file exists and has all required values
2. **Database connection errors**: Verify Supabase URL and service role key
3. **Cohere API errors**: Check API key and usage limits
4. **No data returned**: Verify events exist in the configured time windows

### Debug Mode

Set `LOG_LEVEL=DEBUG` in `.env` for verbose logging:

```bash
LOG_LEVEL=DEBUG python run.py multiday --dry-run
```

### Data Quality

Monitor source freshness in logs. The system will warn when:
- Calendar/email data is more than 5 minutes stale
- Event confidence scores are low
- Insufficient data points for reliable inference

## Future Enhancements

- **Instant inference**: Real-time stress analysis with physiological data
- **Personalization**: User-specific baselines and thresholds  
- **Enhanced features**: Sleep data, location context, meeting types
- **Dashboard integration**: Real-time UI updates via Supabase Realtime
