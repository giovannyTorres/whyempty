# whyempty: measured benchmark results

Generated 2026-10-22T05:56:40.061561+00:00. CPython 3.13.5 on Windows-11-10.0.26200-SP0.

Exact versions: `whyempty==0.2.1`.

5 rotating timed rounds after two warmups; 2 separate allocation passes. Data construction, assertions and printing are excluded from timings.

| Input size | Baseline ms | Package ms | Package / baseline | Baseline peak KiB | Package peak KiB |
|---:|---:|---:|---:|---:|---:|
| 1,000 trace | 0.120 | 0.240 | 2.01x | 7.3 | 59.9 |
| 1,000 audit | 0.260 | 0.671 | 2.58x | 1.0 | 19.9 |
| 10,000 trace | 1.156 | 2.225 | 1.93x | 73.2 | 662.4 |
| 10,000 audit | 2.622 | 6.692 | 2.55x | 7.0 | 176.6 |
| 50,000 trace | 5.809 | 13.164 | 2.27x | 382.9 | 3369.0 |
| 50,000 audit | 12.809 | 33.630 | 2.63x | 32.5 | 890.4 |

Ratio = package median / baseline median. Values above 1 mean higher latency. Peaks are traced Python allocations and exclude some native memory. Accuracy checks passed before every workload was timed.

The compared values/counts match. The package also produces validation, lineage or diagnostic metadata described in [the comparison](../docs/comparison.md); those extra outputs are not fully implemented by the baseline.

## Ease of use: inspectable code-size proxy

| Function | Physical lines (including signature) | AST statements |
|---|---:|---:|
| baseline | 4 | 3 |
| library | 8 | 1 |

These counts describe one checked example. They do not measure learning time, readability, debugging success or developer productivity. Both recipes remain available for review.

## Interpretation and limits

These are deterministic synthetic examples measured on one host. They support the stated input sizes and operations. They do not establish universal speed, statistical accuracy, behavior on every dtype, or parity with R packages. No R runtime was benchmarked. Larger keys, wider tables, more failures and expensive predicates can change costs substantially.

[Raw samples, checked outcomes, environment and source hashes](latest.json) · [Reproduction and workload definitions](README.md)
