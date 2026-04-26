//! Sprint 29 — zk-proof-worker contract test.
//!
//! Compiles only — no live HTTP. Asserts that the canonical route surface
//! still exists in `src/main.rs`. The integration smoke (real `cargo run`
//! + curl `/health`) is wired by the docker-compose-based CI smoke step.

use std::fs;

const REQUIRED_ROUTES: &[&str] = &[
    "/health",
    "/proofs/verify",
    "/proofs/:proof_id/status",
];

#[test]
fn route_surface_is_declared() {
    let main = fs::read_to_string("src/main.rs")
        .expect("expected to find src/main.rs relative to crate root");
    for route in REQUIRED_ROUTES {
        assert!(
            main.contains(&format!("\"{}\"", route)),
            "zk-proof-worker main.rs missing required route {}",
            route
        );
    }
}
