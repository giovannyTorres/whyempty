# whyempty 0.1.0 design

## Public contract

`trace(iterable)` eagerly consumes an iterable once into `Trace[T]`. A trace is
mutable: `keep(name, predicate)` returns the same object. `items` is a tuple of
surviving references; records are never deep-copied or modified by the library.
Input iteration failures propagate unchanged because no trace exists yet.

Each successful stage stores an immutable `Step`: one-based `index`, `name`,
`before`, `removed`, `remaining`, and `elapsed_seconds`. Derived properties are
`retention_pct` (None for zero input), `emptied`, `skipped`, and
`significant_reduction` (at least 50% removed from nonempty input).

`initial_count`, `count`, `is_empty`, `steps`, and `first_empty_step` expose
recorded state. `rejected()` returns immutable `Rejection` metadata in original
input order: zero-based `original_index`, one-based `step_index`, `filter_name`.
It does not retain rejected records. Repeated values and filter names are valid.

`explain()` formats recorded statistics without reevaluation or printing.
`to_dict()` returns counts, the first emptying step index (or None), and step
statistics. It never serializes records, their representations, or predicates.
Filter names are user-supplied diagnostic labels and must be printable, nonblank
strings. Applications remain responsible for sensitive content in those labels.

## Failure and state invariants

- Each occurrence reaching a stage is evaluated exactly once, including truth
  conversion. Duplicate occurrences of the same object are separate records.
- A stage commits only after every predicate succeeds. `FilterError`, chained
  from the original `Exception`, identifies the stage and original position.
  Failed stages leave survivor references, statistics, and rejections unchanged.
  User predicate side effects cannot be rolled back. `BaseException` propagates.
- Reentering `keep` on the same trace is prohibited. The object is not thread safe.
- `before = removed + remaining`; adjacent stages connect by survivor count.
- `count + len(rejected()) = initial_count`; every original position is either a
  survivor or has exactly one first rejection.
- Only a stage with `before > 0` and `remaining == 0` causes final elimination.
  Later zero-input stages are recorded as skipped and invoke no predicates.
- No stage snapshots or predicates are retained; queries do not rerun user code.

## Storage and complexity

Store survivor references, their original positions, one integer rejection-stage
marker per original position, and step statistics. Initial positions use a range.
Stage partitioning uses temporary survivor and rejected-position buffers to
support atomic failure. Metadata markers permit original-order rejection queries
in linear time without hashing records or sorting.

For N input occurrences and K filters, construction is O(N), filtering is
O(sum of stage input counts) plus predicate work, and persistent storage is
O(N + K). `items`, `count`, and `is_empty` reads are O(1); `steps`,
`first_empty_step`, `explain`, and `to_dict` are O(K), excluding label/output size.
`rejected()` scans N markers and allocates O(R) metadata objects for R rejections.
These costs exclude memory and work inside user predicates. Infinite inputs are
unsupported because input materialization is eager.

## Related work and packaging research

Research checked on 2026-10-21; this is not a claim of novelty.

- [Coffea PackedSelection.cutflow](https://github.com/scikit-hep/coffea/blob/master/src/coffea/analysis_tools.py)
  already counts cumulative selection survivors for NumPy/Awkward arrays.
- [IceCream](https://github.com/gruns/icecream) inspects expressions and values.
- [more-itertools](https://github.com/more-itertools/more-itertools/blob/master/docs/api.rst)
  provides iterable utilities such as `partition` and `filter_except`.

The useful scope here is explicit sequential predicates on ordinary Python
iterables, positional first-rejection provenance, recorded counts and timing,
and a data-free summary, without third-party runtime dependencies.

[PyPA pyproject guidance](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
and its [packaging tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
support a `src` layout, declarative project metadata, SPDX MIT license metadata,
`python -m build`, and `twine check`. Setuptools >=77.0.3 supports modern license
metadata. The [typing distribution specification](https://typing.python.org/en/latest/spec/distributing.html)
requires `py.typed` for packages distributing inline typing information.
