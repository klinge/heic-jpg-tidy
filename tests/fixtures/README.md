# Test fixtures

All files in this directory are synthetic or intentionally created test files.

They must not contain private photographs, GPS coordinates, personal data,
or camera serial-number metadata.

All images under "generated" are fully synthetic and created with tools/generate_fixtures.py

Fixture contracts:

- matching_pair:
  Expected to produce one MOVE_CANDIDATE without image hash verification.

- ambiguous_group:
  Expected to produce one ambiguous file group and no evaluated pair.

- corrupt_file:
  Expected to produce REVIEW with IMAGE_READ_ERROR.