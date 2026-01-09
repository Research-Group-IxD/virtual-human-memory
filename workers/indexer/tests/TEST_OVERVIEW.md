# Indexer Tests Overview

Quick reference guide to all indexer tests - what they test and why.

## Test Files Structure

```
workers/indexer/tests/
├── test_indexer_units.py      (18 tests) - Unit tests for individual functions
├── test_indexer_integration.py (4 tests) - Integration tests for full flows
├── test_indexer_retry.py      (6 tests) - Retry logic and backoff tests
└── test_indexer_shutdown.py   (5 tests) - Graceful shutdown tests
```

**Total: 29 tests** (all passing)

## Visual Test Overview

```
                    Indexer Tests (29 total)
                           │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   Unit Tests          Integration         Specialized
   (18 tests)          Tests (4)          Tests (11)
        │                   │                   │
        │                   │                   │
   ┌────┴────┐         ┌────┴────┐      ┌───────┴───────┐
   │         │         │         │      │               │
   ▼         ▼         ▼         ▼      ▼               ▼
Core    Retry      Full    Kafka   Retry      Shutdown
Ops     Logic      Flow    Retry   Backoff    Tests
(8)     (5)        (2)     (2)     (6)        (5)
```

## Test Breakdown by Category

### 📦 Core Operations (8 tests)
```
✅ process_anchor_success
✅ process_anchor_immutability_violation
✅ anchor_exists_true/false/empty_id
✅ ensure_collection_creates/recreates/no_change
✅ anchor_exists_qdrant_error
```

### 🔄 Retry Logic (11 tests)
```
Unit Tests (5):
✅ anchor_exists_with_retry_success
✅ anchor_exists_with_retry_exhausted
✅ process_anchor_qdrant_retry_success
✅ process_anchor_qdrant_retry_failure
✅ process_anchor_embedding_failure

Integration (2):
✅ kafka_producer_retry_success
✅ kafka_producer_retry_failure

Backoff & Config (6):
✅ qdrant_retry_with_backoff
✅ kafka_retry_with_backoff
✅ retry_configurable_attempts_qdrant/kafka
✅ retry_zero_retries_qdrant
✅ retry_zero_backoff
```

### 🛑 Graceful Shutdown (5 tests)
```
✅ signal_handler_sets_shutdown_flag
✅ signal_handler_logs_shutdown
✅ signal_handler_handles_both_signals
✅ graceful_shutdown_commits_current_message
✅ graceful_shutdown_flushes_producer
```

### 🔗 Integration Flow (2 tests)
```
✅ indexer_full_flow_success
✅ indexer_immutability_enforcement_flow
```

## Test Categories

### 1. Unit Tests (`test_indexer_units.py`)

#### Core Functionality
- `test_process_anchor_success` - Basic anchor processing works
- `test_process_anchor_immutability_violation` - Prevents overwriting existing anchors
- `test_anchor_exists_true` - Finds existing anchors
- `test_anchor_exists_false` - Correctly identifies missing anchors
- `test_anchor_exists_empty_id` - Handles empty IDs gracefully

#### Collection Management
- `test_ensure_collection_creates_new` - Creates collection when missing
- `test_ensure_collection_recreates_on_dimension_mismatch` - Recreates on wrong dimensions
- `test_ensure_collection_no_change_when_correct` - No action when dimensions match

#### Error Handling
- `test_anchor_exists_qdrant_error` - Handles Qdrant errors gracefully

#### Retry Logic (NEW)
- `test_anchor_exists_with_retry_success` - Retries and succeeds on second attempt
- `test_anchor_exists_with_retry_exhausted` - Returns False after all retries fail
- `test_process_anchor_qdrant_retry_success` - Retries Qdrant upsert on failure
- `test_process_anchor_qdrant_retry_failure` - Returns error after retries exhausted
- `test_process_anchor_embedding_failure` - Handles embedding generation failures

### 2. Integration Tests (`test_indexer_integration.py`)

#### Full Flow Tests
- `test_indexer_full_flow_success` - Complete successful flow (Kafka → Process → Qdrant)
- `test_indexer_immutability_enforcement_flow` - Full flow with immutability check

#### Kafka Retry (NEW)
- `test_kafka_producer_retry_success` - Kafka publish retries and succeeds
- `test_kafka_producer_retry_failure` - Message not committed if Kafka publish fails

### 3. Retry Logic Tests (`test_indexer_retry.py`) - NEW FILE

#### Backoff Timing
- `test_qdrant_retry_with_backoff` - Verifies exponential backoff (0.25s, 0.5s, 0.75s...)
- `test_kafka_retry_with_backoff` - Verifies Kafka backoff timing (0.5s, 1.0s...)

#### Configuration
- `test_retry_configurable_attempts_qdrant` - Retry attempts are configurable for Qdrant
- `test_retry_configurable_attempts_kafka` - Retry attempts are configurable for Kafka

#### Edge Cases
- `test_retry_zero_retries_qdrant` - Behavior when retries=0 (uses default)
- `test_retry_zero_backoff` - Behavior when backoff=0.0 (uses default)

### 4. Shutdown Tests (`test_indexer_shutdown.py`) - NEW FILE

#### Signal Handling
- `test_signal_handler_sets_shutdown_flag` - SIGTERM/SIGINT sets shutdown flag
- `test_signal_handler_logs_shutdown` - Shutdown is logged
- `test_signal_handler_handles_both_signals` - Both SIGTERM and SIGINT work

#### Graceful Shutdown
- `test_graceful_shutdown_commits_current_message` - Current message is committed
- `test_graceful_shutdown_flushes_producer` - Producer is flushed on shutdown

## Test Coverage Summary

### What's Tested

✅ **Core Operations**
- Anchor processing
- Immutability enforcement
- Collection management
- Error handling

✅ **Retry Logic** (NEW)
- Qdrant operations (retrieve, upsert)
- Kafka producer operations
- Exponential backoff
- Configuration options

✅ **Graceful Shutdown** (NEW)
- Signal handling (SIGTERM, SIGINT)
- Message acknowledgment
- Producer flushing
- Clean shutdown

### Test Patterns Used

- **Mocking**: All external dependencies (Qdrant, Kafka, time.sleep)
- **Side Effects**: Simulate failures and successes
- **Assertions**: Verify call counts, return values, error handling
- **Fixtures**: Reusable test data (sample_anchor, mock_qdrant_client)

## Quick Test Reference

| Test Name | What It Tests | Key Assertion |
|-----------|---------------|---------------|
| `test_process_anchor_success` | Basic processing | `result["ok"] == True` |
| `test_anchor_exists_with_retry_success` | Retry works | `call_count == 2` (retried once) |
| `test_kafka_producer_retry_failure` | No commit on failure | `success == False` |
| `test_qdrant_retry_with_backoff` | Backoff timing | `sleep(0.25)`, `sleep(0.5)` |
| `test_signal_handler_sets_shutdown_flag` | Shutdown flag | `shutdown_requested == True` |

## Running Tests

```bash
# Run all indexer tests
pytest workers/indexer/tests/ -v

# Run specific test file
pytest workers/indexer/tests/test_indexer_retry.py -v

# Run specific test
pytest workers/indexer/tests/test_indexer_units.py::test_anchor_exists_with_retry_success -v

# Run with coverage
pytest workers/indexer/tests/ --cov=workers.vhm_indexer
```
