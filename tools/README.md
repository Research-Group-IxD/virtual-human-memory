# Tools

This directory contains utility scripts and demo applications for the Virtual Human Memory system.

## Available Tools

### `demo_three_retells.py`

A demonstration script that tests the complete end-to-end flow of the memory system:

1. **Seeds three memory anchors** with different timestamps (12 hours ago, 2 weeks ago, 7 months ago)
2. **Sends a recall request** to query for relevant memories
3. **Waits for resonance beats** (recall-response) from the Resonance worker
4. **Waits for retelling** (retell-response) from the Reteller worker
5. **Logs the complete flow** to a JSON file in `./results/`

#### Usage

```bash
# Make sure all workers are running (indexer, resonance, reteller)
# Then run the demo:
uv run python tools/demo_three_retells.py
```

#### Configuration

- `KAFKA_BOOTSTRAP`: Kafka broker address (default: from `vhm_common_utils.config`)
- `QDRANT_URL`: Qdrant server URL (default: from `vhm_common_utils.config`)
- `QDRANT_COLLECTION`: Collection name (default: from `vhm_common_utils.config`)
- `DEMO_RESET_COLLECTION`: Reset Qdrant collection before running (default: `true`)
- `DEMO_LOG_DIR`: Directory to save log files (default: `./results`)

#### Example Output

```
[demo] Seeding three anchors...
<anchor-id> • stored 12 hours ago • salience 1.0
    While calibrating the narrative memory today, we watched BB-8 mimic the reteller's cadence.
...

[demo] Recall request id: <request-id>

[demo] Waiting for resonance beats...
  Beat 1: anchor <id> • perceived 12 hours ago • activation 0.923
    While calibrating the narrative memory today...

[demo] Waiting for retelling...
[demo] Reteller response:
While calibrating the narrative memory today, we watched BB-8 mimic the reteller's cadence, which echoed our prototype demo at Fontys where questions spiraled about forgetting curves. Looking back, the Reflective City pilot in Rotterdam sparked debates over long-term narrative drift, shaping a thread around narrative memory, forgetting curves, and experimental prototypes.

[demo] Saved transcript to ./results/demo-three-retells-20250121T120000Z.json
```

### `demo/indexer_demo.py`

A Streamlit-based interactive demo for testing and visualizing the Indexer service. See [demo/README.md](./demo/README.md) for details.

## Prerequisites

All tools require:
- Kafka running and accessible
- Qdrant running and accessible
- Relevant workers running (depends on the tool)

See the main [README.md](../README.md) for instructions on starting services.

