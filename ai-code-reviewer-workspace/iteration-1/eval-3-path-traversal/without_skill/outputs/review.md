# Code Review: worker/processor.go

## Summary

This PR introduces a `FileProcessor` background worker for processing uploaded files. While the logic is simple, there are several **critical security vulnerabilities and bugs** that must be addressed before merging.

---

## Critical Issues

### 1. Path Traversal Vulnerability (Security - Critical)

**Location:** `ProcessFile`, line building `filePath`

```go
filePath := filepath.Join(p.UploadDir, filename)
```

The `filename` parameter is passed directly from the caller without any sanitization. An attacker could supply a value like `../../etc/passwd` or `../secrets.env`, and `filepath.Join` will happily resolve it outside of `UploadDir`. This allows arbitrary file reads from the server filesystem.

**Fix:** Validate that the resolved path stays within `UploadDir` after joining:

```go
filePath := filepath.Join(p.UploadDir, filepath.Base(filename))
// or verify the resolved path has the expected prefix:
abs, err := filepath.Abs(filePath)
if err != nil || !strings.HasPrefix(abs, filepath.Clean(p.UploadDir)+string(os.PathSeparator)) {
    return fmt.Errorf("invalid filename: path traversal detected")
}
```

---

### 2. Shell Injection Risk via External Command (Security - Critical)

**Location:** `exec.Command("convert", ...)`

```go
cmd := exec.Command("convert", "-", p.OutputDir+"/"+filename+".out")
```

The output path is constructed by concatenating user-controlled `filename` directly into the argument. While `exec.Command` avoids a shell (unlike `exec.Command("sh", "-c", ...)`), the filename still controls the output path argument. Combined with the missing path traversal check above, this could write output files to arbitrary locations on disk.

Additionally, `convert` is invoked by name with no absolute path, relying entirely on `$PATH`. If an attacker or misconfigured environment has a rogue `convert` binary earlier in `$PATH`, it will be executed instead of the intended tool (e.g., ImageMagick's `convert`).

**Fix:** Use an absolute path for the binary (e.g., `/usr/bin/convert`) and apply the same path sanitization to the output path.

---

### 3. Missing Import: `bytes` Package

**Location:** Top of file / `cmd.Stdin` assignment

```go
cmd.Stdin = bytes.NewReader(content)
```

The `bytes` package is not listed in the import block. This code will not compile as-is.

**Fix:** Add `"bytes"` to the import block.

---

## Significant Bugs

### 4. Errors from the `convert` Command Are Silently Swallowed

```go
out, err := cmd.Output()
if err != nil {
    fmt.Println("conversion failed:", err)
}
```

- The error is printed but not returned, so the function continues as if the conversion succeeded.
- The variable `out` is assigned but never used — this is a compile error in Go (`declared and not used`).

**Fix:** Return the error on failure, and either use `out` or switch to `cmd.Run()`:

```go
if err := cmd.Run(); err != nil {
    return fmt.Errorf("conversion failed: %w", err)
}
```

---

### 5. Silently Ignored Errors Throughout

Multiple errors are discarded with `_`:

```go
files, _ := filepath.Glob(p.UploadDir + "/*")
info, _ := os.Stat(f)
os.Remove(f)
```

- If `filepath.Glob` fails, `files` is nil and the loop silently does nothing.
- If `os.Stat` fails, `info` is nil and the subsequent `info.Size()` call will **panic** with a nil pointer dereference.
- The `os.Remove` error is discarded, so failed deletions go unnoticed.

**Fix:** Handle all errors explicitly:

```go
files, err := filepath.Glob(p.UploadDir + "/*")
if err != nil {
    return fmt.Errorf("glob failed: %w", err)
}
for _, f := range files {
    info, err := os.Stat(f)
    if err != nil {
        // log and continue, or return
        continue
    }
    if info.Size() > 100*1024*1024 {
        if err := os.Remove(f); err != nil {
            // log the error
        }
    }
}
```

---

## Minor Issues

### 6. `ioutil.ReadFile` Is Deprecated

```go
content, err := ioutil.ReadFile(filePath)
```

`io/ioutil` was deprecated in Go 1.16. Use `os.ReadFile` instead:

```go
content, err := os.ReadFile(filePath)
```

This also removes the need to import `"io/ioutil"`.

---

### 7. Unexpected Side Effect: ProcessFile Deletes Unrelated Files

The `ProcessFile` function is responsible for processing a single named file, but it also scans the entire upload directory and deletes any file over 100MB. This is an unexpected side effect with no clear ownership or documentation. It should be extracted into a separate method (e.g., `CleanupLargeFiles`) and called explicitly by the worker orchestrator.

---

### 8. Output Path Construction Is Fragile

```go
p.OutputDir+"/"+filename+".out"
```

Use `filepath.Join` for portability and correctness:

```go
filepath.Join(p.OutputDir, filename+".out")
```

---

## Summary Table

| # | Severity | Issue |
|---|----------|-------|
| 1 | Critical | Path traversal via unsanitized `filename` |
| 2 | Critical | Arbitrary write path + untrusted `$PATH` for `convert` |
| 3 | Critical | Missing `bytes` import — does not compile |
| 4 | High | `convert` errors swallowed; `out` variable unused (compile error) |
| 5 | High | Nil pointer panic from ignored `os.Stat` error |
| 6 | Low | Deprecated `ioutil.ReadFile` |
| 7 | Medium | Unexpected side effect (bulk deletion) inside `ProcessFile` |
| 8 | Low | Fragile string concatenation for path construction |

---

## Verdict

**Do not merge.** This PR has two compile errors (missing `bytes` import, unused `out` variable) that mean it cannot even build, plus two critical security vulnerabilities (path traversal, arbitrary output path). All critical and high severity issues must be resolved first.
