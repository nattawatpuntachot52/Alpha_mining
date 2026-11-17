use alpha_ovca::{
    append_event_to_stream, evaluate_followup, init_intake_event, revalidate_mandate,
    verify_conditioned_stream, AdmissionPolicy, AuthorizationMandate, ConditioningBrief,
    FollowUpEvent,
};
use ovca_types::WorkflowEvent;
use std::env;
use std::fs;
use std::path::Path;
use std::process;

fn print_usage() {
    eprintln!(
        "alpha-ovca — Conditioner + OVCA v1.0 control-plane CLI

USAGE:
  alpha-ovca validate-brief <brief.json>
  alpha-ovca init-workflow --brief <brief.json> --workflow-id <id> --event-id <id> --occurred-at <utc-z> --out <stream.json>
  alpha-ovca verify-stream <stream.json> [--brief <brief.json>]
  alpha-ovca append-event --stream <stream.json> --event <event.json> [--brief <brief.json>]
  alpha-ovca status <stream.json> [--brief <brief.json>]
  alpha-ovca policy-version <policy.json>
  alpha-ovca validate-mandate <mandate.json> [--brief <brief.json>] [--policy <policy.json>]
  alpha-ovca revalidate-mandate --mandate <mandate.json> --policy <policy.json>
  alpha-ovca check-followup --mandate <mandate.json> --followup <followup.json> --policy <policy.json>"
    );
}

fn read_json<T: serde::de::DeserializeOwned>(path: &str) -> Result<T, String> {
    let raw = fs::read_to_string(path).map_err(|e| format!("failed to read '{path}': {e}"))?;
    serde_json::from_str(&raw).map_err(|e| format!("failed to parse JSON '{path}': {e}"))
}

fn write_json_pretty<T: serde::Serialize>(path: &str, value: &T) -> Result<(), String> {
    if let Some(parent) = Path::new(path).parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("failed to create directory for '{path}': {e}"))?;
        }
    }
    let json = serde_json::to_string_pretty(value)
        .map_err(|e| format!("failed to serialize JSON: {e}"))?;
    fs::write(path, format!("{json}\n")).map_err(|e| format!("failed to write '{path}': {e}"))
}

fn flag_value(args: &[String], flag: &str) -> Result<String, String> {
    args.windows(2)
        .find(|w| w[0] == flag)
        .map(|w| w[1].clone())
        .ok_or_else(|| format!("missing required flag {flag}"))
}

fn optional_flag_value(args: &[String], flag: &str) -> Result<Option<String>, String> {
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        if arg == flag {
            let val = iter
                .next()
                .ok_or_else(|| format!("flag {flag} requires a value"))?;
            return Ok(Some(val.clone()));
        }
    }
    Ok(None)
}

fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        print_usage();
        return Err("no subcommand provided".into());
    }

    match args[1].as_str() {
        "--help" | "-h" | "help" => {
            print_usage();
            Ok(())
        }
        "validate-brief" => {
            let path = args
                .get(2)
                .ok_or_else(|| "usage: alpha-ovca validate-brief <brief.json>".to_string())?;
            let brief: ConditioningBrief = read_json(path)?;
            brief.validate().map_err(|e| e.to_string())?;
            let out = serde_json::json!({
                "valid": true,
                "brief_id": brief.brief_id,
                "domain": brief.domain,
                "target_evidence_status": brief.target_evidence_status,
                "unknowns_count": brief.unknowns.len()
            });
            println!(
                "{}",
                serde_json::to_string_pretty(&out).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        "init-workflow" => {
            let brief_path = flag_value(&args[2..], "--brief")?;
            let workflow_id = flag_value(&args[2..], "--workflow-id")?;
            let event_id = flag_value(&args[2..], "--event-id")?;
            let occurred_at = flag_value(&args[2..], "--occurred-at")?;
            let out_path = flag_value(&args[2..], "--out")?;

            let brief: ConditioningBrief = read_json(&brief_path)?;
            let intake = init_intake_event(&brief, &workflow_id, &event_id, &occurred_at)
                .map_err(|e| e.to_string())?;
            let stream = vec![intake];
            let report =
                verify_conditioned_stream(&stream, Some(&brief)).map_err(|e| e.to_string())?;
            write_json_pretty(&out_path, &stream)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        "verify-stream" | "status" => {
            let stream_path = args.get(2).ok_or_else(|| {
                format!(
                    "usage: alpha-ovca {} <stream.json> [--brief <brief.json>]",
                    args[1]
                )
            })?;
            let brief_path = optional_flag_value(&args[3..], "--brief")?;
            let stream: Vec<WorkflowEvent> = read_json(stream_path)?;
            let brief: Option<ConditioningBrief> = match brief_path {
                Some(ref p) => Some(read_json(p)?),
                None => None,
            };
            let report =
                verify_conditioned_stream(&stream, brief.as_ref()).map_err(|e| e.to_string())?;
            println!(
                "{}",
                serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        "append-event" => {
            let stream_path = flag_value(&args[2..], "--stream")?;
            let event_path = flag_value(&args[2..], "--event")?;
            let brief_path = optional_flag_value(&args[2..], "--brief")?;

            let mut stream: Vec<WorkflowEvent> = read_json(&stream_path)?;
            let new_event: WorkflowEvent = read_json(&event_path)?;
            let brief: Option<ConditioningBrief> = match brief_path {
                Some(ref p) => Some(read_json(p)?),
                None => None,
            };

            let report = append_event_to_stream(&mut stream, new_event, brief.as_ref())
                .map_err(|e| e.to_string())?;
            write_json_pretty(&stream_path, &stream)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        "policy-version" => {
            let path = args
                .get(2)
                .ok_or_else(|| "usage: alpha-ovca policy-version <policy.json>".to_string())?;
            let policy: AdmissionPolicy = read_json(path)?;
            let version = policy
                .canonical_policy_version()
                .map_err(|e| e.to_string())?;
            let enabled_rules: Vec<String> = policy
                .proactive_rules
                .iter()
                .filter(|r| r.enabled)
                .map(|r| r.rule_id.clone())
                .collect();
            let out = serde_json::json!({
                "valid": true,
                "policy_schema_version": policy.policy_schema_version,
                "accept_mode": policy.accept_mode,
                "policy_version": version,
                "enabled_rules": enabled_rules,
            });
            println!(
                "{}",
                serde_json::to_string_pretty(&out).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        "validate-mandate" => {
            let mandate_path = args.get(2).ok_or_else(|| {
                "usage: alpha-ovca validate-mandate <mandate.json> [--brief <brief.json>] [--policy <policy.json>]"
                    .to_string()
            })?;
            let brief_path = optional_flag_value(&args[3..], "--brief")?;
            let policy_path = optional_flag_value(&args[3..], "--policy")?;

            let mandate: AuthorizationMandate = read_json(mandate_path)?;
            mandate.validate().map_err(|e| e.to_string())?;
            if let Some(ref p) = brief_path {
                let brief: ConditioningBrief = read_json(p)?;
                brief.validate().map_err(|e| e.to_string())?;
                mandate.bind_to_brief(&brief).map_err(|e| e.to_string())?;
            }
            let revalidation = match policy_path {
                Some(ref p) => {
                    let policy: AdmissionPolicy = read_json(p)?;
                    Some(revalidate_mandate(&mandate, &policy).map_err(|e| e.to_string())?)
                }
                None => None,
            };
            let out = serde_json::json!({
                "valid": true,
                "mandate_id": mandate.mandate_id,
                "strength": mandate.strength,
                "status": mandate.status,
                "policy_version": mandate.policy_version,
                "brief_bound": brief_path.is_some(),
                "revalidation": revalidation,
            });
            println!(
                "{}",
                serde_json::to_string_pretty(&out).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        "revalidate-mandate" => {
            let mandate_path = flag_value(&args[2..], "--mandate")?;
            let policy_path = flag_value(&args[2..], "--policy")?;
            let mandate: AuthorizationMandate = read_json(&mandate_path)?;
            let policy: AdmissionPolicy = read_json(&policy_path)?;
            let report = revalidate_mandate(&mandate, &policy).map_err(|e| e.to_string())?;
            println!(
                "{}",
                serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        "check-followup" => {
            let mandate_path = flag_value(&args[2..], "--mandate")?;
            let followup_path = flag_value(&args[2..], "--followup")?;
            let policy_path = flag_value(&args[2..], "--policy")?;
            let mandate: AuthorizationMandate = read_json(&mandate_path)?;
            let followup: FollowUpEvent = read_json(&followup_path)?;
            let policy: AdmissionPolicy = read_json(&policy_path)?;
            let decision =
                evaluate_followup(&mandate, &followup, &policy).map_err(|e| e.to_string())?;
            println!(
                "{}",
                serde_json::to_string_pretty(&decision).map_err(|e| e.to_string())?
            );
            Ok(())
        }
        other => {
            print_usage();
            Err(format!("unknown subcommand '{other}'"))
        }
    }
}

fn main() {
    if let Err(err) = run() {
        eprintln!("error: {err}");
        process::exit(1);
    }
}
