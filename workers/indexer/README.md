# vhm-worker-indexer

VHM Worker: Ingests and indexes new memories.

## Overview

The Indexer worker consumes memory messages from Kafka, generates vector embeddings, and stores them in Qdrant for semantic search. It enforces immutability (never overwrites existing memories) and includes production-ready features like retry logic and graceful shutdown.

## Key Features

- **Memory Ingestion**: Consumes from `anchors-write` topic, publishes to `anchors-indexed`
- **Immutability**: Prevents overwriting existing memories with the same `anchor_id`
- **Embedding Generation**: Converts text to high-dimensional vectors using configurable models
- **Collection Management**: Automatically handles embedding model dimension changes
- **Production Ready**: Retry logic, graceful shutdown, manual Kafka commits

## Documentation

- **Detailed Overview**: See [`onboarding/03_Service_Deep_Dive.md`](../../onboarding/03_Service_Deep_Dive.md#31-indexer)
- **Conceptual Explanation**: See [`docs/concepts/workers-overview.md`](../../docs/concepts/workers-overview.md#-worker-1-indexer)
- **Retry Logic**: See [`docs/concepts/retry-logic-explanation.md`](../../docs/concepts/retry-logic-explanation.md)
- **Tests**: See [`workers/indexer/tests/TEST_OVERVIEW.md`](tests/TEST_OVERVIEW.md)
