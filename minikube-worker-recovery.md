# Minikube Worker Recovery Guide

Hello future padawan! This scroll captures how we unblocked the VHM workers on Minikube so you can avoid the crash-loop dojo trap next time.

---

## 1. What Was Broken
- Worker pods (`indexer`, `resonance`, `reteller`) were stuck in `CrashLoopBackOff`.
- Images referenced in the manifests lacked required Python packages and couldn’t see shared code.
- Worker modules imported config constants that didn’t exist, causing runtime `ImportError`s.
- ConfigMap/Secret were missing several env values—pods never received defaults.
- The startup script generated inside the container had broken quoting, so even valid images crashed on entry.

## 2. Fixes Applied (TL;DR Table)
| Area | What we changed | Why it matters |
| --- | --- | --- |
| Shared config (`common/utils/vhm_common_utils/config.py`) | Added `_read_env` helper + defined all env vars (Kafka alias, Ollama/OpenAI/Portkey knobs, resonance tuning). | Prevents import crashes and keeps defaults in one place. |
| ConfigMap (`k8s/config/configmap.yaml`) | Added matching keys for all non-secret env vars. | Kubernetes now injects the settings pods expect. |
| Secret (`k8s/config/secrets.yaml`) | Added optional `OPENAI_API_KEY` placeholder. | Keeps manifests consistent; optional/empty is allowed. |
| Worker Deployments | Wired new env vars into `resonance` & `reteller`. | Pods receive the data they import. |
| Docker build (`docker/worker.Dockerfile`) | New shared image: installs deps with `uv`, copies `common` + `workers`, sets sane entrypoint. | Every worker now has the right libraries and code. |
| Entry point | Generates simple shell launcher using `$WORKER_MODULE`. | Same image works for all workers; no quoting bugs. |
| PYTHONPATH | Set to `/app:/app/common/utils`. | Imports like `from vhm_common_utils import ...` finally resolve inside the container. |
| Images | `eval "$(minikube docker-env)"` then rebuilt `vhm-indexer:0.1.1`, `vhm-resonance:0.1.0`, `vhm-reteller:0.1.0`. | Minikube now has fresh images; pods stop pulling broken ones. |
| Resonance worker (`workers/vhm_resonance/main.py`) | Modular refactor with typed settings, structured logging, and Qdrant retry logic. | Recall stays stable under transient broker hiccups and is easier to debug. |
| Deployments | `kubectl rollout restart deployment/<worker> -n vhm`. | Forces K8s to pick up the new images and env. |

---

## 3. Why It Works Now
1. **Images are self-contained** – All dependencies listed in `requirements.txt` are baked into the container, eliminating `ModuleNotFoundError`.
2. **Shared code available** – Copying `common/` alongside `workers/` plus the new `PYTHONPATH` means imports resolve.
3. **Config surface aligned** – The Python config module, ConfigMap, Secret, and deployments now agree on variable names and defaults.
4. **Stable entrypoint** – A small shell wrapper launches `python -m <module>` with the correct module per worker image build.
5. **Minikube-aware build** – Building inside Minikube’s Docker daemon stops ImagePull errors and guarantees pods see the new layers.

---

## 4. How to Reproduce the Fix (Cheat Sheet)
```bash
# 0. Start minikube via provided script (ensures namespace/addons)
./k8s/scripts/setup-cluster.sh

# 1. Point Docker CLI at Minikube
eval "$(minikube docker-env)"

# 2. Build each worker image using the shared Dockerfile
docker build -t vhm-indexer:0.1.1 \
  -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_indexer.main .

docker build -t vhm-resonance:0.1.0 \
  -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_resonance.main .

docker build -t vhm-reteller:0.1.0 \
  -f docker/worker.Dockerfile \
  --build-arg WORKER_MODULE=workers.vhm_reteller.main .

# 3. Reapply config (optional but safe)
kubectl apply -f k8s/config/

# 4. Restart deployments
kubectl rollout restart deployment/indexer -n vhm
kubectl rollout restart deployment/resonance -n vhm
kubectl rollout restart deployment/reteller -n vhm

# 5. Verify
kubectl get pods -n vhm
kubectl logs -f deployment/indexer -n vhm
```

To return Docker to the host daemon later:
```bash
eval "$(minikube docker-env -u)"
```

---

## 5. What to Watch During Ops
- **Kafka Topics Missing**: logs warn about `UNKNOWN_TOPIC_OR_PART`. Create topics (`anchors-write`, `recall-request`, `recall-response`) via `kafka-topics.sh` or let the publisher create them.
- **Secrets**: `OPENAI_API_KEY` and `PORTKEY_API_KEY` are optional. Keep them empty if not using those providers.
- **Image Drift**: If code changes, rebuild images using the same commands. Forgetting to rebuild = pods still run old code.
- **Docker Context**: Always confirm `eval "$(minikube docker-env)"` is active before building, or images land on the host daemon and Minikube won’t see them.
- **Health Probes**: All workers run a FastAPI health server on port 8080. `kubectl get pods` should show `READY 1/1` once the `/health` endpoint passes.
- **Resonance Logs**: Tail resonance with `kubectl logs` and tweak verbosity via `RESONANCE_LOG_LEVEL`. Expect structured INFO/ERROR entries with request IDs.

---

## 6. Next Steps for Mastery
1. Seed Kafka with required topics or add automation to create them on startup.
2. Push these images to a registry (GitHub Container Registry, Docker Hub, etc.) for CI/CD parity.
3. Consider templating the worker deployment YAMLs or move to Helm to avoid env drift.
4. Add unit tests around `vhm_common_utils.config` to catch missing env vars early.
5. Enhance the README to link this guide for future dojo trainees.

---

## 7. Quick Checklist (Printable)
- [ ] `minikube start` (or `setup-cluster.sh`)
- [ ] `eval "$(minikube docker-env)"`
- [ ] Build `vhm-indexer`, `vhm-resonance`, `vhm-reteller`
- [ ] `kubectl apply -f k8s/config/`
- [ ] `kubectl rollout restart` each worker
- [ ] `kubectl get pods -n vhm` → all `Running`
- [ ] Create Kafka topics (if absent)
- [ ] `eval "$(minikube docker-env -u)"` when done

---

You’re now armed with the same kata that freed the cluster from the CrashLoop dojo. Go forth and wield it wisely! 🚀

