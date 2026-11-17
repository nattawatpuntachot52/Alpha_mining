use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

fn temp_dir(name: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock must be after epoch")
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("alpha_ovca_cli_{name}_{nanos}"));
    fs::create_dir_all(&dir).expect("temp dir must be created");
    dir
}

#[test]
fn cli_validates_example_brief_and_verifies_example_stream() {
    let bin = env!("CARGO_BIN_EXE_alpha-ovca");
    let root = repo_root();
    let brief = root.join("workflows/examples/quant_alpha_brief.example.json");
    let stream = root.join("workflows/examples/quant_alpha_pass_stream.json");

    let brief_out = Command::new(bin)
        .arg("validate-brief")
        .arg(&brief)
        .output()
        .expect("validate-brief must run");
    assert!(
        brief_out.status.success(),
        "validate-brief failed: {}",
        String::from_utf8_lossy(&brief_out.stderr)
    );

    let stream_out = Command::new(bin)
        .arg("verify-stream")
        .arg(&stream)
        .arg("--brief")
        .arg(&brief)
        .output()
        .expect("verify-stream must run");
    assert!(
        stream_out.status.success(),
        "verify-stream failed: {}",
        String::from_utf8_lossy(&stream_out.stderr)
    );
    let stdout = String::from_utf8_lossy(&stream_out.stdout);
    assert!(stdout.contains("\"phase\": \"completed\""));
    assert!(stdout.contains("\"outcome\": \"passed\""));
}

#[test]
fn cli_init_and_transactional_append_preserves_file_on_rejection() {
    let bin = env!("CARGO_BIN_EXE_alpha-ovca");
    let root = repo_root();
    let brief = root.join("workflows/examples/quant_alpha_brief.example.json");
    let dir = temp_dir("append");
    let stream_path = dir.join("events.json");
    let bad_event_path = dir.join("bad_dispatch.json");

    let init_out = Command::new(bin)
        .args([
            "init-workflow",
            "--brief",
            brief.to_str().unwrap(),
            "--workflow-id",
            "wf-cli-test",
            "--event-id",
            "cli-0",
            "--occurred-at",
            "2026-11-17T00:00:00Z",
            "--out",
            stream_path.to_str().unwrap(),
        ])
        .output()
        .expect("init-workflow must run");
    assert!(
        init_out.status.success(),
        "init-workflow failed: {}",
        String::from_utf8_lossy(&init_out.stderr)
    );

    let before = fs::read_to_string(&stream_path).expect("stream file must exist");

    // Wrong sequence (2 instead of 1) must fail and leave stream file untouched
    let bad_event = r#"{
  "contract_version": "1.0",
  "workflow_id": "wf-cli-test",
  "event_id": "cli-bad",
  "sequence": 2,
  "previous_event_id": "cli-0",
  "occurred_at": "2026-11-17T00:01:00Z",
  "type": "coordinator_dispatched",
  "data": {
    "invocation": {
      "contract_version": "1.0",
      "invocation_id": "inv-bad",
      "requested_by": "coordinator",
      "role": "engineer",
      "objective": "Bad sequence test",
      "authority_ref": "auth-synth-microstructure-001",
      "input_refs": ["brief-synth-microstructure-001"],
      "attempt": 1,
      "requested_at": "2026-11-17T00:01:00Z"
    }
  }
}"#;
    fs::write(&bad_event_path, bad_event).unwrap();

    let bad_out = Command::new(bin)
        .args([
            "append-event",
            "--stream",
            stream_path.to_str().unwrap(),
            "--event",
            bad_event_path.to_str().unwrap(),
            "--brief",
            brief.to_str().unwrap(),
        ])
        .output()
        .expect("append-event must execute");
    assert!(!bad_out.status.success());

    let after = fs::read_to_string(&stream_path).expect("stream file must remain");
    assert_eq!(before, after);

    let _ = fs::remove_dir_all(&dir);
}
