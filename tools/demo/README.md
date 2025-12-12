# Indexer Service Demo

## Overview

This Streamlit app provides a visual interface to test and demonstrate the Indexer service. It shows the complete flow of how memory anchors are processed:

1. **Create Anchor** → Send a memory anchor to Kafka
2. **Kafka Processing** → Indexer consumes from `anchors-write` topic
3. **Embedding Generation** → Text is converted to a vector embedding
4. **Qdrant Storage** → Anchor is stored in the vector database
5. **Confirmation** → Result published to `anchors-indexed` topic

## Features

- 📝 **Create Anchors**: Send new memory anchors with custom text, salience, and metadata
- 📊 **Processing Flow**: Visualize each step of the indexing process in real-time
- 🗄️ **Qdrant Inspection**: Browse and inspect stored anchors in the vector database
- 🔬 **Detailed Inspection**: View embeddings, metadata, and statistics for specific anchors
- ⏰ **Time Simulation**: Simulate time passing and test how memories are recalled with temporal decay

## Running the Demo

### Prerequisites

1. Make sure you have the required services running:
   - Kafka (default: `localhost:9092`)
   - Qdrant (default: `http://localhost:6333`)
   - Indexer worker (consuming from `anchors-write` topic)
   - Resonance worker (optional, for recall testing)

2. Set environment variables (if needed):
```bash
export KAFKA_BOOTSTRAP=localhost:9092
export QDRANT_URL=http://localhost:6333
export QDRANT_COLLECTION=anchors
export EMBEDDING_MODEL=deterministic  # or ollama:bge-m3, etc.
```

### Running Locally

1. Install dependencies (if not already done):
```bash
uv sync
```

2. Run the Streamlit app:
```bash
uv run streamlit run tools/demo/indexer_demo.py
```

3. Open your browser to: http://localhost:8501

## Usage Guide

### Tab 1: Create Anchor

- Enter the text of your memory anchor
- Adjust the salience (importance) slider (0.3 - 2.5)
- Optionally add tags (comma-separated)
- Click "Send Anchor to Indexer" to publish it to Kafka

### Tab 2: Processing Flow

- Click "Check for New Indexed Anchors" to monitor Kafka for processing results
- View the status of each step:
  - ✅ Created
  - ✅ Kafka (anchors-write)
  - ✅/⏳ Indexer Processing
  - ✅/⏳ Qdrant Storage

### Tab 3: Qdrant Storage

- Browse all anchors stored in Qdrant
- Adjust the limit slider to see more/fewer anchors
- Click "Refresh from Qdrant" to update the list
- View full payload including text, timestamps, salience, and metadata

### Tab 4: Inspection

- Enter a specific anchor ID to inspect
- View detailed information including:
  - Full metadata
  - Embedding vector (preview and statistics)
  - Vector dimensions and model information

### Tab 5: Time & Recall

- Simulate time passing (advance by days, months, or years)
- Test recall queries to see how memories are retrieved
- Visualize decay over time using the Ebbinghaus forgetting curve
- See how activation scores change based on simulated time

## Configuration

The demo respects the following environment variables:

- `KAFKA_BOOTSTRAP`: Kafka broker address (default: `kafka:9092` for Kubernetes, `localhost:9092` for local)
- `QDRANT_URL`: Qdrant server URL (default: `http://qdrant:6333` for Kubernetes, `http://localhost:6333` for local)
- `QDRANT_COLLECTION`: Collection name (default: `anchors`)
- `EMBEDDING_MODEL`: Embedding model to use (default: `deterministic`)
  - Options: `deterministic`, `ollama:bge-m3`, `ollama:nomic-embed-text`, `portkey:cohere-embed-v3`, etc.

## Troubleshooting

### Indexer not processing anchors

- Check that the indexer service is running
- Check indexer logs
- Verify Kafka topics exist: `kafka-topics --list --bootstrap-server localhost:9092`

### Qdrant connection issues

- Verify Qdrant is running
- Check Qdrant logs
- Try refreshing the connection in the sidebar

### Embeddings not working

- For `ollama:*` models, ensure Ollama is running and the model is pulled
- For `deterministic`, no external dependencies needed
- Check the embedding model setting in the sidebar

## Presentation Tips

This demo is designed to be presentation-friendly:

1. **Start with Tab 1**: Create a memorable anchor (e.g., "We demoed our Virtual Human to colleagues")
2. **Move to Tab 2**: Show the processing flow in real-time
3. **Switch to Tab 3**: Show how the anchor is stored in Qdrant
4. **Use Tab 4**: Inspect the embedding to show the technical details
5. **Explore Tab 5**: Demonstrate time simulation and recall with decay

The visual flow makes it easy to explain:
- How Kafka decouples services
- How embeddings convert text to vectors
- How Qdrant stores and retrieves memories
- The complete end-to-end pipeline
- How temporal decay affects memory recall

