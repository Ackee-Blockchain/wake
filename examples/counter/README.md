Install `@openzeppelin`:
```bash
npm install
```

Run
```bash
wake init pytypes
```
to generate pytypes or
```bash
wake init pytypes -w
```
to generate pytypes and keep watching for filesystem changes and re-generate pytypes when needed.

Use
```bash
wake test -d tests/test_*.py
```
to run tests using a single process.

To run tests in parallel (makes sense only for fuzz tests), use
```bash
wake fuzz tests/test_*.py
```