# Logfire Token & Cost Analysis

## Prerequisites

1. Export your Logfire read token:
   ```bash
   export LOGFIRE_READ_TOKEN="your_read_token_here"
   ```

2. Get the read token from: Logfire Dashboard → Settings → Read Tokens

## Token Summary Query

Replace the timestamps with your test run window:

```bash
curl -s -G 'https://logfire-us.pydantic.dev/v1/query' \
  -H "Authorization: Bearer $LOGFIRE_READ_TOKEN" \
  -H 'Accept: application/json' \
  --data-urlencode "sql=SELECT
    SUM(CAST(attributes->>'input_tokens' AS INTEGER)) AS total_input,
    SUM(CAST(attributes->>'output_tokens' AS INTEGER)) AS total_output,
    SUM(CAST(attributes->>'total_tokens' AS INTEGER)) AS total_tokens,
    COUNT(*) AS total_spans,
    SUM(CASE WHEN is_exception THEN 1 ELSE 0 END) AS failed_spans,
    SUM(CASE WHEN NOT is_exception THEN 1 ELSE 0 END) AS successful_spans,
    AVG(CAST(attributes->>'input_tokens' AS DOUBLE)) AS avg_input,
    AVG(CAST(attributes->>'output_tokens' AS DOUBLE)) AS avg_output
  FROM records
  WHERE span_name = 'pii_detection'
    AND start_timestamp >= '2026-03-02T06:57:58Z'
    AND start_timestamp <= '2026-03-02T07:05:10Z'" \
  --data-urlencode "row_oriented=true" | jq '.columns |
    {
      total_input: .[] | select(.name == "total_input") | .values[0],
      total_output: .[] | select(.name == "total_output") | .values[0],
      total_tokens: .[] | select(.name == "total_tokens") | .values[0],
      successful_docs: .[] | select(.name == "successful_spans") | .values[0],
      failed_spans: .[] | select(.name == "failed_spans") | .values[0],
      avg_input: .[] | select(.name == "avg_input") | .values[0],
      avg_output: .[] | select(.name == "avg_output") | .values[0]
    }'
```

## Per-Minute Breakdown Query

Useful for debugging throttling issues:

```bash
curl -s -G 'https://logfire-us.pydantic.dev/v1/query' \
  -H "Authorization: Bearer $LOGFIRE_READ_TOKEN" \
  -H 'Accept: application/json' \
  --data-urlencode "sql=SELECT
    DATE_TRUNC('minute', start_timestamp) AS minute,
    COUNT(*) AS total_requests,
    SUM(CASE WHEN is_exception THEN 1 ELSE 0 END) AS failures,
    SUM(CASE WHEN NOT is_exception THEN 1 ELSE 0 END) AS successes,
    SUM(CAST(attributes->>'total_tokens' AS INTEGER)) AS tokens_billed
  FROM records
  WHERE span_name = 'pii_detection'
    AND start_timestamp >= '2026-03-02T06:57:58Z'
    AND start_timestamp <= '2026-03-02T07:05:10Z'
  GROUP BY DATE_TRUNC('minute', start_timestamp)
  ORDER BY minute" \
  --data-urlencode "row_oriented=true" | jq .
```

## Cost Calculation

Claude Sonnet 4.5 pricing (as of March 2026):
- Input: $3.00 per 1M tokens
- Output: $15.00 per 1M tokens

```bash
# After running the summary query, calculate:
INPUT_TOKENS=320404
OUTPUT_TOKENS=73624

INPUT_COST=$(echo "scale=2; $INPUT_TOKENS / 1000000 * 3.00" | bc)
OUTPUT_COST=$(echo "scale=2; $OUTPUT_TOKENS / 1000000 * 15.00" | bc)
TOTAL_COST=$(echo "scale=2; $INPUT_COST + $OUTPUT_COST" | bc)

echo "Input cost:  \$$INPUT_COST"
echo "Output cost: \$$OUTPUT_COST"
echo "Total cost:  \$$TOTAL_COST"
```

## Error Analysis Query

Check what errors occurred:

```bash
curl -s -G 'https://logfire-us.pydantic.dev/v1/query' \
  -H "Authorization: Bearer $LOGFIRE_READ_TOKEN" \
  -H 'Accept: application/json' \
  --data-urlencode "sql=SELECT
    exception_type,
    COUNT(*) AS count
  FROM records
  WHERE span_name = 'pii_detection'
    AND start_timestamp >= '2026-03-02T06:57:58Z'
    AND start_timestamp <= '2026-03-02T07:05:10Z'
    AND is_exception = true
  GROUP BY exception_type
  ORDER BY count DESC" \
  --data-urlencode "row_oriented=true" | jq .
```

## Quick One-Liner Summary

```bash
# Replace START and END with your timestamps
START="2026-03-02T06:57:58Z"
END="2026-03-02T07:05:10Z"

curl -s -G 'https://logfire-us.pydantic.dev/v1/query' \
  -H "Authorization: Bearer $LOGFIRE_READ_TOKEN" \
  --data-urlencode "sql=SELECT SUM(CAST(attributes->>'input_tokens' AS INTEGER)) as input, SUM(CAST(attributes->>'output_tokens' AS INTEGER)) as output, COUNT(*) as docs FROM records WHERE span_name='pii_detection' AND NOT is_exception AND start_timestamp >= '$START' AND start_timestamp <= '$END'" | \
  jq -r '.columns | "Docs: \(.[2].values[0]) | Input: \(.[0].values[0]) | Output: \(.[1].values[0]) | Cost: $\((.[0].values[0]/1000000*3 + .[1].values[0]/1000000*15) | . * 100 | floor / 100)"'
```
