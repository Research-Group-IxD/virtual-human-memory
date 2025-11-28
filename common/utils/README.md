# VHM Common Utilities

[![utils](https://github.com/Research-Group-IxD/vhm-common-utils/actions/workflows/ci.yml/badge.svg)](https://github.com/Research-Group-IxD/vhm-common-utils/actions/workflows/ci.yml)

This repository contains shared Python utilities and data models for the Virtual Human Memory (VHM) project. It provides a centralized place for common code, ensuring consistency and reusability across all VHM worker services.

## Features

- **Configuration Management**: Centralized Pydantic settings for managing environment variables.
- **Data Models**: Shared Pydantic models for Kafka message payloads.
- **Embedding Service**: A unified interface for generating text embeddings from various providers (Ollama, Portkey, etc.).

## Usage

Install this library in your worker services using a local path in your `pyproject.toml`:

```toml
[tool.uv.sources]
vhm-common-utils = { path = "../common/utils" }
```
