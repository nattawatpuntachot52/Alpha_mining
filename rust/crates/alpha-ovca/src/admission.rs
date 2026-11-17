//! Mechanism 1 (`Context != Authority`: Mandate, Policy Version, Revalidation, Handback)
//! and Mechanism 2 (`Observe Mode`: `off | observe | auto` Admission Table & Gate Contracts).
//!
//! All contracts here operate around `ovca-reference` v1.0 without altering `ovca-types`
//! or `ovca-workflow` wire schemas.

use crate::{AlphaOvcaError, ConditioningBrief};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

/// Pure Rust FIPS 180-4 SHA-256 implementation (offline `--locked` friendly, zero extra deps).
pub fn sha256_hex(input: &[u8]) -> String {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];

    let mut state: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];

    let bit_len = (input.len() as u64) * 8;
    let mut padded = Vec::with_capacity(input.len() + 72);
    padded.extend_from_slice(input);
    padded.push(0x80);
    while (padded.len() % 64) != 56 {
        padded.push(0x00);
    }
    padded.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in padded.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (i, word) in w.iter_mut().take(16).enumerate() {
            let offset = i * 4;
            *word = u32::from_be_bytes([
                chunk[offset],
                chunk[offset + 1],
                chunk[offset + 2],
                chunk[offset + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }

        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = state;
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = h
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        state[0] = state[0].wrapping_add(a);
        state[1] = state[1].wrapping_add(b);
        state[2] = state[2].wrapping_add(c);
        state[3] = state[3].wrapping_add(d);
        state[4] = state[4].wrapping_add(e);
        state[5] = state[5].wrapping_add(f);
        state[6] = state[6].wrapping_add(g);
        state[7] = state[7].wrapping_add(h);
    }

    let mut out = String::with_capacity(64);
    for word in state {
        out.push_str(&format!("{word:08x}"));
    }
    out
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AcceptMode {
    Off,
    Observe,
    Auto,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AdmissionChoice {
    Explicit,
    Inferred,
    Ignore,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UnaddressedChoice {
    Inferred,
    Ignore,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReceivingScope {
    // Keep variants in exact alphabetical order of their snake_case JSON values
    // so BTreeMap ordering aligns identically with sorted JSON keys in Python.
    GithubComment,
    GithubDefaultBranchCi,
    GithubIssue,
    GithubPr,
    OwnerCli,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TriggerSourceKind {
    OwnerCli,
    GithubIssue,
    GithubPr,
    GithubComment,
    GithubDefaultBranchCi,
    Bot,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MandateStrength {
    Explicit,
    Inferred,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MandateStatus {
    Active,
    Ended,
    StoppedByPerson,
    Revoked,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SubscriptionMode {
    OwnedWork,
    ContextOnly,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AddressedKind {
    Mention,
    Direct,
    None,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AdmissionTableRow {
    pub receive_all: bool,
    pub listed_addressed: AdmissionChoice,
    pub listed_unaddressed: UnaddressedChoice,
    pub unlisted_addressed: AdmissionChoice,
    pub unlisted_unaddressed: UnaddressedChoice,
}

impl AdmissionTableRow {
    pub fn validate(&self, scope: ReceivingScope) -> Result<(), AlphaOvcaError> {
        if scope == ReceivingScope::GithubDefaultBranchCi {
            if self.listed_addressed != AdmissionChoice::Ignore
                || self.listed_unaddressed != UnaddressedChoice::Ignore
                || self.unlisted_addressed != AdmissionChoice::Ignore
            {
                return Err(AlphaOvcaError::PolicyValidation(
                    "github_default_branch_ci has no sender; only unlisted_unaddressed may be configured"
                        .into(),
                ));
            }
        } else if !self.receive_all
            && (self.listed_unaddressed != UnaddressedChoice::Ignore
                || self.unlisted_unaddressed != UnaddressedChoice::Ignore)
        {
            return Err(AlphaOvcaError::PolicyValidation(format!(
                "receiving scope '{scope:?}' has receive_all=false, so unaddressed cells must be 'ignore'"
            )));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProactiveRule {
    pub rule_id: String,
    pub enabled: bool,
    pub title: String,
    pub description: String,
    pub receiving_scopes: Vec<ReceivingScope>,
    pub writable_scope: Vec<String>,
    pub silent_ack: bool,
}

impl ProactiveRule {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        require_non_empty_text("proactive_rule.rule_id", &self.rule_id)?;
        require_non_empty_text("proactive_rule.title", &self.title)?;
        require_non_empty_text("proactive_rule.description", &self.description)?;
        if self.receiving_scopes.is_empty() {
            return Err(AlphaOvcaError::PolicyValidation(format!(
                "rule '{}' must declare at least one receiving_scope",
                self.rule_id
            )));
        }
        if self.writable_scope.is_empty() {
            return Err(AlphaOvcaError::PolicyValidation(format!(
                "rule '{}' must declare at least one writable_scope entry",
                self.rule_id
            )));
        }
        let mut seen_scopes = BTreeSet::new();
        for item in &self.writable_scope {
            validate_safe_scope_pattern(item)?;
            if !seen_scopes.insert(item.trim().to_string()) {
                return Err(AlphaOvcaError::PolicyValidation(format!(
                    "rule '{}' has duplicate writable_scope entry '{}'",
                    self.rule_id, item
                )));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AdmissionPolicy {
    pub policy_schema_version: String,
    pub accept_mode: AcceptMode,
    pub allowed_actors: Vec<String>,
    pub bot_allowlist: Vec<String>,
    #[serde(default)]
    pub automated_reviewers_non_bot: Vec<String>,
    pub admission_table: BTreeMap<ReceivingScope, AdmissionTableRow>,
    pub proactive_rules: Vec<ProactiveRule>,
}

impl AdmissionPolicy {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        if self.policy_schema_version != "1.0" {
            return Err(AlphaOvcaError::PolicyValidation(format!(
                "policy_schema_version must be '1.0', got '{}'",
                self.policy_schema_version
            )));
        }
        let allowed = normalize_actor_list("allowed_actors", &self.allowed_actors, true)?;
        for actor in &allowed {
            if is_bot_login(actor) {
                return Err(AlphaOvcaError::PolicyValidation(format!(
                    "bot identity '{actor}' cannot appear in allowed_actors; place bots in bot_allowlist"
                )));
            }
        }
        let bots = normalize_actor_list("bot_allowlist", &self.bot_allowlist, false)?;
        for actor in &bots {
            if allowed.contains(actor) {
                return Err(AlphaOvcaError::PolicyValidation(format!(
                    "actor '{actor}' cannot appear in both allowed_actors and bot_allowlist"
                )));
            }
        }
        let reviewers = normalize_actor_list(
            "automated_reviewers_non_bot",
            &self.automated_reviewers_non_bot,
            false,
        )?;
        for actor in &reviewers {
            if is_bot_login(actor) {
                return Err(AlphaOvcaError::PolicyValidation(format!(
                    "bot identity '{actor}' cannot appear in automated_reviewers_non_bot; place bots in bot_allowlist"
                )));
            }
            if allowed.contains(actor) {
                return Err(AlphaOvcaError::PolicyValidation(format!(
                    "actor '{actor}' cannot appear in both allowed_actors and automated_reviewers_non_bot"
                )));
            }
            if bots.contains(actor) {
                return Err(AlphaOvcaError::PolicyValidation(format!(
                    "actor '{actor}' cannot appear in both bot_allowlist and automated_reviewers_non_bot"
                )));
            }
        }

        if self.admission_table.is_empty() {
            return Err(AlphaOvcaError::PolicyValidation(
                "admission_table must not be empty".into(),
            ));
        }
        for (scope, row) in &self.admission_table {
            row.validate(*scope)?;
        }

        let mut seen_rule_ids = BTreeSet::new();
        for rule in &self.proactive_rules {
            rule.validate()?;
            let id = rule.rule_id.trim().to_string();
            if !seen_rule_ids.insert(id.clone()) {
                return Err(AlphaOvcaError::PolicyValidation(format!(
                    "duplicate proactive rule_id '{id}'"
                )));
            }
        }
        Ok(())
    }

    pub fn canonicalized(&self) -> Result<AdmissionPolicy, AlphaOvcaError> {
        self.validate()?;
        let allowed_actors: Vec<String> =
            normalize_actor_list("allowed_actors", &self.allowed_actors, true)?
                .into_iter()
                .collect();
        let bot_allowlist: Vec<String> =
            normalize_actor_list("bot_allowlist", &self.bot_allowlist, false)?
                .into_iter()
                .collect();
        let automated_reviewers_non_bot: Vec<String> = normalize_actor_list(
            "automated_reviewers_non_bot",
            &self.automated_reviewers_non_bot,
            false,
        )?
        .into_iter()
        .collect();

        let mut proactive_rules: Vec<ProactiveRule> = self
            .proactive_rules
            .iter()
            .map(|r| {
                let mut scopes: BTreeSet<ReceivingScope> =
                    r.receiving_scopes.iter().copied().collect();
                let receiving_scopes: Vec<ReceivingScope> =
                    std::mem::take(&mut scopes).into_iter().collect();
                let writable_set: BTreeSet<String> = r
                    .writable_scope
                    .iter()
                    .map(|s| normalize_scope_string(s))
                    .collect();
                ProactiveRule {
                    rule_id: r.rule_id.trim().to_string(),
                    enabled: r.enabled,
                    title: r.title.trim().to_string(),
                    description: r.description.trim().to_string(),
                    receiving_scopes,
                    writable_scope: writable_set.into_iter().collect(),
                    silent_ack: r.silent_ack,
                }
            })
            .collect();
        proactive_rules.sort_by(|a, b| a.rule_id.cmp(&b.rule_id));

        Ok(AdmissionPolicy {
            policy_schema_version: self.policy_schema_version.trim().to_string(),
            accept_mode: self.accept_mode,
            allowed_actors,
            bot_allowlist,
            automated_reviewers_non_bot,
            admission_table: self.admission_table.clone(),
            proactive_rules,
        })
    }

    /// Deterministic canonical SHA-256 policy version string (`sha256:<64 hex>`),
    /// matching Python `compute_policy_version()` byte-for-byte regardless of `preserve_order`.
    pub fn canonical_policy_version(&self) -> Result<String, AlphaOvcaError> {
        #[derive(Serialize)]
        #[serde(untagged)]
        enum CanonJson {
            Bool(bool),
            Str(String),
            Arr(Vec<CanonJson>),
            Obj(BTreeMap<&'static str, CanonJson>),
            DynObj(BTreeMap<String, CanonJson>),
        }

        fn scope_key(scope: ReceivingScope) -> String {
            match scope {
                ReceivingScope::GithubComment => "github_comment",
                ReceivingScope::GithubDefaultBranchCi => "github_default_branch_ci",
                ReceivingScope::GithubIssue => "github_issue",
                ReceivingScope::GithubPr => "github_pr",
                ReceivingScope::OwnerCli => "owner_cli",
            }
            .to_string()
        }

        fn accept_mode_str(mode: AcceptMode) -> &'static str {
            match mode {
                AcceptMode::Off => "off",
                AcceptMode::Observe => "observe",
                AcceptMode::Auto => "auto",
            }
        }

        fn admission_choice_str(choice: AdmissionChoice) -> &'static str {
            match choice {
                AdmissionChoice::Explicit => "explicit",
                AdmissionChoice::Inferred => "inferred",
                AdmissionChoice::Ignore => "ignore",
            }
        }

        fn unaddressed_choice_str(choice: UnaddressedChoice) -> &'static str {
            match choice {
                UnaddressedChoice::Inferred => "inferred",
                UnaddressedChoice::Ignore => "ignore",
            }
        }

        let canon = self.canonicalized()?;

        let mut table_map = BTreeMap::new();
        for (scope, row) in &canon.admission_table {
            let mut row_map = BTreeMap::new();
            row_map.insert(
                "listed_addressed",
                CanonJson::Str(admission_choice_str(row.listed_addressed).into()),
            );
            row_map.insert(
                "listed_unaddressed",
                CanonJson::Str(unaddressed_choice_str(row.listed_unaddressed).into()),
            );
            row_map.insert("receive_all", CanonJson::Bool(row.receive_all));
            row_map.insert(
                "unlisted_addressed",
                CanonJson::Str(admission_choice_str(row.unlisted_addressed).into()),
            );
            row_map.insert(
                "unlisted_unaddressed",
                CanonJson::Str(unaddressed_choice_str(row.unlisted_unaddressed).into()),
            );
            table_map.insert(scope_key(*scope), CanonJson::Obj(row_map));
        }

        let rules_arr: Vec<CanonJson> = canon
            .proactive_rules
            .iter()
            .map(|r| {
                let mut rm = BTreeMap::new();
                rm.insert("description", CanonJson::Str(r.description.clone()));
                rm.insert("enabled", CanonJson::Bool(r.enabled));
                rm.insert(
                    "receiving_scopes",
                    CanonJson::Arr(
                        r.receiving_scopes
                            .iter()
                            .map(|s| CanonJson::Str(scope_key(*s)))
                            .collect(),
                    ),
                );
                rm.insert("rule_id", CanonJson::Str(r.rule_id.clone()));
                rm.insert("silent_ack", CanonJson::Bool(r.silent_ack));
                rm.insert("title", CanonJson::Str(r.title.clone()));
                rm.insert(
                    "writable_scope",
                    CanonJson::Arr(
                        r.writable_scope
                            .iter()
                            .map(|w| CanonJson::Str(w.clone()))
                            .collect(),
                    ),
                );
                CanonJson::Obj(rm)
            })
            .collect();

        let mut root = BTreeMap::new();
        root.insert(
            "accept_mode",
            CanonJson::Str(accept_mode_str(canon.accept_mode).into()),
        );
        root.insert("admission_table", CanonJson::DynObj(table_map));
        root.insert(
            "allowed_actors",
            CanonJson::Arr(
                canon
                    .allowed_actors
                    .into_iter()
                    .map(CanonJson::Str)
                    .collect(),
            ),
        );
        root.insert(
            "automated_reviewers_non_bot",
            CanonJson::Arr(
                canon
                    .automated_reviewers_non_bot
                    .into_iter()
                    .map(CanonJson::Str)
                    .collect(),
            ),
        );
        root.insert(
            "bot_allowlist",
            CanonJson::Arr(
                canon
                    .bot_allowlist
                    .into_iter()
                    .map(CanonJson::Str)
                    .collect(),
            ),
        );
        root.insert(
            "policy_schema_version",
            CanonJson::Str(canon.policy_schema_version),
        );
        root.insert("proactive_rules", CanonJson::Arr(rules_arr));

        let serialized = serde_json::to_string(&CanonJson::Obj(root))
            .map_err(|e| AlphaOvcaError::PolicyValidation(format!("serialization error: {e}")))?;
        Ok(format!("sha256:{}", sha256_hex(serialized.as_bytes())))
    }

    pub fn is_actor_allowed(&self, actor: &str) -> bool {
        let norm = normalize_actor_str(actor);
        self.allowed_actors
            .iter()
            .any(|a| normalize_actor_str(a) == norm)
    }

    pub fn is_bot_allowed(&self, bot_actor: &str) -> bool {
        let norm = normalize_actor_str(bot_actor);
        self.bot_allowlist
            .iter()
            .any(|b| normalize_actor_str(b) == norm)
    }

    pub fn is_non_bot_automated_reviewer(&self, actor: &str) -> bool {
        let norm = normalize_actor_str(actor);
        self.automated_reviewers_non_bot
            .iter()
            .any(|r| normalize_actor_str(r) == norm)
    }

    pub fn rule(&self, rule_id: &str) -> Option<&ProactiveRule> {
        let target = rule_id.trim();
        self.proactive_rules
            .iter()
            .find(|r| r.rule_id.trim() == target)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorizationMandate {
    pub contract_version: String,
    pub mandate_id: String,
    pub authority_id: String,
    pub origin_thread_id: String,
    pub source_kind: TriggerSourceKind,
    pub receiving_scope: ReceivingScope,
    pub requester_actor: String,
    pub requester_is_bot: bool,
    pub strength: MandateStrength,
    pub policy_version: String,
    #[serde(default)]
    pub matched_rules: Vec<String>,
    pub writable_scope: Vec<String>,
    pub status: MandateStatus,
}

impl AuthorizationMandate {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        if self.contract_version != ovca_types::CONTRACT_VERSION {
            return Err(AlphaOvcaError::MandateViolation(format!(
                "mandate.contract_version must be {}",
                ovca_types::CONTRACT_VERSION
            )));
        }
        require_non_empty_text("mandate.mandate_id", &self.mandate_id)
            .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;
        require_non_empty_text("mandate.authority_id", &self.authority_id)
            .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;
        require_non_empty_text("mandate.origin_thread_id", &self.origin_thread_id)
            .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;
        require_non_empty_text("mandate.requester_actor", &self.requester_actor)
            .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;

        validate_policy_version_format(&self.policy_version)?;

        let is_ci_source = self.source_kind == TriggerSourceKind::GithubDefaultBranchCi;
        let is_ci_scope = self.receiving_scope == ReceivingScope::GithubDefaultBranchCi;
        if is_ci_source != is_ci_scope {
            return Err(AlphaOvcaError::MandateViolation(
                "github_default_branch_ci source_kind and receiving_scope must be paired symmetrically"
                    .into(),
            ));
        }

        let bot_identity = self.requester_is_bot
            || self.source_kind == TriggerSourceKind::Bot
            || is_bot_login(&self.requester_actor);
        if bot_identity && self.strength == MandateStrength::Explicit {
            return Err(AlphaOvcaError::MandateViolation(
                "bot identities cannot hold explicit mandate strength (inferred only)".into(),
            ));
        }
        if is_ci_source && self.strength == MandateStrength::Explicit {
            return Err(AlphaOvcaError::MandateViolation(
                "CI triggers have no human sender and cannot hold explicit mandate strength".into(),
            ));
        }
        if self.strength == MandateStrength::Inferred && self.matched_rules.is_empty() {
            return Err(AlphaOvcaError::MandateViolation(
                "inferred mandate must record at least one matched proactive rule".into(),
            ));
        }
        let mut seen_rules = BTreeSet::new();
        for rule in &self.matched_rules {
            if rule.trim().is_empty() || !seen_rules.insert(rule.trim().to_string()) {
                return Err(AlphaOvcaError::MandateViolation(
                    "mandate.matched_rules must contain non-empty unique rule IDs".into(),
                ));
            }
        }
        if self.writable_scope.is_empty() {
            return Err(AlphaOvcaError::MandateViolation(
                "mandate.writable_scope must contain at least one path".into(),
            ));
        }
        let mut seen_scope = BTreeSet::new();
        for item in &self.writable_scope {
            validate_safe_scope_pattern(item)
                .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;
            if !seen_scope.insert(normalize_scope_string(item)) {
                return Err(AlphaOvcaError::MandateViolation(format!(
                    "duplicate writable_scope entry '{item}'"
                )));
            }
        }
        Ok(())
    }

    pub fn bind_to_brief(&self, brief: &ConditioningBrief) -> Result<(), AlphaOvcaError> {
        self.validate()?;
        if self.authority_id != brief.authority.authority_id {
            return Err(AlphaOvcaError::MandateViolation(format!(
                "mandate.authority_id '{}' does not match brief.authority.authority_id '{}'",
                self.authority_id, brief.authority.authority_id
            )));
        }
        for entry in &self.writable_scope {
            if !is_path_within_scope(entry, &brief.authority.scope) {
                return Err(AlphaOvcaError::MandateViolation(format!(
                    "mandate.writable_scope '{entry}' exceeds ConditioningBrief.authority.scope"
                )));
            }
        }
        Ok(())
    }
}

/// Compute conservative intersection of writable scopes across matched proactive rules.
pub fn intersect_rule_scopes(rules: &[&ProactiveRule]) -> Vec<String> {
    if rules.is_empty() {
        return vec![];
    }
    if rules.len() == 1 {
        let unique: BTreeSet<String> = rules[0]
            .writable_scope
            .iter()
            .map(|s| normalize_scope_string(s))
            .collect();
        return unique.into_iter().collect();
    }

    let mut common = BTreeSet::new();
    for (idx, rule) in rules.iter().enumerate() {
        let other_scopes: Vec<&[String]> = rules
            .iter()
            .enumerate()
            .filter(|(j, _)| *j != idx)
            .map(|(_, r)| r.writable_scope.as_slice())
            .collect();
        for cand in &rule.writable_scope {
            let clean = normalize_scope_string(cand);
            if other_scopes
                .iter()
                .all(|other| is_path_within_scope(&clean, other))
            {
                common.insert(clean);
            }
        }
    }
    common.into_iter().collect()
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MandateRevalidationReport {
    pub mandate_id: String,
    pub valid_to_resume: bool,
    pub resulting_status: MandateStatus,
    pub policy_changed: bool,
    pub current_policy_version: String,
    pub reason: String,
}

/// Revalidate a Mandate against the current `AdmissionPolicy` before resuming or continuing work.
pub fn revalidate_mandate(
    mandate: &AuthorizationMandate,
    policy: &AdmissionPolicy,
) -> Result<MandateRevalidationReport, AlphaOvcaError> {
    mandate.validate()?;
    policy.validate()?;
    let current_version = policy.canonical_policy_version()?;
    let policy_changed = mandate.policy_version != current_version;

    match mandate.status {
        MandateStatus::StoppedByPerson => {
            return Ok(MandateRevalidationReport {
                mandate_id: mandate.mandate_id.clone(),
                valid_to_resume: false,
                resulting_status: MandateStatus::StoppedByPerson,
                policy_changed,
                current_policy_version: current_version,
                reason: "mandate was explicitly stopped by a person and cannot resume".into(),
            });
        }
        MandateStatus::Revoked => {
            return Ok(MandateRevalidationReport {
                mandate_id: mandate.mandate_id.clone(),
                valid_to_resume: false,
                resulting_status: MandateStatus::Revoked,
                policy_changed,
                current_policy_version: current_version,
                reason: "mandate is already revoked".into(),
            });
        }
        MandateStatus::Active | MandateStatus::Ended => {}
    }

    match mandate.strength {
        MandateStrength::Explicit => {
            if policy.is_non_bot_automated_reviewer(&mandate.requester_actor)
                || mandate.requester_is_bot
                || mandate.source_kind == TriggerSourceKind::Bot
                || is_bot_login(&mandate.requester_actor)
                || mandate.source_kind == TriggerSourceKind::GithubDefaultBranchCi
                || mandate.receiving_scope == ReceivingScope::GithubDefaultBranchCi
            {
                return Ok(MandateRevalidationReport {
                    mandate_id: mandate.mandate_id.clone(),
                    valid_to_resume: false,
                    resulting_status: MandateStatus::Revoked,
                    policy_changed,
                    current_policy_version: current_version,
                    reason: format!(
                        "explicit mandate disallowed for automated/bot/CI identity or surface '{}'",
                        mandate.requester_actor
                    ),
                });
            }
            let row = policy.admission_table.get(&mandate.receiving_scope);
            let allowed_explicit = if policy.is_actor_allowed(&mandate.requester_actor) {
                row.is_some_and(|r| r.listed_addressed == AdmissionChoice::Explicit)
            } else {
                row.is_some_and(|r| r.unlisted_addressed == AdmissionChoice::Explicit)
            };
            if !allowed_explicit {
                return Ok(MandateRevalidationReport {
                    mandate_id: mandate.mandate_id.clone(),
                    valid_to_resume: false,
                    resulting_status: MandateStatus::Revoked,
                    policy_changed,
                    current_policy_version: current_version,
                    reason: format!(
                        "explicit requester '{}' no longer qualifies under current policy for {:?}",
                        mandate.requester_actor, mandate.receiving_scope
                    ),
                });
            }
            Ok(MandateRevalidationReport {
                mandate_id: mandate.mandate_id.clone(),
                valid_to_resume: true,
                resulting_status: mandate.status,
                policy_changed,
                current_policy_version: current_version,
                reason: if policy_changed {
                    "explicit mandate remains valid; policy_changed notice attached".into()
                } else {
                    "explicit mandate valid under current policy".into()
                },
            })
        }
        MandateStrength::Inferred => {
            if policy.accept_mode != AcceptMode::Auto {
                return Ok(MandateRevalidationReport {
                    mandate_id: mandate.mandate_id.clone(),
                    valid_to_resume: false,
                    resulting_status: MandateStatus::Revoked,
                    policy_changed,
                    current_policy_version: current_version,
                    reason: format!(
                        "inferred mandate requires accept_mode='auto' to resume (current: {:?})",
                        policy.accept_mode
                    ),
                });
            }
            let mut matched_rule_objs: Vec<&ProactiveRule> =
                Vec::with_capacity(mandate.matched_rules.len());
            for rule_id in &mandate.matched_rules {
                match policy.rule(rule_id) {
                    Some(r) if r.enabled => {
                        if !r.receiving_scopes.contains(&mandate.receiving_scope) {
                            return Ok(MandateRevalidationReport {
                                mandate_id: mandate.mandate_id.clone(),
                                valid_to_resume: false,
                                resulting_status: MandateStatus::Revoked,
                                policy_changed,
                                current_policy_version: current_version,
                                reason: format!(
                                    "matched rule '{rule_id}' no longer applies to receiving_scope {:?}",
                                    mandate.receiving_scope
                                ),
                            });
                        }
                        matched_rule_objs.push(r);
                    }
                    Some(_) => {
                        return Ok(MandateRevalidationReport {
                            mandate_id: mandate.mandate_id.clone(),
                            valid_to_resume: false,
                            resulting_status: MandateStatus::Revoked,
                            policy_changed,
                            current_policy_version: current_version,
                            reason: format!("matched rule '{rule_id}' is now disabled"),
                        });
                    }
                    None => {
                        return Ok(MandateRevalidationReport {
                            mandate_id: mandate.mandate_id.clone(),
                            valid_to_resume: false,
                            resulting_status: MandateStatus::Revoked,
                            policy_changed,
                            current_policy_version: current_version,
                            reason: format!("matched rule '{rule_id}' was removed from policy"),
                        });
                    }
                }
            }

            let bounded_scope = intersect_rule_scopes(&matched_rule_objs);
            if bounded_scope.is_empty() {
                return Ok(MandateRevalidationReport {
                    mandate_id: mandate.mandate_id.clone(),
                    valid_to_resume: false,
                    resulting_status: MandateStatus::Revoked,
                    policy_changed,
                    current_policy_version: current_version,
                    reason: "matched rules have disjoint writable_scope under current policy"
                        .into(),
                });
            }
            for entry in &mandate.writable_scope {
                if !is_path_within_scope(entry, &bounded_scope) {
                    return Ok(MandateRevalidationReport {
                        mandate_id: mandate.mandate_id.clone(),
                        valid_to_resume: false,
                        resulting_status: MandateStatus::Revoked,
                        policy_changed,
                        current_policy_version: current_version,
                        reason: format!(
                            "mandate writable_scope '{entry}' exceeds narrowed rule scope under current policy"
                        ),
                    });
                }
            }

            if mandate.source_kind == TriggerSourceKind::GithubDefaultBranchCi
                || mandate.receiving_scope == ReceivingScope::GithubDefaultBranchCi
            {
                let ci_enabled = policy
                    .admission_table
                    .get(&ReceivingScope::GithubDefaultBranchCi)
                    .is_some_and(|r| r.unlisted_unaddressed == UnaddressedChoice::Inferred);
                if !ci_enabled {
                    return Ok(MandateRevalidationReport {
                        mandate_id: mandate.mandate_id.clone(),
                        valid_to_resume: false,
                        resulting_status: MandateStatus::Revoked,
                        policy_changed,
                        current_policy_version: current_version,
                        reason: "github_default_branch_ci admission cell set to ignore".into(),
                    });
                }
            } else if mandate.requester_is_bot
                || mandate.source_kind == TriggerSourceKind::Bot
                || is_bot_login(&mandate.requester_actor)
            {
                if !policy.is_bot_allowed(&mandate.requester_actor)
                    || !policy
                        .admission_table
                        .contains_key(&mandate.receiving_scope)
                {
                    return Ok(MandateRevalidationReport {
                        mandate_id: mandate.mandate_id.clone(),
                        valid_to_resume: false,
                        resulting_status: MandateStatus::Revoked,
                        policy_changed,
                        current_policy_version: current_version,
                        reason: format!(
                            "bot '{}' removed from bot_allowlist or surface missing",
                            mandate.requester_actor
                        ),
                    });
                }
            } else if policy.is_non_bot_automated_reviewer(&mandate.requester_actor) {
                if !policy
                    .admission_table
                    .contains_key(&mandate.receiving_scope)
                {
                    return Ok(MandateRevalidationReport {
                        mandate_id: mandate.mandate_id.clone(),
                        valid_to_resume: false,
                        resulting_status: MandateStatus::Revoked,
                        policy_changed,
                        current_policy_version: current_version,
                        reason: format!(
                            "receiving_scope '{:?}' missing for automated reviewer '{}'",
                            mandate.receiving_scope, mandate.requester_actor
                        ),
                    });
                }
            } else {
                let row = policy.admission_table.get(&mandate.receiving_scope);
                let still_admitted = row.is_some_and(|r| {
                    if policy.is_actor_allowed(&mandate.requester_actor) {
                        r.listed_addressed != AdmissionChoice::Ignore
                            || (r.receive_all
                                && r.listed_unaddressed == UnaddressedChoice::Inferred)
                    } else {
                        r.unlisted_addressed != AdmissionChoice::Ignore
                            || (r.receive_all
                                && r.unlisted_unaddressed == UnaddressedChoice::Inferred)
                    }
                });
                if !still_admitted {
                    return Ok(MandateRevalidationReport {
                        mandate_id: mandate.mandate_id.clone(),
                        valid_to_resume: false,
                        resulting_status: MandateStatus::Revoked,
                        policy_changed,
                        current_policy_version: current_version,
                        reason: format!(
                            "admission table or allowed_actors weakened for '{}'",
                            mandate.requester_actor
                        ),
                    });
                }
            }

            Ok(MandateRevalidationReport {
                mandate_id: mandate.mandate_id.clone(),
                valid_to_resume: true,
                resulting_status: mandate.status,
                policy_changed,
                current_policy_version: current_version,
                reason: if policy_changed {
                    "inferred mandate remains valid; policy_changed notice attached".into()
                } else {
                    "inferred mandate valid under current policy".into()
                },
            })
        }
    }
}

fn default_addressed_kind() -> AddressedKind {
    AddressedKind::None
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FollowUpEvent {
    pub trigger_id: String,
    pub thread_id: String,
    pub subscription_mode: SubscriptionMode,
    pub actor: String,
    pub actor_is_bot: bool,
    pub is_ci: bool,
    #[serde(default = "default_addressed_kind")]
    pub addressed: AddressedKind,
    #[serde(default)]
    pub requested_scope_paths: Vec<String>,
    #[serde(default)]
    pub requests_stop: bool,
    #[serde(default)]
    pub requests_scope_expansion: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FollowUpAction {
    ProceedInScope,
    ContextOnlyDeliver,
    HandbackRequired,
    StopRequested,
    RevokedCannotResume,
    IgnoreStoppedOrRevoked,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HandbackRecord {
    pub mandate_id: String,
    pub trigger_id: String,
    pub preserve_subscription: bool,
    pub out_of_scope_paths: Vec<String>,
    pub route_to: String,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FollowUpDecision {
    pub action: FollowUpAction,
    pub grant_authority: bool,
    pub allow_resume: bool,
    pub policy_changed_notice: bool,
    pub out_of_scope_paths: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub handback: Option<HandbackRecord>,
    pub reason: String,
}

/// Enforce `Context != Authority`: subscribed threads / bots / CI never expand Mandate scope
/// or gain authority; out-of-scope human follow-ups emit structured `HandbackRecord`.
pub fn evaluate_followup(
    mandate: &AuthorizationMandate,
    followup: &FollowUpEvent,
    policy: &AdmissionPolicy,
) -> Result<FollowUpDecision, AlphaOvcaError> {
    mandate.validate()?;
    policy.validate()?;
    require_non_empty_text("followup.trigger_id", &followup.trigger_id)
        .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;
    require_non_empty_text("followup.thread_id", &followup.thread_id)
        .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;
    require_non_empty_text("followup.actor", &followup.actor)
        .map_err(|e| AlphaOvcaError::MandateViolation(e.to_string()))?;

    let reval = revalidate_mandate(mandate, policy)?;

    if matches!(
        mandate.status,
        MandateStatus::StoppedByPerson | MandateStatus::Revoked
    ) {
        return Ok(FollowUpDecision {
            action: FollowUpAction::IgnoreStoppedOrRevoked,
            grant_authority: false,
            allow_resume: false,
            policy_changed_notice: reval.policy_changed,
            out_of_scope_paths: vec![],
            handback: None,
            reason: reval.reason,
        });
    }

    if followup.subscription_mode == SubscriptionMode::ContextOnly
        || followup.thread_id != mandate.origin_thread_id
    {
        return Ok(FollowUpDecision {
            action: FollowUpAction::ContextOnlyDeliver,
            grant_authority: false,
            allow_resume: false,
            policy_changed_notice: reval.policy_changed,
            out_of_scope_paths: vec![],
            handback: None,
            reason: "context-only subscription or secondary thread grants no authority or resume"
                .into(),
        });
    }

    let is_automated_sender = followup.actor_is_bot
        || followup.is_ci
        || is_bot_login(&followup.actor)
        || policy.is_non_bot_automated_reviewer(&followup.actor);
    if is_automated_sender {
        if mandate.status == MandateStatus::Ended {
            return Ok(FollowUpDecision {
                action: FollowUpAction::ContextOnlyDeliver,
                grant_authority: false,
                allow_resume: false,
                policy_changed_notice: reval.policy_changed,
                out_of_scope_paths: vec![],
                handback: None,
                reason: "bots, CI, and automated reviewers cannot wake an ended mandate or grant stop/new authority"
                    .into(),
            });
        }
        return Ok(FollowUpDecision {
            action: FollowUpAction::ContextOnlyDeliver,
            grant_authority: false,
            allow_resume: false,
            policy_changed_notice: reval.policy_changed,
            out_of_scope_paths: vec![],
            handback: None,
            reason: "automated/bot/CI event delivered as untrusted context only; mandate scope unchanged"
                .into(),
        });
    }

    let is_listed = policy.is_actor_allowed(&followup.actor);
    let row = policy.admission_table.get(&mandate.receiving_scope);
    let is_addressed = matches!(
        followup.addressed,
        AddressedKind::Mention | AddressedKind::Direct
    );

    let is_explicit_followup_actor = if is_listed {
        mandate.receiving_scope == ReceivingScope::GithubDefaultBranchCi
            || row.is_some_and(|r| r.listed_addressed == AdmissionChoice::Explicit)
    } else {
        is_addressed && row.is_some_and(|r| r.unlisted_addressed == AdmissionChoice::Explicit)
    };

    if !is_explicit_followup_actor {
        if policy.accept_mode != AcceptMode::Auto {
            return Ok(FollowUpDecision {
                action: FollowUpAction::ContextOnlyDeliver,
                grant_authority: false,
                allow_resume: false,
                policy_changed_notice: reval.policy_changed,
                out_of_scope_paths: vec![],
                handback: None,
                reason: format!(
                    "actor '{}' follow-up lacks explicit authority and yields context-only while accept_mode is '{:?}'",
                    followup.actor, policy.accept_mode
                ),
            });
        }
        if mandate.receiving_scope == ReceivingScope::GithubDefaultBranchCi {
            return Ok(FollowUpDecision {
                action: FollowUpAction::ContextOnlyDeliver,
                grant_authority: false,
                allow_resume: false,
                policy_changed_notice: reval.policy_changed,
                out_of_scope_paths: vec![],
                handback: None,
                reason: format!(
                    "unlisted actor '{}' cannot act on github_default_branch_ci mandate",
                    followup.actor
                ),
            });
        }
        let inferred_admitted = row.is_some_and(|r| {
            if is_listed {
                if is_addressed {
                    r.listed_addressed != AdmissionChoice::Ignore
                } else {
                    r.listed_addressed != AdmissionChoice::Ignore
                        || (r.receive_all && r.listed_unaddressed == UnaddressedChoice::Inferred)
                }
            } else if is_addressed {
                r.unlisted_addressed != AdmissionChoice::Ignore
            } else {
                r.receive_all && r.unlisted_unaddressed == UnaddressedChoice::Inferred
            }
        });
        if !inferred_admitted {
            return Ok(FollowUpDecision {
                action: FollowUpAction::ContextOnlyDeliver,
                grant_authority: false,
                allow_resume: false,
                policy_changed_notice: reval.policy_changed,
                out_of_scope_paths: vec![],
                handback: None,
                reason: format!(
                    "actor '{}' is not admitted by admission_table for {:?} follow-up",
                    followup.actor, mandate.receiving_scope
                ),
            });
        }
    }

    if followup.requests_stop {
        if !is_explicit_followup_actor {
            return Ok(FollowUpDecision {
                action: FollowUpAction::ContextOnlyDeliver,
                grant_authority: false,
                allow_resume: false,
                policy_changed_notice: reval.policy_changed,
                out_of_scope_paths: vec![],
                handback: None,
                reason: format!(
                    "unlisted actor '{}' cannot stop an owner/explicit mandate",
                    followup.actor
                ),
            });
        }
        return Ok(FollowUpDecision {
            action: FollowUpAction::StopRequested,
            grant_authority: false,
            allow_resume: false,
            policy_changed_notice: reval.policy_changed,
            out_of_scope_paths: vec![],
            handback: None,
            reason: "human stop request routed through Eval gate to mark mandate stopped_by_person"
                .into(),
        });
    }

    if !reval.valid_to_resume {
        return Ok(FollowUpDecision {
            action: FollowUpAction::RevokedCannotResume,
            grant_authority: false,
            allow_resume: false,
            policy_changed_notice: reval.policy_changed,
            out_of_scope_paths: vec![],
            handback: None,
            reason: reval.reason,
        });
    }

    let out_of_scope: Vec<String> = followup
        .requested_scope_paths
        .iter()
        .filter(|path| !is_path_within_scope(path, &mandate.writable_scope))
        .cloned()
        .collect();

    if followup.requests_scope_expansion || !out_of_scope.is_empty() {
        let reason = if !out_of_scope.is_empty() {
            format!(
                "requested paths exceed mandate.writable_scope: {}",
                out_of_scope.join(", ")
            )
        } else {
            "follow-up requested work beyond mandate objective/scope; immutable mandate kept intact"
                .into()
        };
        return Ok(FollowUpDecision {
            action: FollowUpAction::HandbackRequired,
            grant_authority: false,
            allow_resume: false,
            policy_changed_notice: reval.policy_changed,
            out_of_scope_paths: out_of_scope.clone(),
            handback: Some(HandbackRecord {
                mandate_id: mandate.mandate_id.clone(),
                trigger_id: followup.trigger_id.clone(),
                preserve_subscription: true,
                out_of_scope_paths: out_of_scope,
                route_to: "fresh_eval".into(),
                reason: reason.clone(),
            }),
            reason,
        });
    }

    Ok(FollowUpDecision {
        action: FollowUpAction::ProceedInScope,
        grant_authority: true,
        allow_resume: mandate.status == MandateStatus::Ended,
        policy_changed_notice: reval.policy_changed,
        out_of_scope_paths: vec![],
        handback: None,
        reason: if mandate.status == MandateStatus::Ended {
            "human follow-up passed revalidation and fits mandate.writable_scope (resumed)".into()
        } else {
            "human follow-up fits active mandate.writable_scope".into()
        },
    })
}

/// Segment-safe containment check preventing prefix confusion (`python/alpha` vs `python/alpha_evil`)
/// and rejecting path traversal (`..`), absolute paths, drive prefixes, backslashes, or null bytes.
pub fn is_path_within_scope(candidate: &str, allowed_scopes: &[String]) -> bool {
    let trimmed = candidate.trim();
    if trimmed.is_empty()
        || trimmed.starts_with('/')
        || trimmed.starts_with('\\')
        || trimmed.contains('\\')
        || trimmed.contains('\0')
        || trimmed.chars().nth(1) == Some(':')
    {
        return false;
    }

    let cand_parts = match normalized_segments(trimmed) {
        Some(p) if !p.is_empty() => p,
        _ => return false,
    };

    for raw_scope in allowed_scopes {
        let Some(scope_parts) = normalized_segments(raw_scope) else {
            continue;
        };
        if scope_parts.is_empty() {
            continue;
        }
        if cand_parts.len() >= scope_parts.len() && cand_parts[..scope_parts.len()] == scope_parts {
            return true;
        }
    }
    false
}

fn normalized_segments(raw: &str) -> Option<Vec<&str>> {
    let clean = raw.trim().trim_end_matches('/');
    if clean.is_empty()
        || clean.starts_with('/')
        || clean.contains('\\')
        || clean.contains('\0')
        || clean.chars().nth(1) == Some(':')
    {
        return None;
    }
    let mut parts = Vec::new();
    for seg in clean.split('/') {
        if seg.is_empty() || seg == "." || seg == ".." {
            return None;
        }
        parts.push(seg);
    }
    Some(parts)
}

fn validate_safe_scope_pattern(raw: &str) -> Result<(), AlphaOvcaError> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err(AlphaOvcaError::PolicyValidation(
            "writable_scope entry must not be empty".into(),
        ));
    }
    if trimmed.starts_with('/') || trimmed.contains('\\') || trimmed.contains('\0') {
        return Err(AlphaOvcaError::PolicyValidation(format!(
            "writable_scope entry '{raw}' must be repository-relative with forward slashes"
        )));
    }
    if normalized_segments(trimmed).is_none() {
        return Err(AlphaOvcaError::PolicyValidation(format!(
            "writable_scope entry '{raw}' contains invalid path segments or drive prefix (e.g. '.', '..', empty, 'C:')"
        )));
    }
    Ok(())
}

fn normalize_scope_string(raw: &str) -> String {
    raw.trim().to_string()
}

fn validate_policy_version_format(version: &str) -> Result<(), AlphaOvcaError> {
    let v = version.trim();
    if let Some(hex) = v.strip_prefix("sha256:") {
        if hex.len() == 64 && hex.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) {
            return Ok(());
        }
    }
    Err(AlphaOvcaError::MandateViolation(format!(
        "policy_version must match 'sha256:<64 lowercase hex chars>', got '{version}'"
    )))
}

fn normalize_actor_str(actor: &str) -> String {
    actor.trim().to_lowercase()
}

fn is_bot_login(actor: &str) -> bool {
    normalize_actor_str(actor).ends_with("[bot]")
}

fn normalize_actor_list(
    field: &str,
    items: &[String],
    require_non_empty: bool,
) -> Result<BTreeSet<String>, AlphaOvcaError> {
    if require_non_empty && items.is_empty() {
        return Err(AlphaOvcaError::PolicyValidation(format!(
            "{field} must contain at least one actor"
        )));
    }
    let mut set = BTreeSet::new();
    for item in items {
        let norm = normalize_actor_str(item);
        if norm.is_empty() {
            return Err(AlphaOvcaError::PolicyValidation(format!(
                "{field} must not contain empty actor entries"
            )));
        }
        if !set.insert(norm.clone()) {
            return Err(AlphaOvcaError::PolicyValidation(format!(
                "{field} must not contain duplicate actor '{norm}'"
            )));
        }
    }
    Ok(set)
}

fn require_non_empty_text(field: &str, value: &str) -> Result<(), AlphaOvcaError> {
    if value.trim().is_empty() {
        Err(AlphaOvcaError::PolicyValidation(format!(
            "{field} must not be empty"
        )))
    } else {
        Ok(())
    }
}
