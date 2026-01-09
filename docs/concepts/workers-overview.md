# Virtual Human Memory: Workers Overview

A presentation-friendly explanation of how the three workers collaborate to create a psychologically plausible memory system.

## 🎯 The Big Picture

The Virtual Human Memory system simulates how humans form, recall, and retell memories. It uses three specialized workers that work together:

```
┌─────────────┐
│   Client    │  "What did I do last week?"
│ Application │
└──────┬──────┘
       │
       │ 1. Store Memory
       ▼
┌─────────────────────────────────────────────────────┐
│              KAFKA (Message Broker)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │anchors-write │  │recall-request│  │recall-   │ │
│  │              │  │              │  │response  │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────┘
       │                    │                    │
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────┐         ┌──────────┐         ┌──────────┐
│ INDEXER  │         │RESONANCE │         │ RETELLER │
│          │         │          │         │          │
│ Store    │         │ Recall   │         │ Narrate  │
│ Memories │         │ Memories │         │ Stories  │
└────┬─────┘         └────┬─────┘         └────┬─────┘
     │                    │                    │
     │                    │                    │
     └────────────────────┴────────────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │   QDRANT    │
                  │ Vector DB   │
                  └─────────────┘
```

---

## 📦 Worker 1: Indexer

**Purpose**: Store new memories and make them searchable

### What It Does

The Indexer is the **memory ingestion service**. It takes new memories and converts them into a searchable format.

```
┌─────────────┐
│   Chatbot   │  "I had a great meeting today!"
└──────┬──────┘
       │
       │ Publishes to Kafka
       ▼
┌─────────────┐
│   Kafka     │  Topic: anchors-write
│  (Message)  │  {
│             │    "anchor_id": "uuid-123",
│             │    "text": "Great meeting today!",
│             │    "stored_at": "2025-01-15T10:00:00Z",
│             │    "salience": 1.5
│             │  }
└──────┬──────┘
       │
       │ Indexer consumes
       ▼
┌─────────────────────────────────┐
│         INDEXER                 │
│  ┌───────────────────────────┐  │
│  │ 1. Validate message       │  │
│  │ 2. Check if exists        │  │  ← Immutability check
│  │ 3. Generate embedding     │  │  ← Text → Vector
│  │ 4. Store in Qdrant        │  │  ← Vector + metadata
│  │ 5. Publish confirmation   │  │  ← Success message
│  └───────────────────────────┘  │
└──────────────┬──────────────────┘
       │
       │ Stores vector + metadata
       ▼
┌─────────────┐
│   Qdrant    │  Vector: [0.12, -0.45, 0.89, ...]
│  (Storage)  │  Metadata: {text, stored_at, salience}
└─────────────┘
       │
       │ Confirmation
       ▼
┌─────────────┐
│   Kafka     │  Topic: anchors-indexed
│ (Confirmation)│  {"ok": true, "anchor_id": "uuid-123"}
└─────────────┘
```

### Key Features

1. **Immutability**: Never overwrites existing memories (same `anchor_id`)
2. **Embedding Generation**: Converts text to high-dimensional vectors
3. **Model Flexibility**: Automatically handles embedding model changes
4. **Reliability**: Retry logic ensures memories aren't lost on temporary failures

### Why It Matters

Without the Indexer, memories would never be stored. It's the foundation of the entire system.

---

## 🔍 Worker 2: Resonance

**Purpose**: Simulate human recall - find and rank relevant memories

### What It Does

Resonance is the **memory search engine**. It finds relevant memories and applies psychological models to determine which ones are most "active" or top-of-mind.

```
┌─────────────┐
│   Client    │  "What did I do last week?"
└──────┬──────┘
       │
       │ Publishes recall request
       ▼
┌─────────────┐
│   Kafka     │  Topic: recall-request
│  (Request)  │  {
│             │    "query": "What did I do last week?",
│             │    "now": "2025-01-15T10:00:00Z",
│             │    "top_k": 10
│             │  }
└──────┬──────┘
       │
       │ Resonance consumes
       ▼
┌─────────────────────────────────┐
│        RESONANCE                │
│  ┌───────────────────────────┐  │
│  │ 1. Embed query            │  │  ← Query → Vector
│  │ 2. Semantic search        │  │  ← Find similar memories
│  │ 3. Calculate activation   │  │  ← Apply psychology
│  │ 4. Select diverse results │  │  ← Avoid repetition
│  │ 5. Format as "beats"      │  │  ← Prepare for retelling
│  └───────────────────────────┘  │
└──────────────┬──────────────────┘
       │
       │ Searches Qdrant
       ▼
┌─────────────┐
│   Qdrant    │  Returns: Similar memories
│  (Search)   │  with similarity scores
└──────┬──────┘
       │
       │ Resonance applies:
       │ activation = similarity × decay × salience
       ▼
┌─────────────────────────────────┐
│  Multi-Factor Activation        │
│  ┌───────────────────────────┐  │
│  │ similarity: 0.85          │  │  ← How similar to query?
│  │ × decay: 0.60            │  │  ← How old? (forgetting curve)
│  │ × salience: 1.5          │  │  ← How important?
│  │ = activation: 0.77       │  │  ← Final score
│  └───────────────────────────┘  │
└──────────────┬──────────────────┘
       │
       │ Publishes beats
       ▼
┌─────────────┐
│   Kafka     │  Topic: recall-response
│  (Beats)    │  {
│             │    "beats": [
│             │      {
│             │        "text": "Great meeting today!",
│             │        "activation": 0.77,
│             │        "perceived_age": "yesterday"
│             │      },
│             │      ...
│             │    ]
│             │  }
└─────────────┘
```

### The Activation Formula

Resonance uses a **psychologically-inspired formula**:

```
activation = similarity × decay × salience
```

- **Similarity**: How semantically similar is the memory to the query? (0.0 - 1.0)
- **Decay**: How old is the memory? Older = lower score (Ebbinghaus forgetting curve)
- **Salience**: How important was the memory when stored? (user-defined)

### Key Features

1. **Semantic Search**: Finds memories by meaning, not just keywords
2. **Temporal Decay**: Older memories fade naturally (like human memory)
3. **Diversity Selection**: Avoids repetitive results
4. **Human-Readable Ages**: "yesterday", "about 3 months ago"

### Why It Matters

Resonance makes the system psychologically plausible. It doesn't just retrieve memories - it simulates how humans actually remember things.

---

## 📖 Worker 3: Reteller

**Purpose**: Transform raw memory fragments into coherent, human-like stories

### What It Does

The Reteller is the **narrative generation layer**. It takes disconnected memory "beats" and weaves them into a single, coherent story.

```
┌─────────────┐
│   Kafka     │  Topic: recall-response
│  (Beats)    │  {
│             │    "beats": [
│             │      {"text": "Meeting at Fontys", "activation": 0.85, "age": "yesterday"},
│             │      {"text": "Demo presentation", "activation": 0.72, "age": "2 days ago"},
│             │      {"text": "Q&A about ethics", "activation": 0.65, "age": "3 days ago"}
│             │    ]
│             │  }
└──────┬──────┘
       │
       │ Reteller consumes
       ▼
┌─────────────────────────────────┐
│         RETELLER                │
│  ┌───────────────────────────┐  │
│  │ 1. Order beats            │  │  ← Chronological
│  │ 2. Extract motifs         │  │  ← Find themes
│  │ 3. Apply forgetting       │  │  ← Fade old details
│  │ 4. Build prompt           │  │  ← Guide LLM
│  │ 5. Generate narrative     │  │  ← Create story
│  └───────────────────────────┘  │
└──────────────┬──────────────────┘
       │
       │ Tries LLMs in order:
       │ 1. OpenAI
       │ 2. Portkey
       │ 3. Ollama (local)
       │ 4. Stub (fallback)
       ▼
┌─────────────────────────────────┐
│  Generated Narrative            │
│  ┌───────────────────────────┐  │
│  │ "I demoed our Virtual     │  │
│  │  Human at Fontys          │  │
│  │  yesterday, which echoed  │  │
│  │  the presentation from a   │  │
│  │  couple days ago. Looking │  │
│  │  back, there was a Q&A    │  │
│  │  about ethics, shaping a   │  │
│  │  thread around research   │  │
│  │  and responsibility."     │  │
│  └───────────────────────────┘  │
└──────────────┬──────────────────┘
       │
       │ Publishes narrative
       ▼
┌─────────────┐
│   Kafka     │  Topic: retell-response
│ (Narrative) │  {
│             │    "retelling": "I demoed our..."
│             │  }
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Client    │  Receives natural story
│ Application │
└─────────────┘
```

### Key Features

1. **Smart Prompting**: Doesn't just dump text - extracts themes, motifs, and temporal structure
2. **Forgetting Simulation**: Older memories lose specific details (e.g., "at 14:30 in room R10" → "sometime in a room")
3. **LLM Fallback Chain**: Tries multiple LLM providers, falls back to deterministic stub
4. **First-Person Narrative**: Writes as if the Virtual Human is remembering

### Why It Matters

The Reteller transforms raw data into something humans can understand. It's the difference between a database query and a story.

---

## 🔄 The Complete Flow

Here's how all three workers collaborate:

```
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY FORMATION                         │
└─────────────────────────────────────────────────────────────┘

Client → Kafka (anchors-write) → INDEXER → Qdrant
                                    ↓
                              Kafka (anchors-indexed)


┌─────────────────────────────────────────────────────────────┐
│                    MEMORY RECALL                            │
└─────────────────────────────────────────────────────────────┘

Client → Kafka (recall-request) → RESONANCE → Qdrant
                                      ↓
                              Kafka (recall-response)
                                      ↓
                                  RETELLER
                                      ↓
                              Kafka (retell-response)
                                      ↓
                                    Client
```

### Example: Complete Journey

1. **Monday**: Chatbot says "I had a great meeting!"
   - → Indexer stores it in Qdrant

2. **Friday**: User asks "What did I do this week?"
   - → Resonance searches Qdrant, finds the meeting
   - → Resonance calculates: high similarity, recent (low decay), high salience
   - → Resonance returns beat: "Great meeting!" (activation: 0.85)

3. **Reteller receives beat**:
   - → Orders chronologically
   - → Extracts theme: "work meetings"
   - → Generates: "I had a great meeting earlier this week that stood out."

4. **User receives**: Natural, human-like story

---

## 🎯 Key Takeaways for Presentations

### 1. **Separation of Concerns**
Each worker has one job:
- **Indexer**: Store
- **Resonance**: Find
- **Reteller**: Narrate

### 2. **Psychological Plausibility**
The system doesn't just store and retrieve - it simulates:
- **Forgetting** (temporal decay)
- **Importance** (salience)
- **Context** (semantic similarity)
- **Narrative** (storytelling)

### 3. **Scalability**
All workers are:
- **Stateless**: No internal state
- **Horizontally scalable**: Run multiple instances
- **Event-driven**: Communicate via Kafka

### 4. **Reliability**
- **Retry logic**: Handles temporary failures
- **Graceful shutdown**: No data loss
- **Fallback chains**: Multiple LLM options

### 5. **The Magic Formula**
```
activation = similarity × decay × salience
```
This simple formula creates psychologically plausible memory recall.

---

## 📊 Visual Summary

```
┌─────────────────────────────────────────────────────────┐
│                    THE THREE WORKERS                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  INDEXER          RESONANCE          RETELLER           │
│  ┌──────┐         ┌──────┐         ┌──────┐           │
│  │ Store│         │ Find │         │ Tell │           │
│  │      │         │      │         │      │           │
│  │ Text │         │ Query│         │ Beats│           │
│  │  ↓   │         │  ↓   │         │  ↓   │           │
│  │Vector│         │Beats │         │Story │           │
│  └──────┘         └──────┘         └──────┘           │
│     │                │                │                │
│     └────────────────┴────────────────┘                │
│                    │                                    │
│                    ▼                                    │
│              ┌──────────┐                              │
│              │  QDRANT  │                              │
│              │ Vector DB│                              │
│              └──────────┘                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 💡 Analogies

- **Indexer** = Librarian: Takes new books (memories), catalogs them, puts them on shelves (Qdrant)
- **Resonance** = Memory researcher: Searches the library, finds relevant books, ranks them by relevance
- **Reteller** = Storyteller: Takes the found books, weaves them into a coherent narrative

---

## 🚀 Production Features

All workers include:
- ✅ **Retry logic** (handles network issues)
- ✅ **Graceful shutdown** (no data loss)
- ✅ **Health checks** (Kubernetes ready)
- ✅ **Comprehensive tests** (29+ tests for Indexer)
- ✅ **Structured logging** (easy debugging)

---

This system creates a **psychologically plausible, scalable, and reliable** memory system for virtual humans.
