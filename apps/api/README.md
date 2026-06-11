# spin2note-api

FastAPI backend for Spin&Gold analytics. Heavy hand-history parsing is delegated to the
Rust `hh_parser` extension (see `../../crates/hh-parser`). All business logic lives here;
the Next.js frontend is presentation-only.

See the root `CLAUDE.md` for build/run/test commands.
