# heic-jpg-tidy

![Tests](https://github.com/klinge/heic-jpg-tidy/actions/workflows/tests.yml/badge.svg)
[![codecov](https://codecov.io/gh/klinge/heic-jpg-tidy/graph/badge.svg)](https://codecov.io/gh/klinge/heic-jpg-tidy)

Many photo libraries — especially those from iPhones — contain both a HEIC and
a JPG version of the same photo. The JPG is typically a legacy export or a
sharing copy and serves no purpose once the HEIC is safely stored. Over time
these pairs accumulate and clutter the library.

heic-jpg-tidy scans a photo archive for HEIC/JPG filename pairs, evaluates
whether the JPG is a redundant copy of the HEIC, and optionally moves confirmed
candidates to a quarantine directory for review before permanent deletion.

The tool is intentionally conservative. Files are never deleted automatically.
Every operation is dry-run by default and requires explicit confirmation before
anything is moved.

---

## Requirements

- Python 3.12 or later
- [Pillow](https://python-pillow.org) for image reading and EXIF metadata
- [pillow-heif](https://github.com/bigcat88/pillow_heif) for HEIC/HEIF support

Optional, for perceptual image hash verification:

- [ImageHash](https://github.com/JohannesBuchner/imagehash)

---

## Installation

```bash
git clone https://github.com/klinge/heic-jpg-tidy.git
cd heic-jpg-tidy
pip install .
```

To include the optional image hash dependency:

```bash
pip install ".[hash]"
```

Using a virtual environment is recommended:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install .
```

---

## Usage

heic-jpg-tidy uses a single `scan` command.

### Dry run (default)

Always start with a dry run. No files are moved.

```bash
heic-jpg-tidy scan \
  --source /path/to/photo/archive \
  --quarantine /path/to/quarantine \
  --report-dir /path/to/reports
```

This scans the archive, evaluates all HEIC/JPG pairs, and writes a CSV
evaluation report to `--report-dir`. Nothing is moved.

### Apply mode

Once you have reviewed the evaluation report and are satisfied with the
results, run with `--apply --confirm` to move confirmed candidates to
quarantine:

```bash
heic-jpg-tidy scan \
  --source /path/to/photo/archive \
  --quarantine /path/to/quarantine \
  --report-dir /path/to/reports \
  --apply --confirm
```

Both `--apply` and `--confirm` are required to perform real operations. This
double flag requirement is intentional to prevent accidental execution.

The quarantine directory must be completely separate from the source directory.
The relative directory structure of the source archive is preserved inside the
quarantine directory.

---

## Options

| Option | Default | Description |
|---|---|---|
| `--source` | required | Root directory of the photo archive to scan. |
| `--quarantine` | required | Directory where confirmed JPG candidates are moved. |
| `--report-dir` | required | Directory where CSV reports and action logs are written. |
| `--datetime-tolerance-seconds` | `5.0` | Maximum allowed difference in `DateTimeOriginal` between the HEIC and JPG, in seconds. |
| `--verify-image-hash` | off | Enable perceptual hash verification for pairs that pass all metadata checks. Requires the `hash` optional dependency. |
| `--max-hash-distance` | `4` | Maximum allowed perceptual hash distance when `--verify-image-hash` is enabled. |
| `--apply` | off | Move confirmed candidates to quarantine. Requires `--confirm`. |
| `--confirm` | off | Confirms that `--apply` should perform real operations. |

---

## How pairs are evaluated

A HEIC and a JPG are considered a pair only when they are located in the same
directory and share the same base filename (case-insensitive), for example
`IMG_1234.HEIC` and `IMG_1234.JPG`.

A JPG is only marked as a `MOVE_CANDIDATE` when all of the following conditions
are satisfied:

1. Both files can be read without errors.
2. `DateTimeOriginal` is present in both files and the difference is within
   `--datetime-tolerance-seconds`.
3. Camera `Make` and `Model` metadata do not conflict (missing values are
   allowed, conflicting values are not).
4. Image dimensions match exactly after applying EXIF orientation.
5. If `--verify-image-hash` is enabled, the perceptual hash distance is within
   `--max-hash-distance`.

Any pair that does not satisfy all conditions receives a `REVIEW` decision and
is never moved automatically.

Groups where the same filename stem maps to more than one HEIC or more than one
JPG are treated as ambiguous and always receive a `REVIEW` decision.

---

## Output files

Each run writes a timestamped CSV evaluation report to `--report-dir`:

```
evaluation_20260115_123000.csv
```

When `--apply --confirm` is used, a second CSV action log is written:

```
quarantine_actions_20260115_123000.csv
```

The evaluation report contains one row per evaluated pair or ambiguous group,
with columns for the decision, reason codes, metadata values, and comparison
results.

The action log contains one row per quarantine operation, with columns for the
status (`MOVED`, `SKIPPED`, or `ERROR`), source and quarantine paths, and
SHA-256 checksums for both the source and the quarantine copy.

---

## Quarantine safety

When a file is moved to quarantine the following steps are performed in order:

1. The file is copied to a temporary path in the quarantine directory.
2. File size of the source and the copy are compared.
3. SHA-256 checksums of the source and the copy are compared.
4. The temporary file is atomically renamed to its final destination.
5. The source file is removed.

The source file is only removed after the copy has been fully verified. If any
step fails the operation is recorded as `ERROR`, the temporary file is cleaned
up, and the source file is left untouched.

---

## Architecture

The project is structured as a pipeline of independent layers. Each layer
depends only on the layers below it.

```
cli.py          Command-line interface. Parses arguments, orchestrates the
                pipeline, and prints output.

workflow.py     Orchestration. Iterates file groups, reads metadata, calls
                rules, and optionally calculates image hashes. Uses dependency
                injection for the metadata reader and hash calculator to keep
                the layer testable without real image files.

rules.py        Pure evaluation logic. Takes a CandidatePair and a RuleConfig
                and returns an EvaluationResult. No I/O.

quarantine.py   Safe file move operations. Copy, verify, rename, delete with
                SHA-256 integrity checking.

reporter.py     CSV report writing for evaluation results and quarantine action
                logs.

scanner.py      Filesystem traversal. Finds HEIC/JPG filename pairs and groups
                them by stem and directory.

metadata.py     Image metadata reading via Pillow. Extracts EXIF fields and
                applies orientation to reported dimensions.

image_hash.py   Perceptual hash calculation via the optional ImageHash library.

models.py       Shared data models. Frozen dataclasses and enums only, no logic.
```

### Key design decisions

- **Dry-run by default.** Files are never moved unless both `--apply` and
  `--confirm` are provided.
- **Conservative evaluation.** Any uncertainty results in `REVIEW`, never
  `MOVE_CANDIDATE`.
- **No deletions.** The tool moves files to quarantine. Permanent deletion is
  left to the user after manual review.
- **Dependency injection in the workflow.** The metadata reader and hash
  calculator are injected, making the workflow layer fully testable without
  touching the filesystem or requiring real image files.
- **Integrity verification.** Every quarantine operation is verified with
  SHA-256 before the source file is removed.
