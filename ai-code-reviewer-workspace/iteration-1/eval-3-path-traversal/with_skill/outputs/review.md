# Code Review — worker/processor.go

## Inline Findings

---

### File: worker/processor.go  Line: 18-19
**[SECURITY][error] Path traversal vulnerability — attacker-controlled filename escapes UploadDir**

`filename` comes directly from the caller (ultimately from user input) and is passed to `filepath.Join` without any sanitization. An attacker can supply a filename like `../../etc/passwd` or `../config/secrets.yaml`, and `filepath.Join` will happily resolve the path outside `p.UploadDir`. The same unsanitized value is later used to construct the output path (`p.OutputDir+"/"+filename+".out"`), so the vulnerability is present in both the read and write paths.

Fix: After joining, verify the resolved path is still rooted under the expected directory:

```go
filePath := filepath.Join(p.UploadDir, filepath.Clean("/"+filename))
absUpload, _ := filepath.Abs(p.UploadDir)
absFile, _ := filepath.Abs(filePath)
if !strings.HasPrefix(absFile, absUpload+string(os.PathSeparator)) {
    return fmt.Errorf("invalid filename: %q escapes upload directory", filename)
}
```

Apply the same guard before constructing the output path.

---

### File: worker/processor.go  Line: 23-27
**[SECURITY][error] Command injection via unsanitized filename passed to exec.Command**

The `filename` value (user-supplied) is concatenated directly into the output path that becomes an argument to the external `convert` binary:

```go
cmd := exec.Command("convert", "-", p.OutputDir+"/"+filename+".out")
```

If the shell ever interprets this argument (e.g., a downstream wrapper, or if `convert` itself spawns a shell), a filename containing shell metacharacters (`;`, `|`, `$(...)`, etc.) becomes a command injection vector. Even without shell involvement, the filename controls which output path `convert` writes to, which is an arbitrary file write if path traversal isn't blocked (see finding above).

Fix: Sanitize `filename` to only allow alphanumerics, dots, underscores, and hyphens before it is used in any path or command argument. Use `filepath.Base` to strip any directory components, then validate against an allowlist regex.

---

### File: worker/processor.go  Line: 23
**[SECURITY][error] `convert` resolved from PATH — tool hijacking risk**

`exec.Command("convert", ...)` resolves the binary using the process's `PATH`. If `PATH` is ever modified (e.g., in a containerized or CI environment where `PATH` is attacker-influenced, or via a compromised dependency that prepends a directory), an attacker can substitute a malicious `convert` binary.

Fix: Use an absolute path to the binary, configured via a struct field or build-time constant:

```go
type FileProcessor struct {
    UploadDir      string
    OutputDir      string
    ConverterBinary string // e.g. "/usr/bin/convert"
}
```

---

### File: worker/processor.go  Line: 25-28
**[BUG][error] `bytes` package not imported — code will not compile**

`bytes.NewReader(content)` is used on line 25 but `"bytes"` is not in the import block. This is a compilation error; the PR cannot be merged as-is.

Fix: Add `"bytes"` to the import block.

---

### File: worker/processor.go  Line: 26-28
**[BUG][error] Conversion error is swallowed; function continues and returns nil**

```go
out, err := cmd.Output()
if err != nil {
    fmt.Println("conversion failed:", err)
}
```

When `convert` fails, the error is only printed — execution continues, the failed output file is not cleaned up, and `ProcessFile` returns `nil` (success). The caller has no way to know the conversion failed.

Additionally, `out` is assigned but never used, which is also a compile error in Go.

Fix:

```go
if err := cmd.Run(); err != nil {
    return fmt.Errorf("conversion failed for %q: %w", filename, err)
}
```

(Switch to `cmd.Run()` since the output isn't needed, or use `cmd.Output()` and discard it explicitly with `_` if you need the return value for another reason.)

---

### File: worker/processor.go  Line: 31-36
**[BUG][error] Glob errors silently ignored; nil `info` causes panic**

```go
files, _ := filepath.Glob(p.UploadDir + "/*")
for _, f := range files {
    info, _ := os.Stat(f)
    if info.Size() > 100*1024*1024 {
```

`filepath.Glob` errors are discarded. More dangerously, if `os.Stat` fails (file deleted between the glob and the stat, permission denied, etc.), `info` is `nil` and `info.Size()` panics with a nil pointer dereference, crashing the worker process.

Fix:

```go
files, err := filepath.Glob(filepath.Join(p.UploadDir, "*"))
if err != nil {
    return fmt.Errorf("glob failed: %w", err)
}
for _, f := range files {
    info, err := os.Stat(f)
    if err != nil {
        continue // file may have been removed concurrently
    }
    if info.Size() > 100*1024*1024 {
        if err := os.Remove(f); err != nil {
            // log or return; don't silently ignore
        }
    }
}
```

---

### File: worker/processor.go  Line: 35
**[BUG][error] `os.Remove` errors silently ignored**

Failed deletions are not reported. If the worker is supposed to enforce a size cap, silently failing to delete oversized files is a logic error — disk space will fill up without any alert.

Fix: At minimum log the error; ideally return or accumulate it.

---

### File: worker/processor.go  Line: 31-36
**[BUG][warning] `ProcessFile` deletes files it was not asked to process**

The function accepts a single `filename` to process, but the cleanup loop at the end scans and potentially deletes *all* files in `UploadDir` that exceed 100 MB. This means processing any one file can silently remove other files that are still being uploaded or waiting to be processed by concurrent workers. This is a concurrency hazard and a data loss bug.

Fix: Separate concerns — move the cleanup into a dedicated `CleanupOversizedFiles` method called by the scheduler, not from within `ProcessFile`.

---

### File: worker/processor.go  Line: 7
**[CODE QUALITY][info] `ioutil.ReadFile` is deprecated**

`io/ioutil` was deprecated in Go 1.16. Use `os.ReadFile` instead.

Fix:

```go
content, err := os.ReadFile(filePath)
```

Remove the `io/ioutil` import.

---

### File: worker/processor.go  Line: 22
**[PERFORMANCE][warning] Entire file read into memory before streaming to `convert`**

`ioutil.ReadFile` reads the entire file into a `[]byte`, then `bytes.NewReader` wraps it so it can be piped to `convert`. For large files this doubles peak memory usage unnecessarily.

Fix: Open the file and use it directly as stdin:

```go
f, err := os.Open(filePath)
if err != nil {
    return err
}
defer f.Close()
cmd.Stdin = f
```

---

### File: worker/processor.go  Line: 22
**[PERFORMANCE][warning] Output path uses string concatenation instead of `filepath.Join`**

```go
p.OutputDir+"/"+filename+".out"
```

This is not portable (hardcoded `/` separator), inconsistent with the use of `filepath.Join` for the input path, and prone to double-slash issues if `OutputDir` has a trailing slash.

Fix:

```go
filepath.Join(p.OutputDir, filename+".out")
```

---

## Code Review Summary

**Overall: REQUEST CHANGES**

| Category        | Errors | Warnings | Info |
|-----------------|--------|----------|------|
| Bugs            | 4      | 1        | 0    |
| Security        | 3      | 0        | 0    |
| Performance     | 0      | 2        | 0    |
| Code Quality    | 0      | 0        | 1    |
| Test Coverage   | 0      | 0        | 1    |
| **Total**       | **7**  | **3**    | **2**|

---

### Critical Issues (must fix before merge)

1. **[SECURITY] Path traversal** — `worker/processor.go:18-19` — User-controlled `filename` can escape `UploadDir` on both read and write paths.
2. **[SECURITY] Command injection / arbitrary file write** — `worker/processor.go:23-27` — `filename` used unsanitized in the output argument to `exec.Command`.
3. **[SECURITY] `convert` resolved via PATH** — `worker/processor.go:23` — Binary path should be absolute and explicitly configured.
4. **[BUG] Won't compile: missing `bytes` import** — `worker/processor.go:25` — `bytes.NewReader` used without importing `"bytes"`.
5. **[BUG] Won't compile: `out` declared and not used** — `worker/processor.go:26` — Go will refuse to compile an unused variable.
6. **[BUG] Conversion errors swallowed** — `worker/processor.go:26-28` — Function returns `nil` on conversion failure; caller cannot detect the error.
7. **[BUG] Nil pointer panic on failed `os.Stat`** — `worker/processor.go:32-34` — If `os.Stat` returns an error, calling `.Size()` on a nil `FileInfo` panics.

### Recommended Fixes (should address)

1. **[BUG] `ProcessFile` deletes unrelated files** — `worker/processor.go:31-36` — The cleanup loop is a data-loss risk under concurrent use; extract it to a separate method.
2. **[BUG] `os.Remove` errors silently ignored** — `worker/processor.go:35` — Disk-space enforcement silently fails; at least log the error.
3. **[PERFORMANCE] Whole file buffered in memory** — `worker/processor.go:22` — Stream directly from `os.Open` to avoid doubling peak memory usage.

### Suggestions (optional improvements)

1. **[CODE QUALITY]** Replace deprecated `io/ioutil.ReadFile` with `os.ReadFile` (`worker/processor.go:7`).
2. **[TEST COVERAGE]** No tests accompany this new worker. At minimum: a happy-path test with a small fixture file, a test that verifies path traversal attempts are rejected, and a test for the conversion-failure error path.

### What's Good

- Using `filepath.Join` for the input path rather than raw string concatenation shows awareness of path handling — just needs to be applied consistently to the output path too.
- The 100 MB size cap is a reasonable safeguard for a file processing worker; the intent is right, the implementation just needs to be made safe and isolated.
