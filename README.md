# Virtual Human Memory (VHM)

[![utils](https://github.com/Research-Group-IxD/vhm-common-utils/actions/workflows/ci.yml/badge.svg)](https://github.com/Research-Group-IxD/vhm-common-utils/actions/workflows/ci.yml)

This repository is the central workspace for the Virtual Human Memory (VHM) project, a multi-agent, psychologically-grounded, long-term memory system for virtual humans. Our goal is to enable emergent identity through the stories virtual humans tell over time.

**[➡️ View the full Project Page here](https://research-group-ixd.github.io/virtual-human-memory/)**

## Architecture

The VHM system is built on a distributed, microservices architecture. This workspace coordinates the following core services, which are included as Git submodules:

- `vhm-worker-indexer`: Ingests and indexes new memories.
- `vhm-worker-resonance`: Calculates the emotional and contextual significance of memories.
- `vhm-worker-reteller`: Weaves memories into coherent, dynamic narratives.
- `vhm-common-utils`: Shared utilities and data models for all services.
- `vhm-k8s-manifests`: Kubernetes manifests for deploying the system.

## Getting Started

To clone this workspace and all its submodules, run:

```bash
git clone --recurse-submodules https://github.com/Research-Group-IxD/virtual-human-memory.git
```

If you have already cloned the repository without the submodules, you can initialize them with:

```bash
git submodule update --init --recursive
```

For detailed information about the project's architecture, research goals, and results, please see our [full project page](https://research-group-ixd.github.io/virtual-human-memory/).
