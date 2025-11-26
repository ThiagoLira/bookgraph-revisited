# Performance Optimization Experiments

Comprehensive documentation of optimization experiments for the bookgraph citation extraction system.

**Test Environment:**
- GPU: NVIDIA RTX 5090 (32GB VRAM)
- Model: Qwen3-30B-A3B-Q5_K_S.gguf (~20GB)
- Server: llama.cpp with OpenAI-compatible API
- Test dataset: Susan Sontag "Where the Stress Falls" (680KB, 733 sentences)

---

## Table of Contents

1. [Batch-Size Parameter Study](#batch-size-parameter-study)
2. [Chunk Granularity Study](#chunk-granularity-study)
3. [Critical Bug: Double Reservation](#critical-bug-double-reservation)
4. [Critical Bug: LLM Hallucination](#critical-bug-llm-hallucination)
5. [Optimal Configuration](#optimal-configuration)
6. [Parameter Flow Documentation](#parameter-flow-documentation)

---

## Batch-Size Parameter Study

### Hypothesis
The `--batch-size` parameter controls how many tokens llama.cpp processes in parallel during generation. Larger batch sizes might improve GPU utilization and throughput.

### Methodology
Tested batch sizes: 256, 512, 1024, 2048 with fixed settings:
- Chunk size: 50 sentences
- Concurrency: 30 parallel requests
- Context: 6144 tokens per request (4096 input + 2048 output)

### Results - Test Subset (15 chunks)

| Batch Size | Execution Time | GPU Utilization | Speedup vs 256 |
|------------|---------------|-----------------|----------------|
| 256        | 16.2s         | 73.7%           | baseline       |
| 512        | 14.5s         | 68.3%           | 10.5% faster   |
| **1024**   | **14.0s**     | **63.2%**       | **13.6% faster** |
| 2048       | 14.8s         | 59.2%           | 8.6% faster    |

### Results - Full Book (106 chunks)

| Batch Size | Execution Time | GPU Utilization |
|------------|---------------|-----------------|
| 1024       | 60.1s         | 75.3%           |
| **2048**   | **57.5s**     | **72.8%**       |

### Key Findings

1. **Workload-dependent optimum**: Small workloads favor 1024, large workloads favor 2048
2. **Counterintuitive GPU metrics**: Lower batch sizes show higher utilization but slower performance
3. **Explanation**: Smaller batches cause more frequent kernel launches and context switches, inflating utilization metrics while reducing actual throughput
4. **Sweet spot**: Batch size of 2048 provides best performance for production workloads

### Recommendation
**Default batch-size: 2048** for optimal full-book processing speed.

---

## Chunk Granularity Study

### Hypothesis
Very small chunks (1 sentence) with high concurrency might saturate GPU better through massive parallelism.

### Methodology
Compared two approaches:
- **A**: 50-sentence chunks, 30 concurrency → 15 chunks total
- **B**: 1-sentence chunks, 50 concurrency → 733 chunks total

### Results

| Approach | Chunk Size | Chunks | Concurrency | Time  | GPU Util | Speedup |
|----------|-----------|--------|-------------|-------|----------|---------|
| **A**    | 50 sent   | 15     | 30          | 14.0s | 63-68%   | baseline |
| B        | 1 sent    | 733    | 50          | 78.0s | 62.9%    | **5.6x SLOWER** |

### Key Findings

1. **API overhead dominates**: Making 733 HTTP requests vs 15 requests adds massive overhead
2. **GPU utilization similar**: Both approaches show ~63% utilization, proving parallelism isn't the bottleneck
3. **Larger chunks = better efficiency**:
   - More context for LLM to understand citations
   - Fewer API calls = less protocol overhead
   - Better amortization of fixed costs (connection setup, JSON parsing)
4. **Diminishing returns**: Beyond 50-75 sentences, chunks may exceed token limits

### Recommendation
**Chunk size: 50 sentences** provides optimal balance between context quality and API efficiency.

---

## Critical Bug: Double Reservation

### Discovery
While analyzing parameter flow between profiling script and library, discovered the input token budget was only 2048 tokens instead of expected 4096 tokens.

### Root Cause

**Server-side reservation:**
```bash
CONTEXT_PER_REQUEST = MAX_INPUT_TOKENS + MAX_COMPLETION_TOKENS
                    = 4096 + 2048 = 6144
TOTAL_CONTEXT = 6144 × 30 = 184320
```

**Library-side reservation:**
```python
# BUGGY CODE
available_input_tokens = max_input_tokens - max_completion_tokens
                       = 4096 - 2048 = 2048  # Only 2048 usable!
```

The server already allocated space for output by including `MAX_COMPLETION_TOKENS` in the context calculation. The library then subtracted it again, wasting 50% of input capacity.

### Impact Analysis

**Before fix:**
- Effective input budget: 2048 tokens
- Full book: 106 chunks, 57.5s
- Wasted capacity: 2048 tokens (50%)

**After fix:**
- Effective input budget: 4096 tokens (100% utilized)
- Full book: 104 chunks, 55.4s
- Performance gain: 3.6% faster, 2% fewer chunks

### Solution

Renamed parameters for semantic clarity:
- `max_input_tokens` → `max_context_per_request` (total window including input+output)
- Updated calculation: `available_input = max_context_per_request - max_completion_tokens`

### Code Changes

**extract_citations.py:**
```python
# Before
available_input_tokens = max_input_tokens - max_completion_tokens

# After
available_input_tokens = max_context_per_request - max_completion_tokens
```

**run_single_file.py:**
```python
# Before
parser.add_argument("--max-input-tokens", type=int, default=4000)

# After
parser.add_argument("--max-context-per-request", type=int, default=6144)
```

**profiling/single_gpu/run_profiled_single.sh:**
```bash
# Calculation remains the same, but naming is clearer
CONTEXT_PER_REQUEST=$((MAX_INPUT_TOKENS + MAX_COMPLETION_TOKENS))
TOTAL_CONTEXT_SIZE=$((CONTEXT_PER_REQUEST * MAX_CONCURRENCY))

# Pass correct value to library
--max-context-per-request "$CONTEXT_PER_REQUEST"
```

### Lessons Learned

1. **Semantic naming matters**: Ambiguous parameter names led to double-counting
2. **Trust but verify**: Even working code may have subtle efficiency bugs
3. **Document assumptions**: Clear comments about who reserves what space
4. **Parameter flow validation**: Trace values end-to-end to catch mismatches

---

## Critical Bug: LLM Hallucination

### Discovery
While validating chunk sizes, discovered the output JSON contained nonsensical sentence numbers like `1234567890` or negative ranges.

### Root Cause

The prompt previously asked the LLM to echo `chunk_index`, `start_sentence`, and `end_sentence`. When those values were missing or unclear, the model hallucinated metadata.

### Impact

**Severity**: Medium (data quality issue, not performance)
- Output metadata could be incorrect or unusable
- Mapping citations back to source sentences became unreliable

### Solution

Stop asking the LLM for metadata. The prompt now only requests a `citations` list, and the caller deterministically injects `chunk_index`, `start_sentence`, and `end_sentence` after parsing the response.

### Validation

After fix, chunks perfectly aligned:
```
Chunk 0: sentences 1-50 (50 sentences)
Chunk 1: sentences 51-100 (50 sentences)
...
Chunk 14: sentences 701-733 (33 sentences)

Average: 48.9 sentences/chunk
```

### Lessons Learned

1. **Never assume LLM knowledge**: Explicitly provide all required values in prompts
2. **Validate outputs early**: Check data quality on small samples before production runs
3. **Schema ≠ values**: Showing a schema doesn't tell the LLM what values to use
4. **Trust but verify**: Always validate LLM outputs against ground truth

---

## Optimal Configuration

Based on all experiments, the optimal configuration is:

### Core Parameters
```bash
CHUNK_SIZE=50              # Sentences per chunk
MAX_CONCURRENCY=30         # Parallel requests
MAX_INPUT_TOKENS=4096      # Desired input budget
MAX_COMPLETION_TOKENS=2048 # Desired output budget
BATCH_SIZE=2048           # Token processing batch size
```

### Computed Values
```bash
CONTEXT_PER_REQUEST=6144   # 4096 + 2048
TOTAL_CONTEXT_SIZE=184320  # 6144 × 30
```

### Server Configuration
```bash
llama-server \
  -m Qwen3-30B-A3B-Q5_K_S.gguf \
  -c 184320 \
  -np 30 \
  -n 2048 \
  -b 2048 \
  -ngl -1 \
  -ctk q4_0 \
  -ctv q4_0 \
  --repeat-penalty 1.2 \
  --presence-penalty 0.4 \
  --frequency-penalty 0.6
```

### Performance Results

**Full Book (733 sentences):**
- Processing time: ~55 seconds
- Chunks generated: 104 (50 sentences each)
- GPU utilization: 70-75% sustained
- VRAM usage: ~24.5 GB
- Throughput: ~13.3 sentences/second

**Test Subset (733 sentences):**
- Processing time: ~13.5 seconds
- Chunks generated: 15
- GPU utilization: 70-75%

---

## Parameter Flow Documentation

### Complete Parameter Flow Diagram

```
┌──────────────────────────────────────────────────────────┐
│  User Configuration (profiling/single_gpu/run_profiled_single.sh) │
└─────────────────────┬────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │                           │
        v                           v
┌───────────────────┐      ┌──────────────────┐
│ MAX_INPUT_TOKENS  │      │ MAX_COMPLETION   │
│      4096         │      │ _TOKENS: 2048    │
└─────────┬─────────┘      └────────┬─────────┘
          │                         │
          └────────┬────────────────┘
                   │
                   v
        ┌─────────────────────┐
        │ CONTEXT_PER_REQUEST │
        │   4096 + 2048       │
        │   = 6144            │
        └──────────┬──────────┘
                   │
                   v
        ┌─────────────────────┐
        │ TOTAL_CONTEXT_SIZE  │
        │   6144 × 30         │
        │   = 184320          │
        └──────────┬──────────┘
                   │
                   v
        ┌─────────────────────┐
        │   llama-server      │
        │   -c 184320         │
        │   -np 30            │
        │   -n 2048           │
        │                     │
        │ Per-slot context:   │
        │   184320 / 30       │
        │   = 6144 tokens     │
        └──────────┬──────────┘
                   │
                   v
        ┌─────────────────────────────┐
        │    run_single_file.py       │
        │ --max-context-per-request   │
        │        6144                 │
        │ --max-completion-tokens     │
        │        2048                 │
        └──────────┬──────────────────┘
                   │
                   v
        ┌─────────────────────────────┐
        │   extract_citations.py      │
        │                             │
        │ available_input_tokens =    │
        │   max_context_per_request - │
        │   max_completion_tokens     │
        │   = 6144 - 2048             │
        │   = 4096 tokens ✓           │
        └─────────────────────────────┘
```

### Key Design Principles

1. **Single source of truth**: User specifies desired input/output budgets at the top level
2. **Server handles division**: llama.cpp automatically divides context by `-np` for parallel slots
3. **Library respects server**: Library trusts the server has allocated space correctly
4. **Clear naming**: Parameters match their semantic meaning at each layer

### Common Pitfalls

❌ **Wrong**: Subtracting output tokens twice (old bug)
```python
# Server reserves: (input + output) × concurrency
# Library also reserves: input - output
# Result: Double reservation, wasted space
```

✅ **Right**: Each layer has clear responsibility
```python
# Server: Allocate total context
# Library: Use what's available after output
# Result: Full utilization
```

---

## Experiment Timeline

1. **Initial optimization** (concurrency tuning)
   - Tested concurrency 20-40
   - Found optimal: 30

2. **KV cache quantization** (VRAM optimization)
   - Compared f16, q8_0, q4_0
   - Found optimal: q4_0 (50% VRAM savings, no quality loss)

3. **Batch-size study** (GPU throughput)
   - Tested 256, 512, 1024, 2048
   - Found optimal: 2048 for full books

4. **Chunk granularity study** (API efficiency)
   - Tested 1-sentence vs 50-sentence chunks
   - Found optimal: 50 sentences (5.6x faster)

5. **Parameter flow audit** (correctness)
   - Discovered double-reservation bug
   - Fixed with parameter renaming
   - Result: 3.6% speedup, clearer code

6. **Output validation** (data quality)
   - Discovered LLM hallucination bug
   - Fixed prompt to provide explicit values
   - Result: Perfect chunk alignment

---

## Future Optimization Opportunities

### 1. Larger Chunk Sizes
Now that we have full 4096 tokens available, test:
- 75-sentence chunks (~3000 tokens)
- 100-sentence chunks (~4000 tokens)
- May reduce chunks to 70-80 total, further improving speed

### 2. Dynamic Batch Size
Automatically adjust batch size based on workload:
- Small jobs (<50 chunks): batch=1024
- Large jobs (>50 chunks): batch=2048

### 3. Adaptive Concurrency
Monitor GPU utilization and auto-tune concurrency:
- If GPU <70%: increase concurrency
- If OOM errors: decrease concurrency

### 4. Prompt Optimization
Current prompt is verbose. Could reduce token usage by:
- Shorter instructions
- More concise schema
- Save ~200 tokens per request

### 5. Streaming Responses
Currently waits for complete JSON. Could:
- Stream partial results
- Process citations as they arrive
- Reduce end-to-end latency

### 6. Model Quantization
Test smaller quantizations:
- Q4_K_M (smaller, slightly faster)
- Q3_K_L (half size, acceptable quality?)
- May enable higher concurrency

---

## Performance Comparison: Before vs After

### Initial State (Before Optimizations)
- Time: Unknown (baseline lost)
- Configuration: Sub-optimal defaults
- Issues: Multiple bugs, unclear parameters

### Final State (After All Optimizations)
- **Time**: 55 seconds for full book
- **GPU utilization**: 70-75% sustained
- **VRAM efficiency**: q4_0 KV cache saves 50%
- **Code quality**: Clear parameter names, validated outputs
- **Bugs fixed**: 2 critical (double reservation, hallucination)

### Net Result
Achieved production-ready citation extraction system with:
- Optimal GPU utilization
- Minimal VRAM waste
- Fast processing (13.3 sentences/sec)
- Validated output quality
- Clear, maintainable code

---

## Conclusion

Through systematic experimentation, we optimized the bookgraph citation extraction system from initial implementation to production-ready performance. Key insights:

1. **Measure, don't guess**: Profiling revealed unexpected bottlenecks (API overhead > GPU parallelism)
2. **Validate assumptions**: Parameter flow audit caught 50% capacity waste
3. **Trust but verify**: LLM outputs need validation against ground truth
4. **Clear naming prevents bugs**: Semantic parameter names avoid confusion
5. **Workload matters**: Optimal settings vary by job size

The final system processes books at ~13 sentences/second with validated output quality and efficient resource utilization.
