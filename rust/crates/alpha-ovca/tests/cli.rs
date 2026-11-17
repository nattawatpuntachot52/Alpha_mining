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

#[test]
fn cli_policy_version_and_mandate_followup_commands() {
    let bin = env!("CARGO_BIN_EXE_alpha-ovca");
    let root = repo_root();
    let policy_path = root.join("config/governance/admission_policy.json");

    let pv_out = Command::new(bin)
        .arg("policy-version")
        .arg(&policy_path)
        .output()
        .expect("policy-version must run");
    assert!(
        pv_out.status.success(),
        "policy-version failed: {}",
        String::from_utf8_lossy(&pv_out.stderr)
    );
    let pv_json: serde_json::Value = serde_json::from_slice(&pv_out.stdout).unwrap();
    assert_eq!(pv_json["valid"], true);
    assert_eq!(pv_json["accept_mode"], "observe");
    let policy_ver = pv_json["policy_version"].as_str().unwrap().to_string();
    assert!(policy_ver.starts_with("sha256:"));

    let dir = temp_dir("mandate_cli");
    let mandate_path = dir.join("mandate.json");
    let followup_path = dir.join("followup.json");

    let mandate_json = serde_json::json!({
        "contract_version": "1.0",
        "mandate_id": "mnd-cli-1",
        "authority_id": "auth-synth-microstructure-001",
        "origin_thread_id": "pr:1",
        "source_kind": "github_pr",
        "receiving_scope": "github_pr",
        "requester_actor": "nattawatpuntachot52",
        "requester_is_bot": false,
        "strength": "explicit",
        "policy_version": policy_ver,
        "matched_rules": [],
        "writable_scope": ["workflows/examples"],
        "status": "active"
    });
    fs::write(
        &mandate_path,
        serde_json::to_string_pretty(&mandate_json).unwrap(),
    )
    .unwrap();

    let brief = root.join("workflows/examples/quant_alpha_brief.example.json");
    let vm_out = Command::new(bin)
        .args([
            "validate-mandate",
            mandate_path.to_str().unwrap(),
            "--brief",
            brief.to_str().unwrap(),
            "--policy",
            policy_path.to_str().unwrap(),
        ])
        .output()
        .expect("validate-mandate must run");
    assert!(
        vm_out.status.success(),
        "validate-mandate failed: {}",
        String::from_utf8_lossy(&vm_out.stderr)
    );
    let vm_json: serde_json::Value = serde_json::from_slice(&vm_out.stdout).unwrap();
    assert_eq!(vm_json["brief_bound"], true);
    assert_eq!(vm_json["revalidation"]["valid_to_resume"], true);

    let followup_json = serde_json::json!({
        "trigger_id": "trg-cli-1",
        "thread_id": "pr:1",
        "subscription_mode": "owned_work",
        "actor": "nattawatpuntachot52",
        "actor_is_bot": false,
        "is_ci": false,
        "requested_scope_paths": ["rust/crates/alpha-ovca/src/lib.rs"],
        "requests_stop": false,
        "requests_scope_expansion": false
    });
    fs::write(
        &followup_path,
        serde_json::to_string_pretty(&followup_json).unwrap(),
    )
    .unwrap();

    let cf_out = Command::new(bin)
        .args([
            "check-followup",
            "--mandate",
            mandate_path.to_str().unwrap(),
            "--followup",
            followup_path.to_str().unwrap(),
            "--policy",
            policy_path.to_str().unwrap(),
        ])
        .output()
        .expect("check-followup must run");
    assert!(
        cf_out.status.success(),
        "check-followup failed: {}",
        String::from_utf8_lossy(&cf_out.stderr)
    );
    let cf_json: serde_json::Value = serde_json::from_slice(&cf_out.stdout).unwrap();
    assert_eq!(cf_json["action"], "handback_required");
    assert_eq!(cf_json["grant_authority"], false);

    // revalidate-mandate succeeds on active explicit owner mandate under default observe policy
    let rev_out = Command::new(bin)
        .args([
            "revalidate-mandate",
            "--mandate",
            mandate_path.to_str().unwrap(),
            "--policy",
            policy_path.to_str().unwrap(),
        ])
        .output()
        .expect("revalidate-mandate must run");
    assert!(
        rev_out.status.success(),
        "revalidate-mandate failed: {}",
        String::from_utf8_lossy(&rev_out.stderr)
    );
    let rev_json: serde_json::Value = serde_json::from_slice(&rev_out.stdout).unwrap();
    assert_eq!(rev_json["valid_to_resume"], true);
    assert_eq!(rev_json["resulting_status"], "active");
    assert_eq!(rev_json["policy_changed"], false);

    // Inferred mandate under observe policy returns revoked from revalidate-mandate CLI
    let inferred_mandate_path = dir.join("inferred_mandate.json");
    let inferred_mandate_json = serde_json::json!({
        "contract_version": "1.0",
        "mandate_id": "mnd-cli-inf",
        "authority_id": "auth-synth-microstructure-001",
        "origin_thread_id": "branch:main",
        "source_kind": "github_default_branch_ci",
        "receiving_scope": "github_default_branch_ci",
        "requester_actor": "github-ci",
        "requester_is_bot": false,
        "strength": "inferred",
        "policy_version": policy_ver,
        "matched_rules": ["ci-default-branch-failure"],
        "writable_scope": ["rust/"],
        "status": "active"
    });
    fs::write(
        &inferred_mandate_path,
        serde_json::to_string_pretty(&inferred_mandate_json).unwrap(),
    )
    .unwrap();
    let rev_inf_out = Command::new(bin)
        .args([
            "revalidate-mandate",
            "--mandate",
            inferred_mandate_path.to_str().unwrap(),
            "--policy",
            policy_path.to_str().unwrap(),
        ])
        .output()
        .expect("revalidate-mandate inferred must run");
    assert!(rev_inf_out.status.success());
    let rev_inf_json: serde_json::Value = serde_json::from_slice(&rev_inf_out.stdout).unwrap();
    assert_eq!(rev_inf_json["valid_to_resume"], false);
    assert_eq!(rev_inf_json["resulting_status"], "revoked");

    let _ = fs::remove_dir_all(&dir);
}
