BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_foundation

CREATE TABLE platform_settings (
    id INTEGER NOT NULL, 
    free_until TIMESTAMP WITH TIME ZONE, 
    registration_open BOOLEAN NOT NULL, 
    plans JSON NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE rate_buckets (
    id VARCHAR NOT NULL, 
    hits INTEGER NOT NULL, 
    window_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE tenants (
    id VARCHAR NOT NULL, 
    slug VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    free_until TIMESTAMP WITH TIME ZONE, 
    settings JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_tenants_slug ON tenants (slug);

CREATE TABLE users (
    id VARCHAR NOT NULL, 
    email VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    password_hash VARCHAR NOT NULL, 
    verified BOOLEAN NOT NULL, 
    platform_admin BOOLEAN NOT NULL, 
    disabled BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE agent_runs (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    request_id VARCHAR NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    funding VARCHAR NOT NULL, 
    input JSON NOT NULL, 
    output JSON NOT NULL, 
    error_code VARCHAR NOT NULL, 
    error VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_agent_runs_tenant_id ON agent_runs (tenant_id);

CREATE TABLE assets (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    object_key VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    mime VARCHAR NOT NULL, 
    size INTEGER NOT NULL, 
    sha256 VARCHAR NOT NULL, 
    consent BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_assets_tenant_id ON assets (tenant_id);

CREATE TABLE audit_events (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    action VARCHAR NOT NULL, 
    target_id VARCHAR NOT NULL, 
    detail JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_audit_events_tenant_id ON audit_events (tenant_id);

CREATE TABLE auth_sessions (
    id VARCHAR NOT NULL, 
    user_id VARCHAR NOT NULL, 
    csrf_hash VARCHAR NOT NULL, 
    tenant_id VARCHAR, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE budget_buckets (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    period VARCHAR NOT NULL, 
    resource VARCHAR NOT NULL, 
    used INTEGER NOT NULL, 
    reserved INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, period, resource), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_budget_buckets_tenant_id ON budget_buckets (tenant_id);

CREATE TABLE contents (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    title VARCHAR NOT NULL, 
    form VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    current_version INTEGER NOT NULL, 
    topic_id VARCHAR, 
    created_by VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_contents_tenant_id ON contents (tenant_id);

CREATE TABLE conversations (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    token_hash VARCHAR NOT NULL, 
    channel VARCHAR NOT NULL, 
    external_user VARCHAR NOT NULL, 
    state VARCHAR NOT NULL, 
    title VARCHAR NOT NULL, 
    lead_id VARCHAR, 
    tags JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_conversations_tenant_id ON conversations (tenant_id);

CREATE TABLE email_tokens (
    id VARCHAR NOT NULL, 
    user_id VARCHAR NOT NULL, 
    purpose VARCHAR NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE integrations (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    provider VARCHAR NOT NULL, 
    secret_cipher VARCHAR NOT NULL, 
    config JSON NOT NULL, 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, provider), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_integrations_tenant_id ON integrations (tenant_id);

CREATE TABLE knowledge_chunks (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    record_id VARCHAR NOT NULL, 
    title VARCHAR NOT NULL, 
    body VARCHAR NOT NULL, 
    version INTEGER NOT NULL, 
    embedding VECTOR(1024), 
    PRIMARY KEY (id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_knowledge_chunks_tenant_id ON knowledge_chunks (tenant_id);

CREATE TABLE media_jobs (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    prompt VARCHAR NOT NULL, 
    funding VARCHAR NOT NULL, 
    request_id VARCHAR NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    provider_task_id VARCHAR, 
    provider_request_id VARCHAR, 
    parameters JSON NOT NULL, 
    asset_ids JSON NOT NULL, 
    error_code VARCHAR NOT NULL, 
    error VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_media_jobs_tenant_id ON media_jobs (tenant_id);

CREATE TABLE memberships (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    user_id VARCHAR NOT NULL, 
    role VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, user_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_memberships_user_id ON memberships (user_id);

CREATE INDEX ix_memberships_tenant_id ON memberships (tenant_id);

CREATE TABLE metric_snapshots (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    publish_job_id VARCHAR NOT NULL, 
    metrics JSON NOT NULL, 
    source VARCHAR NOT NULL, 
    summary VARCHAR NOT NULL, 
    eligible BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_metric_snapshots_tenant_id ON metric_snapshots (tenant_id);

CREATE TABLE records (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR NOT NULL, 
    data JSON NOT NULL, 
    version INTEGER NOT NULL, 
    created_by VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_records_tenant_id ON records (tenant_id);

CREATE INDEX ix_records_kind ON records (kind);

CREATE INDEX ix_record_kind ON records (tenant_id, kind);

CREATE TABLE rubric_candidates (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    form VARCHAR NOT NULL, 
    weights JSON NOT NULL, 
    notes VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    corpus_hash VARCHAR NOT NULL, 
    report JSON NOT NULL, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_rubric_candidates_tenant_id ON rubric_candidates (tenant_id);

CREATE TABLE social_accounts (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    platform VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    config JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_social_accounts_tenant_id ON social_accounts (tenant_id);

CREATE TABLE usage_records (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    request_id VARCHAR NOT NULL, 
    resource VARCHAR NOT NULL, 
    funding VARCHAR NOT NULL, 
    reserved INTEGER NOT NULL, 
    actual INTEGER NOT NULL, 
    cost_fen INTEGER NOT NULL, 
    unit_rate_fen INTEGER NOT NULL, 
    unit_scale INTEGER NOT NULL, 
    estimated BOOLEAN NOT NULL, 
    state VARCHAR NOT NULL, 
    period VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id, resource), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_usage_records_tenant_id ON usage_records (tenant_id);

CREATE TABLE webhook_receipts (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    external_id VARCHAR NOT NULL, 
    body_hash VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, external_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_webhook_receipts_tenant_id ON webhook_receipts (tenant_id);

CREATE TABLE content_versions (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    content_id VARCHAR NOT NULL, 
    version INTEGER NOT NULL, 
    title VARCHAR NOT NULL, 
    body VARCHAR NOT NULL, 
    assets JSON NOT NULL, 
    content_hash VARCHAR NOT NULL, 
    policy_checked BOOLEAN NOT NULL, 
    policy_notes JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, content_id, version), 
    FOREIGN KEY(content_id, tenant_id) REFERENCES contents (id, tenant_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_content_versions_tenant_id ON content_versions (tenant_id);

CREATE TABLE credit_entries (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    enrollment_id VARCHAR NOT NULL, 
    student_id VARCHAR, 
    lesson_id VARCHAR, 
    delta INTEGER NOT NULL, 
    kind VARCHAR NOT NULL, 
    request_id VARCHAR NOT NULL, 
    reverses_id VARCHAR, 
    actor_id VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    FOREIGN KEY(enrollment_id, tenant_id) REFERENCES records (id, tenant_id), 
    UNIQUE (tenant_id, reverses_id), 
    UNIQUE (tenant_id, enrollment_id, lesson_id, kind), 
    UNIQUE (tenant_id, student_id, lesson_id, kind), 
    FOREIGN KEY(student_id, tenant_id) REFERENCES records (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_credit_entries_tenant_id ON credit_entries (tenant_id);

CREATE TABLE ledger_entries (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    order_id VARCHAR NOT NULL, 
    entry_type VARCHAR NOT NULL, 
    amount_fen INTEGER NOT NULL, 
    request_id VARCHAR NOT NULL, 
    reverses_id VARCHAR, 
    note VARCHAR NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    FOREIGN KEY(order_id, tenant_id) REFERENCES records (id, tenant_id), 
    FOREIGN KEY(reverses_id, tenant_id) REFERENCES ledger_entries (id, tenant_id), 
    UNIQUE (id, tenant_id), 
    UNIQUE (tenant_id, reverses_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_ledger_entries_tenant_id ON ledger_entries (tenant_id);

CREATE TABLE messages (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    conversation_id VARCHAR NOT NULL, 
    role VARCHAR NOT NULL, 
    body VARCHAR NOT NULL, 
    external_id VARCHAR, 
    sources JSON NOT NULL, 
    delivery_state VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, external_id), 
    FOREIGN KEY(conversation_id, tenant_id) REFERENCES conversations (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_messages_tenant_id ON messages (tenant_id);

CREATE TABLE settlements (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    channel_id VARCHAR NOT NULL, 
    period VARCHAR NOT NULL, 
    amount_fen INTEGER NOT NULL, 
    entries JSON NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, channel_id, period), 
    FOREIGN KEY(channel_id, tenant_id) REFERENCES records (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_settlements_tenant_id ON settlements (tenant_id);

CREATE TABLE predictions (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    version_id VARCHAR NOT NULL, 
    content_hash VARCHAR NOT NULL, 
    rubric_version VARCHAR NOT NULL, 
    payload JSON NOT NULL, 
    blind_status VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, version_id), 
    FOREIGN KEY(version_id, tenant_id) REFERENCES content_versions (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_predictions_tenant_id ON predictions (tenant_id);

CREATE TABLE publish_jobs (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    version_id VARCHAR NOT NULL, 
    account_id VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    request_id VARCHAR NOT NULL, 
    external_id VARCHAR NOT NULL, 
    external_url VARCHAR NOT NULL, 
    error_code VARCHAR NOT NULL, 
    error VARCHAR NOT NULL, 
    retro_due_at TIMESTAMP WITH TIME ZONE, 
    submitted_at TIMESTAMP WITH TIME ZONE, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    UNIQUE (tenant_id, version_id, account_id), 
    FOREIGN KEY(version_id, tenant_id) REFERENCES content_versions (id, tenant_id), 
    FOREIGN KEY(account_id, tenant_id) REFERENCES social_accounts (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_publish_jobs_tenant_id ON publish_jobs (tenant_id);

ALTER TABLE records ENABLE ROW LEVEL SECURITY;

ALTER TABLE records FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON records USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON audit_events USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE ledger_entries ENABLE ROW LEVEL SECURITY;

ALTER TABLE ledger_entries FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON ledger_entries USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE credit_entries ENABLE ROW LEVEL SECURITY;

ALTER TABLE credit_entries FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON credit_entries USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;

ALTER TABLE integrations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON integrations USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE assets ENABLE ROW LEVEL SECURITY;

ALTER TABLE assets FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON assets USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE contents ENABLE ROW LEVEL SECURITY;

ALTER TABLE contents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON contents USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE content_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE content_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON content_versions USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;

ALTER TABLE predictions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON predictions USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE agent_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON agent_runs USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE media_jobs ENABLE ROW LEVEL SECURITY;

ALTER TABLE media_jobs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON media_jobs USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE social_accounts ENABLE ROW LEVEL SECURITY;

ALTER TABLE social_accounts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON social_accounts USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE publish_jobs ENABLE ROW LEVEL SECURITY;

ALTER TABLE publish_jobs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON publish_jobs USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE metric_snapshots ENABLE ROW LEVEL SECURITY;

ALTER TABLE metric_snapshots FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON metric_snapshots USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY;

ALTER TABLE usage_records FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON usage_records USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE budget_buckets ENABLE ROW LEVEL SECURITY;

ALTER TABLE budget_buckets FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON budget_buckets USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

ALTER TABLE conversations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON conversations USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

ALTER TABLE messages FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON messages USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;

ALTER TABLE knowledge_chunks FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON knowledge_chunks USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE webhook_receipts ENABLE ROW LEVEL SECURITY;

ALTER TABLE webhook_receipts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON webhook_receipts USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE rubric_candidates ENABLE ROW LEVEL SECURITY;

ALTER TABLE rubric_candidates FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON rubric_candidates USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

ALTER TABLE settlements ENABLE ROW LEVEL SECURITY;

ALTER TABLE settlements FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON settlements USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

CREATE FUNCTION ops_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only record'; END; $$;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON predictions FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON content_versions FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON ledger_entries FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON credit_entries FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON settlements FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE UNIQUE INDEX uq_enrollment_order ON records (tenant_id, (data->>'order_id')) WHERE kind='enrollment';

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ops_app;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO ops_app;

REVOKE ALL ON alembic_version FROM ops_app;

INSERT INTO alembic_version (version_num) VALUES ('0001_foundation') RETURNING alembic_version.version_num;

-- Running upgrade 0001_foundation -> 0002_staff_social

ALTER TABLE memberships ADD COLUMN roles JSON;

ALTER TABLE memberships ADD COLUMN status VARCHAR DEFAULT 'active' NOT NULL;

ALTER TABLE memberships ADD COLUMN authz_version INTEGER DEFAULT '1' NOT NULL;

UPDATE memberships SET roles=CASE WHEN role='operator' THEN '["admissions","content_ops","academic_admin"]'::json ELSE json_build_array(role) END WHERE roles IS NULL;

ALTER TABLE assets ADD COLUMN uploaded_by VARCHAR DEFAULT '' NOT NULL;

ALTER TABLE conversations ADD COLUMN owner_id VARCHAR DEFAULT '' NOT NULL;

ALTER TABLE conversations ADD COLUMN account_id VARCHAR DEFAULT '' NOT NULL;

ALTER TABLE conversations ADD COLUMN external_thread_id VARCHAR DEFAULT '' NOT NULL;

ALTER TABLE conversations ADD COLUMN source_work_id VARCHAR DEFAULT '' NOT NULL;

ALTER TABLE conversations ADD COLUMN interaction_kind VARCHAR DEFAULT 'private_message' NOT NULL;

CREATE TABLE member_invitations (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    email VARCHAR NOT NULL, 
    roles JSON NOT NULL, 
    inviter_id VARCHAR NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    revoked BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_member_invitations_tenant_id ON member_invitations (tenant_id);

ALTER TABLE member_invitations ENABLE ROW LEVEL SECURITY;

ALTER TABLE member_invitations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON member_invitations USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON member_invitations TO ops_app;

CREATE TABLE social_events (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    account_id VARCHAR NOT NULL, 
    external_id VARCHAR NOT NULL, 
    kind VARCHAR NOT NULL, 
    thread_id VARCHAR NOT NULL, 
    work_id VARCHAR NOT NULL, 
    sender_id VARCHAR NOT NULL, 
    sender_name VARCHAR NOT NULL, 
    body VARCHAR NOT NULL, 
    conversation_id VARCHAR NOT NULL, 
    metadata_json JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, account_id, external_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(account_id, tenant_id) REFERENCES social_accounts (id, tenant_id), 
    FOREIGN KEY(conversation_id, tenant_id) REFERENCES conversations (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_social_events_tenant_id ON social_events (tenant_id);

ALTER TABLE social_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE social_events FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON social_events USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON social_events TO ops_app;

CREATE TABLE social_replies (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    account_id VARCHAR NOT NULL, 
    event_id VARCHAR NOT NULL, 
    conversation_id VARCHAR NOT NULL, 
    request_id VARCHAR NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    automatic BOOLEAN NOT NULL, 
    draft_only BOOLEAN NOT NULL, 
    body VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    external_id VARCHAR NOT NULL, 
    error VARCHAR NOT NULL, 
    sources JSON NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    FOREIGN KEY(account_id, tenant_id) REFERENCES social_accounts (id, tenant_id), 
    FOREIGN KEY(event_id, tenant_id) REFERENCES social_events (id, tenant_id), 
    FOREIGN KEY(conversation_id, tenant_id) REFERENCES conversations (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_social_replies_tenant_id ON social_replies (tenant_id);

ALTER TABLE social_replies ENABLE ROW LEVEL SECURITY;

ALTER TABLE social_replies FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON social_replies USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON social_replies TO ops_app;

UPDATE alembic_version SET version_num='0002_staff_social' WHERE alembic_version.version_num = '0001_foundation';

-- Running upgrade 0002_staff_social -> 0003_operations

CREATE TABLE addon_requests (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    addon VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    note VARCHAR NOT NULL, 
    platform_note VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_addon_requests_tenant_id ON addon_requests (tenant_id);

ALTER TABLE addon_requests ENABLE ROW LEVEL SECURITY;

ALTER TABLE addon_requests FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON addon_requests USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON addon_requests TO ops_app;

CREATE TABLE admission_imports (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    asset_id VARCHAR NOT NULL, 
    request_id VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    template_version VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    progress INTEGER NOT NULL, 
    rows_cipher VARCHAR NOT NULL, 
    error VARCHAR NOT NULL, 
    version INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_admission_imports_tenant_id ON admission_imports (tenant_id);

ALTER TABLE admission_imports ENABLE ROW LEVEL SECURITY;

ALTER TABLE admission_imports FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON admission_imports USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON admission_imports TO ops_app;

CREATE TABLE business_events (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR NOT NULL, 
    record_id VARCHAR NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    payload JSON NOT NULL, 
    request_id VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_business_events_tenant_id ON business_events (tenant_id);

CREATE INDEX ix_business_events_record_id ON business_events (record_id);

CREATE INDEX ix_business_events_kind ON business_events (kind);

ALTER TABLE business_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE business_events FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON business_events USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON business_events TO ops_app;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON business_events FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TABLE flow_instances (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    definition_id VARCHAR NOT NULL, 
    definition_version INTEGER NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    binding VARCHAR NOT NULL, 
    record_id VARCHAR NOT NULL, 
    payload_cipher VARCHAR NOT NULL, 
    state JSON NOT NULL, 
    request_id VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    revision INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_flow_instances_tenant_id ON flow_instances (tenant_id);

ALTER TABLE flow_instances ENABLE ROW LEVEL SECURITY;

ALTER TABLE flow_instances FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON flow_instances USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON flow_instances TO ops_app;

CREATE TABLE form_submissions (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    definition_id VARCHAR NOT NULL, 
    definition_version INTEGER NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    values_cipher VARCHAR NOT NULL, 
    binding VARCHAR NOT NULL, 
    record_id VARCHAR NOT NULL, 
    request_id VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    revision INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_form_submissions_tenant_id ON form_submissions (tenant_id);

ALTER TABLE form_submissions ENABLE ROW LEVEL SECURITY;

ALTER TABLE form_submissions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON form_submissions USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON form_submissions TO ops_app;

CREATE TABLE lesson_rosters (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    lesson_id VARCHAR NOT NULL, 
    class_id VARCHAR NOT NULL, 
    teacher_id VARCHAR NOT NULL, 
    student_id VARCHAR NOT NULL, 
    enrollment_id VARCHAR NOT NULL, 
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, lesson_id, enrollment_id), 
    UNIQUE (tenant_id, lesson_id, student_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_lesson_rosters_tenant_id ON lesson_rosters (tenant_id);

ALTER TABLE lesson_rosters ENABLE ROW LEVEL SECURITY;

ALTER TABLE lesson_rosters FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON lesson_rosters USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON lesson_rosters TO ops_app;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON lesson_rosters FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TABLE notification_outbox (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    request_id VARCHAR NOT NULL, 
    kind VARCHAR NOT NULL, 
    body VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    attempts INTEGER NOT NULL, 
    config_version INTEGER NOT NULL, 
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    error VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_notification_outbox_tenant_id ON notification_outbox (tenant_id);

ALTER TABLE notification_outbox ENABLE ROW LEVEL SECURITY;

ALTER TABLE notification_outbox FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON notification_outbox USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON notification_outbox TO ops_app;

CREATE TABLE ops_alerts (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    rule_id VARCHAR NOT NULL, 
    period VARCHAR NOT NULL, 
    metric VARCHAR NOT NULL, 
    value FLOAT NOT NULL, 
    threshold FLOAT NOT NULL, 
    status VARCHAR NOT NULL, 
    class_id VARCHAR NOT NULL, 
    owner_id VARCHAR NOT NULL, 
    note VARCHAR NOT NULL, 
    detail JSON NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, rule_id, period), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_ops_alerts_tenant_id ON ops_alerts (tenant_id);

ALTER TABLE ops_alerts ENABLE ROW LEVEL SECURITY;

ALTER TABLE ops_alerts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON ops_alerts USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON ops_alerts TO ops_app;

CREATE TABLE receipt_links (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR NOT NULL, 
    record_id VARCHAR NOT NULL, 
    asset_id VARCHAR NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    note VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, kind, record_id, asset_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_receipt_links_tenant_id ON receipt_links (tenant_id);

ALTER TABLE receipt_links ENABLE ROW LEVEL SECURITY;

ALTER TABLE receipt_links FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON receipt_links USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON receipt_links TO ops_app;

CREATE TABLE report_snapshots (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR NOT NULL, 
    period VARCHAR NOT NULL, 
    version INTEGER NOT NULL, 
    digest VARCHAR NOT NULL, 
    payload JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, kind, period, version), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_report_snapshots_tenant_id ON report_snapshots (tenant_id);

ALTER TABLE report_snapshots ENABLE ROW LEVEL SECURITY;

ALTER TABLE report_snapshots FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON report_snapshots USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON report_snapshots TO ops_app;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON report_snapshots FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TABLE studio_definitions (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    binding VARCHAR NOT NULL, 
    draft JSON NOT NULL, 
    version INTEGER NOT NULL, 
    published_version INTEGER NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    created_by VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE UNIQUE INDEX uq_active_business_workflow ON studio_definitions (tenant_id, binding) WHERE kind = 'workflow' AND enabled;

CREATE INDEX ix_studio_definitions_tenant_id ON studio_definitions (tenant_id);

ALTER TABLE studio_definitions ENABLE ROW LEVEL SECURITY;

ALTER TABLE studio_definitions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON studio_definitions USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON studio_definitions TO ops_app;

CREATE TABLE feedback_kpis (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    lesson_id VARCHAR NOT NULL, 
    class_id VARCHAR NOT NULL, 
    teacher_id VARCHAR NOT NULL, 
    due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    version INTEGER NOT NULL, 
    notes VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, lesson_id), 
    FOREIGN KEY(lesson_id, tenant_id) REFERENCES records (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_feedback_kpis_tenant_id ON feedback_kpis (tenant_id);

ALTER TABLE feedback_kpis ENABLE ROW LEVEL SECURITY;

ALTER TABLE feedback_kpis FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON feedback_kpis USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON feedback_kpis TO ops_app;

CREATE TABLE flow_tasks (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    instance_id VARCHAR NOT NULL, 
    node_id VARCHAR NOT NULL, 
    assignee_id VARCHAR NOT NULL, 
    node_type VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    decision_note VARCHAR NOT NULL, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, instance_id, node_id, assignee_id), 
    FOREIGN KEY(instance_id, tenant_id) REFERENCES flow_instances (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_flow_tasks_tenant_id ON flow_tasks (tenant_id);

ALTER TABLE flow_tasks ENABLE ROW LEVEL SECURITY;

ALTER TABLE flow_tasks FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON flow_tasks USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON flow_tasks TO ops_app;

CREATE TABLE studio_versions (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    definition_id VARCHAR NOT NULL, 
    kind VARCHAR NOT NULL, 
    version INTEGER NOT NULL, 
    spec JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, definition_id, version), 
    FOREIGN KEY(definition_id, tenant_id) REFERENCES studio_definitions (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_studio_versions_tenant_id ON studio_versions (tenant_id);

ALTER TABLE studio_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE studio_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON studio_versions USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON studio_versions TO ops_app;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON studio_versions FOR EACH ROW EXECUTE FUNCTION ops_append_only();

DO $$ DECLARE tid text; BEGIN
FOR tid IN SELECT id FROM tenants LOOP
PERFORM set_config('ops.tenant_id',tid,true);
UPDATE records o SET data=(o.data::jsonb || jsonb_build_object('program_name',COALESCE(o.data->>'program_name',c.data->>'name',o.data->>'name'),'purchased_units',COALESCE((o.data->>'purchased_units')::int,(o.data->>'course_lessons')::int,(c.data->>'lessons')::int,0)))::json FROM records c WHERE o.tenant_id=tid AND c.tenant_id=tid AND o.kind='order' AND c.kind='course' AND c.id=o.data->>'course_id';
UPDATE records SET data=(data::jsonb || jsonb_build_object('status',COALESCE(data->>'status','active'),'history_calibrated',COALESCE((data->>'history_calibrated')::boolean,false)))::json WHERE tenant_id=tid AND kind='enrollment';
UPDATE records SET data=(data::jsonb || jsonb_build_object('kpi_eligible',COALESCE((data->>'kpi_eligible')::boolean,false)))::json WHERE tenant_id=tid AND kind='lesson';
UPDATE tenants SET settings=(settings::jsonb || jsonb_build_object('consultation_enabled',false,'ops_schema_version',3))::json WHERE id=tid;
END LOOP;
PERFORM set_config('ops.tenant_id','',true);
END $$;

UPDATE alembic_version SET version_num='0003_operations' WHERE alembic_version.version_num = '0002_staff_social';

-- Running upgrade 0003_operations -> 0004_capabilities

UPDATE memberships m SET roles = (m.roles::jsonb || '["scheduler"]'::jsonb)::json,
                  authz_version = m.authz_version + 1 FROM tenants t
                  WHERE t.id=m.tenant_id
                  AND COALESCE((t.settings->>'authorization_schema_version')::int,0) < 1
                  AND m.roles::jsonb ? 'academic_admin' AND NOT (m.roles::jsonb ? 'scheduler');

UPDATE tenants SET settings = (settings::jsonb || jsonb_build_object('authorization_schema_version', 1))::json
                  WHERE COALESCE((settings->>'authorization_schema_version')::int,0) < 1;

UPDATE alembic_version SET version_num='0004_capabilities' WHERE alembic_version.version_num = '0003_operations';

-- Running upgrade 0004_capabilities -> 0005_media_matrix

ALTER TABLE social_accounts ADD COLUMN profile_id VARCHAR;

ALTER TABLE social_accounts ADD COLUMN identity_key VARCHAR;

ALTER TABLE social_accounts ADD COLUMN paused BOOLEAN NOT NULL DEFAULT false;

CREATE UNIQUE INDEX uq_social_identity ON social_accounts (tenant_id, identity_key);

ALTER TABLE rubric_candidates ADD COLUMN profile_id VARCHAR;

CREATE TABLE matrix_charges (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    request_id VARCHAR NOT NULL, 
    resource VARCHAR NOT NULL, 
    plan_id VARCHAR NOT NULL, 
    run_id VARCHAR NOT NULL, 
    account_id VARCHAR NOT NULL, 
    profile_id VARCHAR NOT NULL, 
    reserved_fen INTEGER NOT NULL, 
    actual_fen INTEGER NOT NULL, 
    state VARCHAR NOT NULL, 
    period VARCHAR NOT NULL, 
    day VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id, resource), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_matrix_charges_tenant_id ON matrix_charges (tenant_id);

ALTER TABLE matrix_charges ENABLE ROW LEVEL SECURITY;

ALTER TABLE matrix_charges FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON matrix_charges USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON matrix_charges TO ops_app;

CREATE TABLE media_profiles (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    name VARCHAR NOT NULL, 
    audience VARCHAR NOT NULL, 
    style VARCHAR NOT NULL, 
    knowledge_ids JSON NOT NULL, 
    asset_ids JSON NOT NULL, 
    rubrics JSON NOT NULL, 
    version INTEGER NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_media_profiles_tenant_id ON media_profiles (tenant_id);

ALTER TABLE media_profiles ENABLE ROW LEVEL SECURITY;

ALTER TABLE media_profiles FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON media_profiles USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON media_profiles TO ops_app;

CREATE TABLE account_groups (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    profile_id VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    version INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(profile_id, tenant_id) REFERENCES media_profiles (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_account_groups_tenant_id ON account_groups (tenant_id);

ALTER TABLE account_groups ENABLE ROW LEVEL SECURITY;

ALTER TABLE account_groups FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON account_groups USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON account_groups TO ops_app;

CREATE TABLE automation_plans (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    profile_id VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    spec JSON NOT NULL, 
    version INTEGER NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    authorized_by VARCHAR NOT NULL, 
    last_error VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(profile_id, tenant_id) REFERENCES media_profiles (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_automation_plans_tenant_id ON automation_plans (tenant_id);

ALTER TABLE automation_plans ENABLE ROW LEVEL SECURITY;

ALTER TABLE automation_plans FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON automation_plans USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON automation_plans TO ops_app;

CREATE TABLE account_group_members (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    group_id VARCHAR NOT NULL, 
    account_id VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, group_id, account_id), 
    FOREIGN KEY(group_id, tenant_id) REFERENCES account_groups (id, tenant_id), 
    FOREIGN KEY(account_id, tenant_id) REFERENCES social_accounts (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_account_group_members_tenant_id ON account_group_members (tenant_id);

ALTER TABLE account_group_members ENABLE ROW LEVEL SECURITY;

ALTER TABLE account_group_members FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON account_group_members USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON account_group_members TO ops_app;

CREATE TABLE automation_plan_versions (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    plan_id VARCHAR NOT NULL, 
    version INTEGER NOT NULL, 
    snapshot JSON NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, plan_id, version), 
    FOREIGN KEY(plan_id, tenant_id) REFERENCES automation_plans (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_automation_plan_versions_tenant_id ON automation_plan_versions (tenant_id);

ALTER TABLE automation_plan_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE automation_plan_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON automation_plan_versions USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON automation_plan_versions TO ops_app;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON automation_plan_versions FOR EACH ROW EXECUTE FUNCTION ops_append_only();

CREATE TABLE automation_runs (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    plan_id VARCHAR NOT NULL, 
    plan_version INTEGER NOT NULL, 
    request_id VARCHAR NOT NULL, 
    actor_id VARCHAR NOT NULL, 
    trial BOOLEAN NOT NULL, 
    status VARCHAR NOT NULL, 
    paused BOOLEAN NOT NULL, 
    snapshot JSON NOT NULL, 
    slot TIMESTAMP WITH TIME ZONE NOT NULL, 
    lease_until TIMESTAMP WITH TIME ZONE, 
    lease_token VARCHAR NOT NULL, 
    revision INTEGER NOT NULL, 
    error VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, request_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(plan_id, tenant_id) REFERENCES automation_plans (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_automation_runs_tenant_id ON automation_runs (tenant_id);

ALTER TABLE automation_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE automation_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON automation_runs USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON automation_runs TO ops_app;

CREATE TABLE automation_account_tasks (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    run_id VARCHAR NOT NULL, 
    account_id VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    stage VARCHAR NOT NULL, 
    data JSON NOT NULL, 
    content_id VARCHAR NOT NULL, 
    version_id VARCHAR NOT NULL, 
    publish_job_id VARCHAR NOT NULL, 
    error_code VARCHAR NOT NULL, 
    error VARCHAR NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, run_id, account_id), 
    UNIQUE (id, tenant_id), 
    FOREIGN KEY(run_id, tenant_id) REFERENCES automation_runs (id, tenant_id), 
    FOREIGN KEY(account_id, tenant_id) REFERENCES social_accounts (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_automation_account_tasks_tenant_id ON automation_account_tasks (tenant_id);

ALTER TABLE automation_account_tasks ENABLE ROW LEVEL SECURITY;

ALTER TABLE automation_account_tasks FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON automation_account_tasks USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON automation_account_tasks TO ops_app;

CREATE TABLE automation_steps (
    id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    task_id VARCHAR NOT NULL, 
    key VARCHAR NOT NULL, 
    status VARCHAR NOT NULL, 
    object_id VARCHAR NOT NULL, 
    detail JSON NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (tenant_id, task_id, key), 
    FOREIGN KEY(task_id, tenant_id) REFERENCES automation_account_tasks (id, tenant_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE INDEX ix_automation_steps_tenant_id ON automation_steps (tenant_id);

ALTER TABLE automation_steps ENABLE ROW LEVEL SECURITY;

ALTER TABLE automation_steps FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON automation_steps USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true));

GRANT SELECT,INSERT,UPDATE,DELETE ON automation_steps TO ops_app;

ALTER TABLE social_accounts ADD CONSTRAINT fk_social_profile FOREIGN KEY (profile_id,tenant_id) REFERENCES media_profiles(id,tenant_id);

ALTER TABLE rubric_candidates ADD CONSTRAINT fk_rubric_profile FOREIGN KEY (profile_id,tenant_id) REFERENCES media_profiles(id,tenant_id);

DO $$ DECLARE tid text; prof text; pid text; c record; cfg jsonb; spec jsonb; BEGIN
FOR tid,cfg IN SELECT id,settings::jsonb FROM tenants LOOP
PERFORM set_config('ops.tenant_id',tid,true);
IF COALESCE((cfg->>'matrix_schema_version')::int,0) < 1 THEN
IF EXISTS(SELECT 1 FROM records WHERE tenant_id=tid AND kind='campaign') THEN
prof:=md5(random()::text||clock_timestamp()::text);
INSERT INTO media_profiles(id,tenant_id,created_at,name,audience,style,knowledge_ids,asset_ids,rubrics,version,updated_at)
SELECT prof,tid,now(),name||' · 待配置品牌','请配置品牌受众','','[]','[]','{}',1,now() FROM tenants WHERE id=tid;
FOR c IN SELECT * FROM records WHERE tenant_id=tid AND kind='campaign' LOOP
pid:=md5(random()::text||clock_timestamp()::text);
spec:=jsonb_build_object('direction',COALESCE(c.data->>'objective',c.data->>'name','待配置内容方向'),'account_ids','[]'::jsonb,'group_ids','[]'::jsonb,'mode','matrix','source_urls','[]'::jsonb,'xhs_search',false,'weekdays','[1,4]'::jsonb,'times','["18:00"]'::jsonb,'timezone','Asia/Shanghai','funding','platform','review','manual','allowed_render_modes','["program","aigc","mixed"]'::jsonb,'min_video_seconds',45,'max_video_seconds',90,'run_budget_fen',0,'daily_budget_fen',0);
INSERT INTO automation_plans(id,tenant_id,created_at,profile_id,name,spec,version,enabled,actor_id,authorized_by,last_error,updated_at)
VALUES(pid,tid,now(),prof,COALESCE(c.data->>'name','历史计划')||'（待确认）',spec::json,1,false,c.created_by,'','旧计划已停用，需补齐配置',now());
INSERT INTO automation_plan_versions(id,tenant_id,created_at,plan_id,version,snapshot)
VALUES(md5(random()::text||clock_timestamp()::text),tid,now(),pid,1,jsonb_build_object('legacy_record_id',c.id,'spec',spec)::json);
UPDATE records SET data=(data::jsonb || jsonb_build_object('enabled',false,'matrix_migration','待确认品牌、明确账号、预算及试运行'))::json WHERE id=c.id AND tenant_id=tid;
END LOOP;
END IF;
UPDATE tenants SET settings=(settings::jsonb || jsonb_build_object('matrix_schema_version',1))::json WHERE id=tid;
END IF;
END LOOP;
PERFORM set_config('ops.tenant_id','',true);
END $$;

UPDATE alembic_version SET version_num='0005_media_matrix' WHERE alembic_version.version_num = '0004_capabilities';

COMMIT;

