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

COMMIT;

