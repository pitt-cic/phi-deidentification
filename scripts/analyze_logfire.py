#!/usr/bin/env python3
"""Analyze Logfire spans for PII detection test runs.

Usage:
    python scripts/analyze_logfire.py <start_timestamp> <end_timestamp>

Example:
    python scripts/analyze_logfire.py 2026-03-02T17:09:32Z 2026-03-02T17:14:34Z

Requires LOGFIRE_READ_TOKEN environment variable.
Get your token from: Logfire Dashboard → Settings → Read Tokens
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

import requests

LOGFIRE_API_URL = "https://logfire-us.pydantic.dev/v1/query"

# Claude Sonnet 4.5 pricing (as of March 2026)
INPUT_PRICE_PER_1M = 3.00
OUTPUT_PRICE_PER_1M = 15.00
CACHE_READ_PRICE_PER_1M = 0.30  # 90% discount on cached input tokens
CACHE_WRITE_PRICE_PER_1M = 3.75  # 25% premium for writing to cache


def get_token() -> str:
    """Get Logfire read token from environment."""
    token = os.environ.get("LOGFIRE_READ_TOKEN")
    if not token:
        print("Error: LOGFIRE_READ_TOKEN environment variable not set.")
        print("Get your token from: Logfire Dashboard → Settings → Read Tokens")
        sys.exit(1)
    return token


def query_logfire(sql: str, token: str, max_retries: int = 3) -> dict:
    """Execute a SQL query against Logfire API with retry for rate limits."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = {
        "sql": sql,
        "row_oriented": "true",
    }

    for attempt in range(max_retries + 1):
        response = requests.get(LOGFIRE_API_URL, headers=headers, params=params)

        if response.status_code == 429:
            if attempt < max_retries:
                wait_time = 2 ** (attempt + 1)  # 2, 4, 8 seconds
                print(f"  (Rate limited, waiting {wait_time}s...)", file=sys.stderr)
                time.sleep(wait_time)
                continue

        response.raise_for_status()
        return response.json()

    # Should not reach here, but just in case
    response.raise_for_status()
    return response.json()


def extract_column_value(data: dict, column_name: str, default=None):
    """Extract a single value from Logfire column-oriented response."""
    for col in data.get("columns", []):
        if col.get("name") == column_name:
            values = col.get("values", [])
            return values[0] if values else default
    return default


def extract_rows(data: dict) -> list[dict]:
    """Convert Logfire column-oriented response to row-oriented."""
    columns = data.get("columns", [])
    if not columns:
        return []

    num_rows = len(columns[0].get("values", []))
    rows = []

    for i in range(num_rows):
        row = {}
        for col in columns:
            row[col["name"]] = col["values"][i] if i < len(col["values"]) else None
        rows.append(row)

    return rows


def get_summary(start: str, end: str, token: str) -> dict:
    """Get token summary for the time range."""
    sql = f"""
    SELECT
        SUM(CAST(attributes->>'input_tokens' AS INTEGER)) AS total_input,
        SUM(CAST(attributes->>'output_tokens' AS INTEGER)) AS total_output,
        SUM(CAST(attributes->>'total_tokens' AS INTEGER)) AS total_tokens,
        COUNT(*) AS total_spans,
        SUM(CASE WHEN is_exception THEN 1 ELSE 0 END) AS failed_spans,
        SUM(CASE WHEN NOT is_exception THEN 1 ELSE 0 END) AS successful_spans,
        AVG(CAST(attributes->>'input_tokens' AS DOUBLE)) AS avg_input,
        AVG(CAST(attributes->>'output_tokens' AS DOUBLE)) AS avg_output,
        SUM(COALESCE(CAST(attributes->>'cache_read_tokens' AS INTEGER), 0)) AS total_cache_read,
        SUM(COALESCE(CAST(attributes->>'cache_write_tokens' AS INTEGER), 0)) AS total_cache_write,
        AVG(COALESCE(CAST(attributes->>'cache_read_tokens' AS DOUBLE), 0)) AS avg_cache_read,
        AVG(COALESCE(CAST(attributes->>'cache_write_tokens' AS DOUBLE), 0)) AS avg_cache_write
    FROM records
    WHERE span_name = 'pii_detection'
        AND start_timestamp >= '{start}'
        AND start_timestamp <= '{end}'
    """
    return query_logfire(sql, token)


def get_per_minute_breakdown(start: str, end: str, token: str) -> dict:
    """Get per-minute breakdown of requests and tokens."""
    sql = f"""
    SELECT
        DATE_TRUNC('minute', start_timestamp) AS minute,
        COUNT(*) AS total_requests,
        SUM(CASE WHEN is_exception THEN 1 ELSE 0 END) AS failures,
        SUM(CASE WHEN NOT is_exception THEN 1 ELSE 0 END) AS successes,
        SUM(CAST(attributes->>'total_tokens' AS INTEGER)) AS tokens_used
    FROM records
    WHERE span_name = 'pii_detection'
        AND start_timestamp >= '{start}'
        AND start_timestamp <= '{end}'
    GROUP BY DATE_TRUNC('minute', start_timestamp)
    ORDER BY minute
    """
    return query_logfire(sql, token)


def get_error_breakdown(start: str, end: str, token: str) -> dict:
    """Get breakdown of errors by type and message."""
    sql = f"""
    SELECT
        exception_type,
        otel_status_message,
        COUNT(*) AS count
    FROM records
    WHERE span_name = 'pii_detection'
        AND start_timestamp >= '{start}'
        AND start_timestamp <= '{end}'
        AND is_exception = true
    GROUP BY exception_type, otel_status_message
    ORDER BY count DESC
    """
    return query_logfire(sql, token)


def categorize_error(message: str | None) -> str:
    """Categorize error message into TPM, RPM, or Other."""
    if not message:
        return "Other"
    message_lower = message.lower()
    if "too many tokens" in message_lower:
        return "Too many tokens (TPM)"
    if "too many requests" in message_lower:
        return "Too many requests (RPM)"
    return "Other"


def calculate_cost(input_tokens: int, output_tokens: int) -> tuple[float, float, float]:
    """Calculate cost based on token counts."""
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
    total_cost = input_cost + output_cost
    return input_cost, output_cost, total_cost


def format_number(n: int | float | None) -> str:
    """Format number with commas."""
    if n is None:
        return "N/A"
    if isinstance(n, float):
        return f"{n:,.2f}"
    return f"{n:,}"


def print_summary(data: dict) -> tuple[int, int, int, int, int]:
    """Print summary and return token counts and doc count for cost calculation."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_input = extract_column_value(data, "total_input", 0) or 0
    total_output = extract_column_value(data, "total_output", 0) or 0
    total_tokens = extract_column_value(data, "total_tokens", 0) or 0
    total_spans = extract_column_value(data, "total_spans", 0) or 0
    failed_spans = extract_column_value(data, "failed_spans", 0) or 0
    successful_spans = extract_column_value(data, "successful_spans", 0) or 0
    avg_input = extract_column_value(data, "avg_input", 0) or 0
    avg_output = extract_column_value(data, "avg_output", 0) or 0
    total_cache_read = extract_column_value(data, "total_cache_read", 0) or 0
    total_cache_write = extract_column_value(data, "total_cache_write", 0) or 0
    avg_cache_read = extract_column_value(data, "avg_cache_read", 0) or 0
    avg_cache_write = extract_column_value(data, "avg_cache_write", 0) or 0

    print("\nSpans:")
    print(f"  Total:      {format_number(total_spans)}")
    print(f"  Successful: {format_number(successful_spans)}")
    print(f"  Failed:     {format_number(failed_spans)}")

    if total_spans > 0:
        success_rate = (successful_spans / total_spans) * 100
        print(f"  Success Rate: {success_rate:.1f}%")

    print("\nTokens (successful spans only):")
    print(f"  Input:  {format_number(total_input)}")
    print(f"  Output: {format_number(total_output)}")
    print(f"  Total:  {format_number(total_tokens)}")

    # Cache tokens section (only show if caching was used)
    if total_cache_read > 0 or total_cache_write > 0:
        print("\nCache Tokens:")
        print(f"  Cache Read:  {format_number(total_cache_read)}")
        print(f"  Cache Write: {format_number(total_cache_write)}")
        if total_input > 0:
            cache_hit_rate = (total_cache_read / (total_input + total_cache_read)) * 100
            print(f"  Cache Hit Rate: {cache_hit_rate:.1f}%")

    print("\nAverages per span:")
    print(f"  Input:  {format_number(avg_input)}")
    print(f"  Output: {format_number(avg_output)}")
    if total_cache_read > 0 or total_cache_write > 0:
        print(f"  Cache Read:  {format_number(avg_cache_read)}")
        print(f"  Cache Write: {format_number(avg_cache_write)}")

    return total_input, total_output, successful_spans, total_cache_read, total_cache_write


def calculate_cost_with_cache(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> tuple[float, float, float, float, float, float]:
    """Calculate cost based on token counts including cache tokens.

    Note: cache_read_tokens are a SUBSET of input_tokens (tokens served from cache),
    so we subtract them to avoid double-counting.
    """
    # Non-cached input tokens pay full price
    non_cached_input = max(0, input_tokens - cache_read_tokens)
    non_cached_input_cost = (non_cached_input / 1_000_000) * INPUT_PRICE_PER_1M

    # Cached input tokens pay discounted price
    cache_read_cost = (cache_read_tokens / 1_000_000) * CACHE_READ_PRICE_PER_1M

    # Cache writes pay a premium
    cache_write_cost = (cache_write_tokens / 1_000_000) * CACHE_WRITE_PRICE_PER_1M

    # Output tokens
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M

    total_cost = non_cached_input_cost + cache_read_cost + cache_write_cost + output_cost
    return non_cached_input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost, non_cached_input


def print_cost(
    input_tokens: int,
    output_tokens: int,
    doc_count: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
):
    """Print cost breakdown including per-document cost and cache savings."""
    print("\n" + "=" * 60)
    print("COST ESTIMATE (Claude Sonnet 4.5)")
    print("=" * 60)

    non_cached_input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost, non_cached_input = calculate_cost_with_cache(
        input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
    )

    # Show cache costs if caching was used
    if cache_read_tokens > 0 or cache_write_tokens > 0:
        print(f"\n  Input (non-cached): ${non_cached_input_cost:.4f} ({format_number(non_cached_input)} tokens @ $3.00/1M)")
        print(f"  Input (cached):     ${cache_read_cost:.4f} ({format_number(cache_read_tokens)} tokens @ $0.30/1M)")
        print(f"  Cache Write:        ${cache_write_cost:.4f} ({format_number(cache_write_tokens)} tokens @ $3.75/1M)")
        print(f"  Output:             ${output_cost:.4f} ({format_number(output_tokens)} tokens @ $15.00/1M)")

        # Calculate savings from caching
        cost_without_cache = (cache_read_tokens / 1_000_000) * INPUT_PRICE_PER_1M
        cache_savings = cost_without_cache - cache_read_cost
        if cache_savings > 0:
            print(f"  Cache Savings:      ${cache_savings:.4f} (vs full input price)")
    else:
        print(f"\n  Input:  ${non_cached_input_cost:.4f} ({format_number(input_tokens)} tokens @ $3.00/1M)")
        print(f"  Output: ${output_cost:.4f} ({format_number(output_tokens)} tokens @ $15.00/1M)")

    print(f"  Total:  ${total_cost:.4f}")

    if doc_count > 0:
        per_doc_cost = total_cost / doc_count
        per_doc_output = output_cost / doc_count
        print(f"\nPer Document ({doc_count} docs):")
        if cache_read_tokens > 0 or cache_write_tokens > 0:
            per_doc_non_cached_input = non_cached_input_cost / doc_count
            per_doc_cache_read = cache_read_cost / doc_count
            per_doc_cache_write = cache_write_cost / doc_count
            print(f"  Input (non-cached): ${per_doc_non_cached_input:.6f}")
            print(f"  Input (cached):     ${per_doc_cache_read:.6f}")
            print(f"  Cache Write:        ${per_doc_cache_write:.6f}")
        else:
            per_doc_input = non_cached_input_cost / doc_count
            print(f"  Input:  ${per_doc_input:.6f}")
        print(f"  Output: ${per_doc_output:.6f}")
        print(f"  Total:  ${per_doc_cost:.6f}")


def print_per_minute(data: dict):
    """Print per-minute breakdown."""
    print("\n" + "=" * 60)
    print("PER-MINUTE BREAKDOWN")
    print("=" * 60)

    rows = extract_rows(data)
    if not rows:
        print("\n  No data available")
        return

    print(f"\n  {'Minute':<20} {'Total':>8} {'Success':>8} {'Failed':>8} {'Tokens':>12} {'TPM':>10}")
    print("  " + "-" * 68)

    for row in rows:
        minute = row.get("minute", "")
        if minute:
            # Parse and format the timestamp
            try:
                dt = datetime.fromisoformat(minute.replace("Z", "+00:00"))
                minute_str = dt.strftime("%H:%M:%S")
            except (ValueError, AttributeError):
                minute_str = str(minute)[:19]
        else:
            minute_str = "N/A"

        total = row.get("total_requests", 0) or 0
        successes = row.get("successes", 0) or 0
        failures = row.get("failures", 0) or 0
        tokens = row.get("tokens_used", 0) or 0

        # TPM is the tokens used in that minute (already per-minute since grouped by minute)
        tpm = tokens

        print(f"  {minute_str:<20} {total:>8} {successes:>8} {failures:>8} {tokens:>12,} {tpm:>10,}")

    # Calculate totals
    total_requests = sum(r.get("total_requests", 0) or 0 for r in rows)
    total_successes = sum(r.get("successes", 0) or 0 for r in rows)
    total_failures = sum(r.get("failures", 0) or 0 for r in rows)
    total_tokens = sum(r.get("tokens_used", 0) or 0 for r in rows)

    print("  " + "-" * 68)
    print(f"  {'TOTAL':<20} {total_requests:>8} {total_successes:>8} {total_failures:>8} {total_tokens:>12,}")

    # Calculate average TPM
    if rows:
        avg_tpm = total_tokens / len(rows)
        print(f"\n  Average TPM: {avg_tpm:,.0f}")


def print_errors(data: dict):
    """Print error breakdown."""
    print("\n" + "=" * 60)
    print("ERROR BREAKDOWN")
    print("=" * 60)

    rows = extract_rows(data)
    if not rows:
        print("\n  No errors! 🎉")
        return

    # Categorize errors
    categories: dict[str, int] = {
        "Too many tokens (TPM)": 0,
        "Too many requests (RPM)": 0,
        "Other": 0,
    }
    categorized_rows: dict[str, list[dict]] = {
        "Too many tokens (TPM)": [],
        "Too many requests (RPM)": [],
        "Other": [],
    }

    for row in rows:
        message = row.get("otel_status_message", "") or ""
        count = row.get("count", 0) or 0
        category = categorize_error(message)
        categories[category] += count
        categorized_rows[category].append(row)

    # Print summary by category
    total_errors = sum(categories.values())
    print(f"\n  {'Category':<35} {'Count':>8} {'%':>8}")
    print("  " + "-" * 53)

    for category, count in categories.items():
        if count > 0:
            pct = (count / total_errors) * 100 if total_errors > 0 else 0
            print(f"  {category:<35} {count:>8} {pct:>7.1f}%")

    print("  " + "-" * 53)
    print(f"  {'TOTAL':<35} {total_errors:>8}")

    # Print sample error for each category
    for category in ["Too many tokens (TPM)", "Too many requests (RPM)", "Other"]:
        if categories[category] > 0 and categorized_rows[category]:
            # Show first error as sample
            sample = categorized_rows[category][0]
            error_type = sample.get("exception_type", "Unknown") or "Unknown"
            message = sample.get("otel_status_message", "") or ""

            # Truncate message for display
            if len(message) > 70:
                message = message[:67] + "..."

            print(f"\n  {category} (sample):")
            print(f"    Type: {error_type}")
            if message:
                print(f"    Message: {message}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Logfire spans for PII detection test runs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/analyze_logfire.py 2026-03-02T17:09:32Z 2026-03-02T17:14:34Z
    python scripts/analyze_logfire.py 2026-03-02T17:09:32.648775Z 2026-03-02T17:14:34.713253Z

Environment:
    LOGFIRE_READ_TOKEN - Your Logfire read token (required)
        """,
    )
    parser.add_argument(
        "start",
        help="Start timestamp (ISO 8601 format, e.g., 2026-03-02T17:09:32Z)",
    )
    parser.add_argument(
        "end",
        help="End timestamp (ISO 8601 format, e.g., 2026-03-02T17:14:34Z)",
    )
    parser.add_argument(
        "--no-cost",
        action="store_true",
        help="Skip cost calculation",
    )
    parser.add_argument(
        "--no-per-minute",
        action="store_true",
        help="Skip per-minute breakdown",
    )
    parser.add_argument(
        "--no-errors",
        action="store_true",
        help="Skip error breakdown",
    )

    args = parser.parse_args()

    token = get_token()

    print(f"\nAnalyzing Logfire spans from {args.start} to {args.end}")

    # Get summary
    try:
        summary_data = get_summary(args.start, args.end, token)
        input_tokens, output_tokens, doc_count, cache_read, cache_write = print_summary(summary_data)
    except requests.exceptions.HTTPError as e:
        print(f"\nError querying Logfire: {e}")
        sys.exit(1)

    # Cost calculation
    if not args.no_cost:
        print_cost(input_tokens, output_tokens, doc_count, cache_read, cache_write)

    # Per-minute breakdown
    if not args.no_per_minute:
        try:
            per_minute_data = get_per_minute_breakdown(args.start, args.end, token)
            print_per_minute(per_minute_data)
        except requests.exceptions.HTTPError as e:
            print(f"\nError getting per-minute breakdown: {e}")

    # Error breakdown
    if not args.no_errors:
        try:
            error_data = get_error_breakdown(args.start, args.end, token)
            print_errors(error_data)
        except requests.exceptions.HTTPError as e:
            print(f"\nError getting error breakdown: {e}")

    print("\n")


if __name__ == "__main__":
    main()
