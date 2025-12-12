"""Streamlit demo app for testing and visualizing the Indexer service.

This app demonstrates the complete flow:
1. Create an anchor (memory)
2. Send it to Kafka topic 'anchors-write'
3. Monitor the indexer processing it
4. View the result in Qdrant
5. Visualize the embedding and metadata
"""

from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from typing import List, Optional

import pandas as pd
import streamlit as st
from confluent_kafka import Consumer, Producer, KafkaError
from qdrant_client import QdrantClient
from qdrant_client.http import models

from vhm_common_utils.config import (
    KAFKA_BOOTSTRAP,
    QDRANT_URL,
    QDRANT_COLLECTION,
    EMBEDDING_MODEL,
)
from vhm_common_utils.embedding import (
    get_embedding,
    get_embedding_dim,
    human_age,
)


def _check_kafka_connection() -> tuple[bool, str]:
    """Check if Kafka is accessible."""
    try:
        producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "socket.timeout.ms": 2000,  # 2 second timeout
        })
        # Try to get metadata (this will fail if Kafka is not reachable)
        producer.list_topics(timeout=2)
        producer.close()
        return True, "Connected"
    except Exception as e:
        return False, str(e)


def _check_qdrant_connection() -> tuple[bool, str]:
    """Check if Qdrant is accessible."""
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=2)
        # Try to get collections (this will fail if Qdrant is not reachable)
        client.get_collections()
        return True, "Connected"
    except Exception as e:
        return False, str(e)


def _init_state():
    """Initialize session state variables."""
    if "anchors_sent" not in st.session_state:
        st.session_state.anchors_sent = []
    if "anchors_indexed" not in st.session_state:
        st.session_state.anchors_indexed = []
    if "qdrant_client" not in st.session_state:
        try:
            st.session_state.qdrant_client = QdrantClient(url=QDRANT_URL)
        except Exception as e:
            st.session_state.qdrant_client = None
            st.session_state.qdrant_error = str(e)
    if "time_offset" not in st.session_state:
        st.session_state.time_offset = dt.timedelta(0)
    if "recall_results" not in st.session_state:
        st.session_state.recall_results = []
    # Check service connections
    if "service_checks" not in st.session_state:
        st.session_state.service_checks = {
            "kafka": _check_kafka_connection(),
            "qdrant": _check_qdrant_connection(),
        }


def _format_timestamp(ts: dt.datetime | str) -> str:
    """Format timestamp for display."""
    if isinstance(ts, str):
        try:
            ts = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except:
            return ts
    return ts.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _send_anchor_to_kafka(text: str, salience: float, meta: dict) -> dict:
    """Send an anchor to Kafka topic 'anchors-write'."""
    anchor = {
        "anchor_id": str(uuid.uuid4()),
        "text": text,
        "stored_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "salience": salience,
        "meta": meta,
    }
    
    try:
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        producer.produce("anchors-write", json.dumps(anchor).encode("utf-8"))
        producer.flush()
        return anchor
    except Exception as e:
        st.error(f"Failed to send anchor to Kafka: {e}")
        return None


def _consume_indexed_anchors(timeout: float = 2.0) -> List[dict]:
    """Consume messages from 'anchors-indexed' topic."""
    messages = []
    try:
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"indexer-demo-{uuid.uuid4()}",
            "auto.offset.reset": "latest",
        })
        consumer.subscribe(["anchors-indexed"])
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            msg = consumer.poll(0.5)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    st.warning(f"Kafka error: {msg.error()}")
                continue
            
            try:
                payload = json.loads(msg.value().decode("utf-8"))
                messages.append(payload)
            except Exception as e:
                st.warning(f"Failed to parse message: {e}")
        
        consumer.close()
    except Exception as e:
        st.warning(f"Failed to consume from Kafka: {e}")
    
    return messages


def _get_qdrant_anchors(limit: int = 10) -> List[models.Record]:
    """Retrieve anchors from Qdrant."""
    if st.session_state.qdrant_client is None:
        return []
    
    try:
        points, _ = st.session_state.qdrant_client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return points
    except Exception as e:
        st.warning(f"Failed to retrieve from Qdrant: {e}")
        return []


def _get_anchor_by_id(anchor_id: str) -> Optional[models.Record]:
    """Retrieve a specific anchor from Qdrant by ID."""
    if st.session_state.qdrant_client is None:
        return None
    
    try:
        records = st.session_state.qdrant_client.retrieve(
            collection_name=QDRANT_COLLECTION,
            ids=[anchor_id],
            with_payload=True,
            with_vectors=True,
        )
        return records[0] if records else None
    except Exception as e:
        st.warning(f"Failed to retrieve anchor {anchor_id}: {e}")
        return None


def _get_current_time() -> dt.datetime:
    """Get current simulated time."""
    return dt.datetime.now(dt.timezone.utc) + st.session_state.time_offset


def _send_recall_request(query: str, top_k: int = 5) -> str:
    """Send a recall request to Kafka."""
    request_id = str(uuid.uuid4())
    now = _get_current_time()
    
    request = {
        "request_id": request_id,
        "query": query,
        "now": now.isoformat(),
        "top_k": top_k,
        "session_id": None,
        "ignore_anchor_ids": [],
        "allow_session_matches": False,
    }
    
    try:
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        producer.produce("recall-request", json.dumps(request).encode("utf-8"))
        producer.flush()
        return request_id
    except Exception as e:
        st.error(f"Failed to send recall request: {e}")
        return None


def _consume_recall_response(request_id: str, timeout: float = 10.0) -> Optional[dict]:
    """Consume recall response from Kafka."""
    try:
        # Use a unique consumer group for each request to avoid offset issues
        unique_group = f"indexer-demo-recall-{uuid.uuid4()}"
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": unique_group,
            "auto.offset.reset": "earliest",  # Read from beginning to catch all messages
            "enable.auto.commit": False,  # Don't commit offsets
        })
        consumer.subscribe(["recall-response"])
        
        # Give consumer time to join group and get partition assignment
        # Also poll once to force partition assignment
        consumer.poll(0.0)
        time.sleep(0.3)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            msg = consumer.poll(1.0)  # Increased poll timeout
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    # End of partition, continue waiting
                    continue
                st.warning(f"Kafka error: {msg.error()}")
                continue
            
            try:
                payload = json.loads(msg.value().decode("utf-8"))
                if payload.get("request_id") == request_id:
                    consumer.close()
                    return payload
            except json.JSONDecodeError as e:
                st.warning(f"Failed to parse message: {e}")
                continue
            except Exception as e:
                st.warning(f"Error processing message: {e}")
                continue
        
        consumer.close()
        return None
    except Exception as e:
        st.warning(f"Failed to consume recall response: {e}")
        return None


def _calculate_decay_weight(stored_at_iso: str, now: dt.datetime) -> float:
    """Calculate decay weight using Ebbinghaus forgetting curve."""
    import math
    LAM = 0.002  # decay constant per day
    
    stored = dt.datetime.fromisoformat(stored_at_iso.replace("Z", "+00:00")).replace(
        tzinfo=None
    )
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    age_days = (now_naive - stored).days
    return math.exp(-LAM * max(age_days, 0))


def main():
    st.set_page_config(
        page_title="Indexer Service Demo",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()
    
    st.title("🔍 Indexer Service Demo & Testing")
    st.caption(
        "Test and visualize how the Indexer service processes memory anchors"
    )
    
    # Check service status and show warnings
    kafka_ok, kafka_msg = st.session_state.service_checks.get("kafka", (False, ""))
    qdrant_ok, qdrant_msg = st.session_state.service_checks.get("qdrant", (False, ""))
    
    if not kafka_ok or not qdrant_ok:
        with st.container():
            st.warning("⚠️ **Services Not Available**")
            if not kafka_ok:
                st.error(f"**Kafka** is not connected to `{KAFKA_BOOTSTRAP}`")
            if not qdrant_ok:
                st.error(f"**Qdrant** is not connected to `{QDRANT_URL}`")
            st.info("💡 Check the sidebar for connection status and setup instructions.")
            st.divider()
    
    # Sidebar: Configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Service Status
        st.subheader("🔌 Service Status")
        
        # Check Kafka
        kafka_ok, kafka_msg = _check_kafka_connection()
        if kafka_ok:
            st.success(f"✅ Kafka: `{KAFKA_BOOTSTRAP}`")
        else:
            st.error(f"❌ Kafka: Not connected")
            with st.expander("Kafka Connection Error", expanded=True):
                st.code(kafka_msg, language="text")
                st.markdown("""
                **To start Kafka:**
                
                **Option 1: Using Minikube (Recommended)**
                ```bash
                # Start Minikube cluster
                ./k8s/scripts/setup-cluster.sh
                
                # Deploy infrastructure
                kubectl apply -f k8s/infrastructure/
                
                # Port-forward Kafka to localhost
                kubectl port-forward -n vhm svc/kafka-service 9092:9092
                ```
                
                **Option 2: Using Docker Compose**
                ```bash
                # If you have docker-compose.yml
                docker compose up -d kafka
                ```
                
                **Option 3: Local Kafka Installation**
                - Install and start Kafka locally
                - Ensure it's running on `localhost:9092`
                """)
        
        # Check Qdrant
        qdrant_ok, qdrant_msg = _check_qdrant_connection()
        if qdrant_ok:
            st.success(f"✅ Qdrant: `{QDRANT_URL}`")
        else:
            st.error(f"❌ Qdrant: Not connected")
            with st.expander("Qdrant Connection Error", expanded=True):
                st.code(qdrant_msg, language="text")
                st.markdown("""
                **To start Qdrant:**
                
                **Option 1: Using Minikube (Recommended)**
                ```bash
                # Start Minikube cluster
                ./k8s/scripts/setup-cluster.sh
                
                # Deploy infrastructure
                kubectl apply -f k8s/infrastructure/
                
                # Port-forward Qdrant to localhost
                kubectl port-forward -n vhm svc/qdrant-service 6333:6333
                ```
                
                **Option 2: Using Docker**
                ```bash
                docker run -p 6333:6333 qdrant/qdrant:latest
                ```
                
                **Option 3: Local Qdrant Installation**
                - Install and start Qdrant locally
                - Ensure it's running on `http://localhost:6333`
                """)
        
        st.divider()
        
        st.info(f"**Kafka**: `{KAFKA_BOOTSTRAP}`\n\n**Qdrant**: `{QDRANT_URL}`\n\n**Collection**: `{QDRANT_COLLECTION}`")
        
        embedding_model = st.text_input(
            "Embedding Model",
            value=st.session_state.get("embedding_model", EMBEDDING_MODEL),
            help="Model used for embeddings (deterministic, ollama:bge-m3, etc.)",
        )
        st.session_state.embedding_model = embedding_model
        
        if st.button("🔄 Refresh Connections"):
            st.session_state.service_checks = {
                "kafka": _check_kafka_connection(),
                "qdrant": _check_qdrant_connection(),
            }
            try:
                st.session_state.qdrant_client = QdrantClient(url=QDRANT_URL)
                st.success("Refreshed connections!")
            except Exception as e:
                st.warning(f"Qdrant connection failed: {e}")
            st.rerun()
        
        st.divider()
        
        st.divider()
        st.subheader("⏰ Simulated Time")
        current_time = _get_current_time()
        st.info(f"**{_format_timestamp(current_time)}**")
        
        days_offset = st.session_state.time_offset.days
        if days_offset > 0:
            if days_offset < 365:
                st.caption(f"⏩ {days_offset} days ahead")
            else:
                st.caption(f"⏩ {days_offset // 365} year(s) ahead")
        
        if st.button("🔄 Reset Time"):
            st.session_state.time_offset = dt.timedelta(0)
            st.rerun()
        
        st.divider()
        
        if st.button("🧹 Clear History"):
            st.session_state.anchors_sent = []
            st.session_state.anchors_indexed = []
            st.session_state.recall_results = []
            st.rerun()
    
    # Main content: Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📝 Create Anchor",
        "📊 Processing Flow",
        "🗄️ Qdrant Storage",
        "🔬 Inspection",
        "⏰ Time & Recall",
    ])
    
    # Tab 1: Create Anchor
    with tab1:
        st.header("Create a New Memory Anchor")
        st.markdown(
            "Create an anchor (memory) and send it to the Indexer service via Kafka."
        )
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            anchor_text = st.text_area(
                "Anchor Text",
                placeholder="Enter the memory text here...",
                height=150,
                help="The text content of the memory anchor",
            )
        
        with col2:
            salience = st.slider(
                "Salience",
                min_value=0.3,
                max_value=2.5,
                value=1.0,
                step=0.1,
                help="Importance weight of this memory (0.3-2.5)",
            )
            
            meta_tags = st.text_input(
                "Tags (comma-separated)",
                placeholder="work, demo, meeting",
                help="Optional tags for categorization",
            )
        
        # Check service status before allowing actions
        kafka_ok, _ = st.session_state.service_checks.get("kafka", (False, ""))
        if not kafka_ok:
            st.warning("⚠️ Kafka is not connected. Please start Kafka and refresh connections in the sidebar.")
        
        if st.button("🚀 Send Anchor to Indexer", type="primary", disabled=not kafka_ok):
            if not anchor_text.strip():
                st.error("Please enter anchor text!")
            else:
                meta = {}
                if meta_tags.strip():
                    meta["tags"] = [tag.strip() for tag in meta_tags.split(",")]
                
                with st.spinner("Sending anchor to Kafka..."):
                    anchor = _send_anchor_to_kafka(anchor_text, salience, meta)
                    
                    if anchor:
                        st.session_state.anchors_sent.append({
                            **anchor,
                            "sent_at": dt.datetime.now(dt.timezone.utc),
                        })
                        st.success(f"✅ Anchor sent! ID: `{anchor['anchor_id']}`")
                        st.balloons()
                        time.sleep(0.5)
                        st.rerun()
        
        # Show sent anchors
        if st.session_state.anchors_sent:
            st.divider()
            st.subheader("📤 Sent Anchors")
            for idx, anchor in enumerate(reversed(st.session_state.anchors_sent), 1):
                with st.expander(
                    f"Anchor {idx}: {anchor['text'][:50]}...",
                    expanded=False,
                ):
                    st.json(anchor)
    
    # Tab 2: Processing Flow
    with tab2:
        st.header("Processing Flow Visualization")
        st.markdown(
            "Monitor the complete flow: Kafka → Indexer → Qdrant"
        )
        
        if st.button("🔄 Check for New Indexed Anchors"):
            with st.spinner("Consuming from Kafka..."):
                new_messages = _consume_indexed_anchors(timeout=3.0)
                
                for msg in new_messages:
                    if msg not in st.session_state.anchors_indexed:
                        st.session_state.anchors_indexed.append(msg)
        
        # Visualize flow
        if st.session_state.anchors_sent:
            st.subheader("📈 Flow Status")
            
            for anchor in reversed(st.session_state.anchors_sent[-5:]):
                anchor_id = anchor["anchor_id"]
                
                # Check if indexed
                indexed = any(
                    idx.get("anchor_id") == anchor_id
                    for idx in st.session_state.anchors_indexed
                )
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown("**1. Created**")
                    st.success("✅")
                    st.caption(_format_timestamp(anchor["sent_at"]))
                
                with col2:
                    st.markdown("**2. Kafka (anchors-write)**")
                    st.success("✅")
                    st.caption("Published")
                
                with col3:
                    st.markdown("**3. Indexer Processing**")
                    if indexed:
                        idx_msg = next(
                            (idx for idx in st.session_state.anchors_indexed
                             if idx.get("anchor_id") == anchor_id),
                            None,
                        )
                        if idx_msg and idx_msg.get("ok"):
                            st.success("✅ Indexed")
                        else:
                            st.error("❌ Failed")
                            if idx_msg:
                                st.caption(f"Reason: {idx_msg.get('reason', 'unknown')}")
                    else:
                        st.info("⏳ Waiting...")
                
                with col4:
                    st.markdown("**4. Qdrant Storage**")
                    qdrant_record = _get_anchor_by_id(anchor_id)
                    if qdrant_record:
                        st.success("✅ Stored")
                    else:
                        st.info("⏳ Not found yet")
                
                st.divider()
        
        # Show indexed results
        if st.session_state.anchors_indexed:
            st.subheader("📥 Indexed Results")
            for idx, result in enumerate(reversed(st.session_state.anchors_indexed), 1):
                status = "✅ Success" if result.get("ok") else "❌ Failed"
                st.markdown(f"**{idx}. {status}** - `{result.get('anchor_id', 'unknown')}`")
                if not result.get("ok"):
                    st.caption(f"Reason: {result.get('reason', 'unknown')}")
                with st.expander("View details"):
                    st.json(result)
    
    # Tab 3: Qdrant Storage
    with tab3:
        st.header("Qdrant Storage Inspection")
        st.markdown("View anchors stored in the Qdrant vector database.")
        
        limit = st.slider("Number of anchors to display", 1, 50, 10)
        
        if st.button("🔄 Refresh from Qdrant"):
            st.rerun()
        
        points = _get_qdrant_anchors(limit=limit)
        
        if points:
            st.success(f"Found {len(points)} anchor(s) in Qdrant")
            
            for idx, point in enumerate(points, 1):
                payload = point.payload or {}
                text = payload.get("text", "")
                stored_at = payload.get("stored_at", "?")
                salience = payload.get("salience", "?")
                meta = payload.get("meta", {})
                
                with st.expander(
                    f"Anchor {idx}: {text[:60]}{'...' if len(text) > 60 else ''}",
                    expanded=False,
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**ID**: `{point.id}`")
                        st.markdown(f"**Stored At**: {_format_timestamp(stored_at)}")
                        st.markdown(f"**Salience**: {salience}")
                    with col2:
                        st.markdown("**Metadata**:")
                        st.json(meta)
                    
                    st.markdown("**Full Text**:")
                    st.text(text)
                    
                    st.markdown("**Full Payload**:")
                    st.json(payload)
        else:
            st.info("No anchors found in Qdrant. Create some anchors first!")
    
    # Tab 4: Inspection
    with tab4:
        st.header("Detailed Inspection")
        st.markdown("Inspect a specific anchor in detail, including its embedding.")
        
        anchor_id_input = st.text_input(
            "Anchor ID",
            placeholder="Enter anchor ID to inspect...",
        )
        
        if anchor_id_input:
            record = _get_anchor_by_id(anchor_id_input)
            
            if record:
                st.success("✅ Anchor found!")
                
                payload = record.payload or {}
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Metadata")
                    st.json({
                        "id": record.id,
                        "text": payload.get("text", ""),
                        "stored_at": payload.get("stored_at"),
                        "salience": payload.get("salience"),
                        "meta": payload.get("meta", {}),
                    })
                
                with col2:
                    st.subheader("Embedding Info")
                    if record.vector:
                        dim = len(record.vector)
                        st.metric("Dimensions", dim)
                        st.metric("Model", st.session_state.get("embedding_model", "unknown"))
                        
                        # Show embedding preview
                        st.markdown("**Vector Preview (first 10 values)**:")
                        preview = record.vector[:10]
                        st.code(f"[{', '.join(f'{v:.4f}' for v in preview)}...]")
                        
                        # Embedding statistics
                        import numpy as np
                        vec_array = np.array(record.vector)
                        st.markdown("**Statistics**:")
                        st.json({
                            "min": float(np.min(vec_array)),
                            "max": float(np.max(vec_array)),
                            "mean": float(np.mean(vec_array)),
                            "std": float(np.std(vec_array)),
                            "norm": float(np.linalg.norm(vec_array)),
                        })
                    else:
                        st.warning("No vector data available")
            else:
                st.warning("Anchor not found in Qdrant. It may not have been indexed yet.")
    
    # Tab 5: Time Simulation & Recall
    with tab5:
        st.header("⏰ Time Simulation & Recall Testing")
        st.markdown(
            "Simulate time passing and test how memories are recalled with temporal decay."
        )
        
        # Time controls
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("Current Time")
            current_time = _get_current_time()
            st.info(f"**{_format_timestamp(current_time)}**")
            
            days_offset = st.session_state.time_offset.days
            if days_offset == 0:
                st.caption("🕐 Present time")
            elif days_offset < 7:
                st.caption(f"⏰ {days_offset} day(s) in the future")
            elif days_offset < 30:
                st.caption(f"⏰ {days_offset // 7} week(s) in the future")
            elif days_offset < 365:
                st.caption(f"⏰ {days_offset // 30} month(s) in the future")
            else:
                st.caption(f"⏰ {days_offset // 365} year(s) in the future")
        
        with col2:
            st.subheader("Advance Time")
            time_input = st.text_input(
                "Time to advance",
                placeholder="30d, 6m, 1y",
                help="Format: number followed by d (days), m (months), or y (years)",
            )
            
            col2a, col2b = st.columns(2)
            with col2a:
                if st.button("⏩ Advance", type="primary"):
                    if time_input.strip():
                        try:
                            amount = int(time_input[:-1])
                            unit = time_input[-1].lower()
                            
                            if unit == "d":
                                st.session_state.time_offset += dt.timedelta(days=amount)
                            elif unit == "m":
                                st.session_state.time_offset += dt.timedelta(days=amount * 30)
                            elif unit == "y":
                                st.session_state.time_offset += dt.timedelta(days=amount * 365)
                            else:
                                st.error("Invalid unit. Use d, m, or y")
                                st.rerun()
                            
                            st.success(f"Time advanced by {time_input}")
                            st.rerun()
                        except (ValueError, IndexError):
                            st.error("Invalid format. Use: 30d, 6m, 1y")
                    else:
                        st.warning("Please enter a time value")
            
            with col2b:
                if st.button("🔄 Reset Time"):
                    st.session_state.time_offset = dt.timedelta(0)
                    st.success("Time reset to present")
                    st.rerun()
        
        with col3:
            st.subheader("Quick Presets")
            if st.button("1 Week"):
                st.session_state.time_offset += dt.timedelta(days=7)
                st.rerun()
            if st.button("1 Month"):
                st.session_state.time_offset += dt.timedelta(days=30)
                st.rerun()
            if st.button("1 Year"):
                st.session_state.time_offset += dt.timedelta(days=365)
                st.rerun()
        
        st.divider()
        
        # Recall testing
        st.subheader("Test Recall with Simulated Time")
        st.markdown(
            "Query your stored memories and see how activation scores change based on time."
        )
        
        recall_query = st.text_input(
            "Recall Query",
            placeholder="Tell me about...",
            help="Enter a query to search for relevant memories",
        )
        
        col_recall1, col_recall2 = st.columns([3, 1])
        with col_recall1:
            top_k = st.slider("Top K results", 1, 10, 5)
        
        with col_recall2:
            st.write("")  # Spacing
            st.write("")  # Spacing
            if st.button("🔍 Recall Memories", type="primary"):
                if not recall_query.strip():
                    st.error("Please enter a query!")
                else:
                    with st.spinner("Sending recall request and waiting for response..."):
                        request_id = _send_recall_request(recall_query, top_k)
                        if request_id:
                            response = _consume_recall_response(request_id, timeout=10.0)
                            
                            if response:
                                response["query"] = recall_query
                                response["simulated_time"] = current_time.isoformat()
                                st.session_state.recall_results.append(response)
                                st.success(f"✅ Recall completed! Found {len(response.get('beats', []))} memory(ies)")
                                st.rerun()
                            else:
                                st.warning("⏳ No response received. Make sure the Resonance worker is running.")
        
        # Show recall results
        if st.session_state.recall_results:
            st.divider()
            st.subheader("📊 Recall Results")
            
            for idx, result in enumerate(reversed(st.session_state.recall_results), 1):
                query = result.get("query", "Unknown query")
                beats = result.get("beats", [])
                sim_time = result.get("simulated_time", "")
                
                with st.expander(
                    f"Recall {idx}: '{query[:50]}{'...' if len(query) > 50 else ''}' - {len(beats)} result(s)",
                    expanded=(idx == 1),
                ):
                    st.caption(f"Simulated time: {_format_timestamp(sim_time)}")
                    
                    if beats:
                        for beat_idx, beat in enumerate(beats, 1):
                            st.markdown(f"**Beat {beat_idx}**")
                            
                            col_beat1, col_beat2 = st.columns([3, 1])
                            with col_beat1:
                                st.write(beat.get("text", ""))
                                st.caption(
                                    f"Age: {beat.get('perceived_age', '?')} | "
                                    f"Activation: {beat.get('activation', 0):.4f}"
                                )
                            
                            with col_beat2:
                                # Show decay visualization
                                anchor_id = beat.get("anchor_id")
                                if anchor_id:
                                    anchor_record = _get_anchor_by_id(anchor_id)
                                    if anchor_record:
                                        payload = anchor_record.payload or {}
                                        stored_at = payload.get("stored_at")
                                        if stored_at:
                                            decay = _calculate_decay_weight(
                                                stored_at, current_time
                                            )
                                            st.metric("Decay", f"{decay:.3f}")
                                            
                                            # Show how decay would change over time
                                            stored = dt.datetime.fromisoformat(
                                                stored_at.replace("Z", "+00:00")
                                            )
                                            age_days = (current_time.replace(tzinfo=None) - stored.replace(tzinfo=None)).days
                                            st.caption(f"{age_days} days old")
                            
                            if beat_idx < len(beats):
                                st.divider()
                    else:
                        st.info("No memories found for this query.")
        
        # Decay visualization
        if st.session_state.recall_results and st.session_state.anchors_sent:
            st.divider()
            st.subheader("📈 Decay Over Time Visualization")
            
            selected_anchor_id = st.selectbox(
                "Select an anchor to visualize decay",
                options=[a["anchor_id"] for a in st.session_state.anchors_sent],
                format_func=lambda x: next(
                    (a["text"][:50] + "..." if len(a["text"]) > 50 else a["text"]
                     for a in st.session_state.anchors_sent if a["anchor_id"] == x),
                    x,
                ),
            )
            
            if selected_anchor_id:
                anchor = next(
                    (a for a in st.session_state.anchors_sent if a["anchor_id"] == selected_anchor_id),
                    None,
                )
                if anchor:
                    stored_at = anchor.get("stored_at")
                    if stored_at:
                        # Calculate decay at different time points
                        time_points = [0, 7, 30, 90, 180, 365, 730]  # days
                        base_time = dt.datetime.fromisoformat(
                            stored_at.replace("Z", "+00:00")
                        )
                        
                        decay_values = []
                        labels = []
                        for days in time_points:
                            future_time = base_time + dt.timedelta(days=days)
                            decay = _calculate_decay_weight(stored_at, future_time)
                            decay_values.append(decay)
                            labels.append(f"{days}d")
                        
                        # Show chart
                        df = pd.DataFrame({
                            "Days": labels,
                            "Decay Weight": decay_values,
                        })
                        
                        st.line_chart(df.set_index("Days"))
                        st.caption(
                            "Ebbinghaus forgetting curve: exp(-0.002 × days). "
                            "Shows how memory strength decreases over time."
                        )


if __name__ == "__main__":
    main()

