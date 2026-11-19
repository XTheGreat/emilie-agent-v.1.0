# Versioning guide (SemVer)

- **MAJOR** (X.0.0): incompatible change to the public interface - removed/renamed command, option, function, config key, file format, or changed default behavior callers rely on.
- **MINOR** (0.X.0): backward-compatible new capability.
- **PATCH** (0.0.X): backward-compatible bug fix, internal change, docs.
- **0.y.z**: initial development; the project may treat minor as breaking. Say which policy applies.
- **Pre-releases**: `1.2.0-rc.1`, `-beta.2`; they sort before `1.2.0`. Python (PEP 440) spells them `1.2.0rc1`.
- **CalVer** (2026.11.1) is fine if the project already uses it; do not mix schemes.
- Deprecation: announce in a minor, remove in the next major.
- Never reuse or move a published version; publish a new patch instead.
- Signals of a breaking change: `!` in a commit type, `BREAKING CHANGE:` footer, deleted public symbols, changed signatures, stricter validation, dropped platform/runtime support.
