# Test Guide

This guide explains the test suite for the Virtual Human Memory project, focusing on the indexer worker. It is designed to help new contributors understand how tests are organized, how to run them, and how to navigate the test codebase.

## Introduction

The test suite provides comprehensive coverage for the indexer worker, which is responsible for ingesting and indexing new memories. Tests are organized into unit tests (testing individual functions in isolation) and integration tests (testing complete workflows).

### What is Tested?

The test suite covers the following indexer functionality:

- **Anchor Processing**: Creating and storing memory anchors in Qdrant
- **Immutability Enforcement**: Ensuring anchors cannot be overwritten once created
- **Collection Management**: Creating and managing Qdrant collections with correct vector dimensions
- **Error Handling**: Graceful handling of database errors and edge cases

### Test Location

All indexer tests are located in `workers/indexer/tests/`:

- `test_indexer_units.py` - Unit tests for individual functions
- `test_indexer_integration.py` - Integration tests for complete workflows

## Test Structure

### Test Organization

The test suite follows a clear organizational structure:

```
workers/indexer/tests/
├── __init__.py
├── test_indexer_units.py      # Unit tests (9 tests)
└── test_indexer_integration.py # Integration tests (2 tests)
```

### Test Categories

#### Unit Tests (`test_indexer_units.py`)

Unit tests focus on testing individual functions in isolation, with all external dependencies mocked. These tests verify:

- `process_anchor()` - Anchor processing logic
- `ensure_collection()` - Qdrant collection management
- `anchor_exists()` - Anchor existence checks

#### Integration Tests (`test_indexer_integration.py`)

Integration tests verify the interaction between components, testing complete workflows:

- Full anchor processing flow from start to finish
- Immutability enforcement in the complete workflow

## Understanding Test Components

### Fixtures (`conftest.py`)

Fixtures are reusable test helpers defined in the root `conftest.py` file. They provide mock objects and sample data that are automatically available to all tests.

Available fixtures:

- `mock_qdrant_client` - A mock QdrantClient for testing database operations
- `mock_get_embedding` - A mock embedding function that returns deterministic embeddings
- `sample_anchor` - A sample Anchor model instance for testing
- `sample_anchor_payload` - A sample anchor as a dictionary

**How to use fixtures:**

Fixtures are automatically injected into test functions as parameters. Simply include the fixture name as a parameter:

```python
def test_example(mock_qdrant_client, sample_anchor):
    # mock_qdrant_client and sample_anchor are automatically provided
    result = process_anchor(sample_anchor, mock_qdrant_client)
    assert result["ok"] is True
```

### Test Naming Conventions

Tests follow a clear naming pattern:

- All test functions must start with `test_` (pytest requirement)
- Pattern: `test_<function>_<scenario>`
- Examples:
  - `test_anchor_exists_true` - Tests that `anchor_exists()` returns True
  - `test_process_anchor_success` - Tests successful anchor processing
  - `test_ensure_collection_creates_new` - Tests collection creation

### Test Structure (AAA Pattern)

All tests follow the Arrange-Act-Assert (AAA) pattern:

1. **Arrange** (Setup) - Prepare test data and configure mocks
2. **Act** (Execute) - Call the function being tested
3. **Assert** (Verify) - Check that the results are correct

Example:

```python
def test_anchor_exists_true(mock_qdrant_client):
    # Arrange: Configure mock to return an anchor
    mock_qdrant_client.retrieve.return_value = [Mock()]
    
    # Act: Call the function
    result = anchor_exists(mock_qdrant_client, "test-id")
    
    # Assert: Verify the result
    assert result is True
    mock_qdrant_client.retrieve.assert_called_once()
```

## Running Tests

### Basic Commands

Run all tests:

```bash
uv run pytest workers/indexer/tests/ -v
```

Run only unit tests:

```bash
uv run pytest workers/indexer/tests/test_indexer_units.py -v
```

Run only integration tests:

```bash
uv run pytest workers/indexer/tests/test_indexer_integration.py -v
```

### Running Specific Tests

Run a single test:

```bash
uv run pytest workers/indexer/tests/test_indexer_units.py::test_anchor_exists_true -v
```

### Debugging Tests

Stop at first failure with detailed output:

```bash
uv run pytest workers/indexer/tests/ -x -vv
```

Drop into Python debugger on failure:

```bash
uv run pytest workers/indexer/tests/ --pdb
```

View test output (print statements):

```bash
uv run pytest workers/indexer/tests/ -s
```

### Viewing Test Information

List all available tests without running them:

```bash
uv run pytest workers/indexer/tests/ --collect-only
```

List only test names:

```bash
uv run pytest workers/indexer/tests/ --collect-only -q
```

### Test Coverage

View which code is covered by tests:

```bash
uv run pytest workers/indexer/tests/ --cov=workers.vhm_indexer
```

## Navigating Tests

### How to Read a Test

When reading a test for the first time, follow these steps:

1. **Read the docstring** - Each test has a description explaining what it tests
2. **Examine the setup** - Look at what mocks are configured and what data is prepared
3. **Find the function call** - Identify which function is being tested
4. **Check the assertions** - See what conditions must be met for the test to pass

### Understanding Test Code

**Example: Simple Test**

```python
def test_anchor_exists_true(mock_qdrant_client):
    """Test anchor_exists returns True when the anchor exists."""
    # Setup: Mock returns an anchor (simulating it exists)
    mock_qdrant_client.retrieve.return_value = [Mock()]
    
    # Execute: Call the function
    result = anchor_exists(mock_qdrant_client, "test-id")
    
    # Verify: Result is True and retrieve was called once
    assert result is True
    mock_qdrant_client.retrieve.assert_called_once()
```

**What this test does:**

1. Configures the mock Qdrant client to return a mock object (simulating an existing anchor)
2. Calls `anchor_exists()` with a test ID
3. Verifies that the function returns `True` and that the `retrieve` method was called exactly once

### Tips for Understanding Tests

1. **Compare related tests** - Reading `test_anchor_exists_true` and `test_anchor_exists_false` together helps understand both success and failure cases

2. **Follow the code** - Use your IDE's "Go to Definition" feature (Cmd+Click / Ctrl+Click) to jump from test code to the actual implementation

3. **Read in order** - Start with simpler tests and work toward more complex ones:
   - `test_anchor_exists_true` (simplest)
   - `test_anchor_exists_false` (similar)
   - `test_process_anchor_success` (more complex)
   - `test_process_anchor_immutability_violation` (edge case)
   - `test_ensure_collection_*` (collection management)
   - Integration tests (complete workflows)

## Common Questions

### What is a mock?

A mock is a fake version of an object (like a database or function) that behaves in a controlled way. Mocks allow tests to run without needing real external dependencies like Qdrant or Kafka.

### Why use fixtures?

Fixtures provide reusable test setup code. Instead of creating mocks in every test, fixtures define them once and make them available to all tests automatically.

### What does `assert_called_once()` do?

This assertion verifies that a mocked function was called exactly once (not zero times, not twice). It's used to ensure functions are called the expected number of times.

### What is `return_value`?

`return_value` is a property of mocks that defines what value the mock should return when called. For example:

```python
mock_qdrant_client.retrieve.return_value = [Mock()]
```

This means: "When `retrieve()` is called, return a list containing one Mock object."

### Why do we test this?

Tests ensure that code works as expected, even when changes are made later. They provide confidence that:
- New features don't break existing functionality
- Refactoring doesn't introduce bugs
- The code behaves correctly in edge cases

### How do I add a new test?

1. Create a test function starting with `test_`
2. Use fixtures as parameters for any mocks or sample data you need
3. Follow the AAA pattern (Arrange, Act, Assert)
4. Add a docstring explaining what the test verifies

Example:

```python
def test_new_feature(mock_qdrant_client, sample_anchor):
    """Test that new feature works correctly."""
    # Arrange
    mock_qdrant_client.some_method.return_value = expected_value
    
    # Act
    result = function_under_test(sample_anchor, mock_qdrant_client)
    
    # Assert
    assert result["ok"] is True
```

## Reference: Quick Command Cheat Sheet

```bash
# Run all tests
uv run pytest workers/indexer/tests/ -v

# Run specific test file
uv run pytest workers/indexer/tests/test_indexer_units.py -v

# Run specific test
uv run pytest workers/indexer/tests/test_indexer_units.py::test_anchor_exists_true -v

# Run with output visible
uv run pytest workers/indexer/tests/ -s

# Run with coverage
uv run pytest workers/indexer/tests/ --cov=workers.vhm_indexer

# List all tests
uv run pytest workers/indexer/tests/ --collect-only -q

# Debug mode (stop at first failure)
uv run pytest workers/indexer/tests/ -x -vv
```
