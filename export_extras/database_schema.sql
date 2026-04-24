-- AXIOM (DataVision Pro) — Database Schema
-- PostgreSQL 16 — generated automatically
-- Use this to recreate the schema in a new database.


-- ==================== analysis_history ====================
CREATE TABLE IF NOT EXISTS analysis_history (
    id integer DEFAULT nextval('analysis_history_id_seq'::regclass) NOT NULL,
    dataset_id integer NOT NULL,
    analysis_type character varying(100) NOT NULL,
    analysis_date timestamp without time zone,
    results json,
    ai_insights text
);
CREATE UNIQUE INDEX analysis_history_pkey ON public.analysis_history USING btree (id);
CREATE INDEX ix_analysis_history_id ON public.analysis_history USING btree (id);

-- ==================== chat_history ====================
CREATE TABLE IF NOT EXISTS chat_history (
    id integer DEFAULT nextval('chat_history_id_seq'::regclass) NOT NULL,
    dataset_id integer,
    user_message text NOT NULL,
    ai_response text NOT NULL,
    timestamp timestamp without time zone
);
CREATE UNIQUE INDEX chat_history_pkey ON public.chat_history USING btree (id);
CREATE INDEX ix_chat_history_id ON public.chat_history USING btree (id);

-- ==================== dataset_records ====================
CREATE TABLE IF NOT EXISTS dataset_records (
    id integer DEFAULT nextval('dataset_records_id_seq'::regclass) NOT NULL,
    user_id integer,
    filename character varying(255) NOT NULL,
    dataset_name character varying(255) NOT NULL,
    upload_date timestamp without time zone,
    period_month integer,
    period_year integer,
    row_count integer NOT NULL,
    column_count integer NOT NULL,
    columns_info json,
    data_hash character varying(64) NOT NULL,
    summary_stats json,
    file_size double precision,
    source_parquet bytea,
    parse_meta json,
    step_recipes json,
    active_step_index integer,
    project_id integer
);
CREATE UNIQUE INDEX dataset_records_pkey ON public.dataset_records USING btree (id);
CREATE INDEX ix_dataset_records_id ON public.dataset_records USING btree (id);
CREATE INDEX ix_dataset_records_project_id ON public.dataset_records USING btree (project_id);

-- ==================== dataset_relationships ====================
CREATE TABLE IF NOT EXISTS dataset_relationships (
    id integer DEFAULT nextval('dataset_relationships_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    left_dataset_id integer NOT NULL,
    left_column character varying(255) NOT NULL,
    right_dataset_id integer NOT NULL,
    right_column character varying(255) NOT NULL,
    cardinality character varying(8) NOT NULL,
    join_type character varying(16) NOT NULL,
    created_at timestamp without time zone
);
CREATE UNIQUE INDEX dataset_relationships_pkey ON public.dataset_relationships USING btree (id);
CREATE INDEX ix_dataset_relationships_id ON public.dataset_relationships USING btree (id);
CREATE INDEX ix_dataset_relationships_user_id ON public.dataset_relationships USING btree (user_id);
CREATE INDEX ix_dataset_relationships_right_dataset_id ON public.dataset_relationships USING btree (right_dataset_id);
CREATE INDEX ix_dataset_relationships_left_dataset_id ON public.dataset_relationships USING btree (left_dataset_id);

-- ==================== password_reset_tokens ====================
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id integer DEFAULT nextval('password_reset_tokens_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    token_hash character varying(128) NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used_at timestamp without time zone,
    created_at timestamp without time zone
);
CREATE UNIQUE INDEX password_reset_tokens_pkey ON public.password_reset_tokens USING btree (id);
CREATE UNIQUE INDEX ix_password_reset_tokens_token_hash ON public.password_reset_tokens USING btree (token_hash);
CREATE INDEX ix_password_reset_tokens_id ON public.password_reset_tokens USING btree (id);
CREATE INDEX ix_password_reset_tokens_user_id ON public.password_reset_tokens USING btree (user_id);

-- ==================== project_knowledge_base ====================
CREATE TABLE IF NOT EXISTS project_knowledge_base (
    id integer DEFAULT nextval('project_knowledge_base_id_seq'::regclass) NOT NULL,
    project_id integer NOT NULL,
    source_kind character varying(16) NOT NULL,
    source_label character varying(512) NOT NULL,
    content_text text NOT NULL,
    char_count integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);
CREATE UNIQUE INDEX project_knowledge_base_pkey ON public.project_knowledge_base USING btree (id);
CREATE INDEX ix_project_knowledge_base_id ON public.project_knowledge_base USING btree (id);
CREATE UNIQUE INDEX ix_project_knowledge_base_project_id ON public.project_knowledge_base USING btree (project_id);

-- ==================== project_learned_notes ====================
CREATE TABLE IF NOT EXISTS project_learned_notes (
    id integer DEFAULT nextval('project_learned_notes_id_seq'::regclass) NOT NULL,
    project_id integer NOT NULL,
    kind character varying(16) NOT NULL,
    content text NOT NULL,
    created_at timestamp without time zone
);
CREATE UNIQUE INDEX project_learned_notes_pkey ON public.project_learned_notes USING btree (id);
CREATE INDEX ix_project_learned_notes_created_at ON public.project_learned_notes USING btree (created_at);
CREATE INDEX ix_project_learned_notes_project_id ON public.project_learned_notes USING btree (project_id);
CREATE INDEX ix_project_learned_notes_id ON public.project_learned_notes USING btree (id);

-- ==================== projects ====================
CREATE TABLE IF NOT EXISTS projects (
    id integer DEFAULT nextval('projects_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    last_opened_at timestamp without time zone
);
CREATE UNIQUE INDEX projects_pkey ON public.projects USING btree (id);
CREATE INDEX ix_projects_id ON public.projects USING btree (id);
CREATE INDEX ix_projects_user_id ON public.projects USING btree (user_id);
CREATE INDEX ix_projects_last_opened_at ON public.projects USING btree (last_opened_at);

-- ==================== subscriptions ====================
CREATE TABLE IF NOT EXISTS subscriptions (
    id integer DEFAULT nextval('subscriptions_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    plan_type character varying(50) NOT NULL,
    status character varying(50),
    start_date timestamp without time zone,
    end_date timestamp without time zone,
    stripe_subscription_id character varying(255),
    amount double precision
);
CREATE UNIQUE INDEX subscriptions_pkey ON public.subscriptions USING btree (id);
CREATE INDEX ix_subscriptions_id ON public.subscriptions USING btree (id);

-- ==================== support_messages ====================
CREATE TABLE IF NOT EXISTS support_messages (
    id integer DEFAULT nextval('support_messages_id_seq'::regclass) NOT NULL,
    email character varying(255) NOT NULL,
    name character varying(255),
    message text NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    is_read boolean DEFAULT false
);
CREATE UNIQUE INDEX support_messages_pkey ON public.support_messages USING btree (id);
CREATE INDEX ix_support_messages_id ON public.support_messages USING btree (id);

-- ==================== users ====================
CREATE TABLE IF NOT EXISTS users (
    id integer DEFAULT nextval('users_id_seq'::regclass) NOT NULL,
    email character varying(255) NOT NULL,
    username character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    full_name character varying(255),
    is_admin boolean,
    is_active boolean,
    subscription_type character varying(50),
    subscription_end timestamp without time zone,
    created_at timestamp without time zone,
    last_login timestamp without time zone,
    analysis_count integer,
    storage_used double precision,
    phone character varying(50),
    country character varying(100),
    gender character varying(20),
    specialty character varying(100),
    specialty_other character varying(255),
    trial_start timestamp without time zone DEFAULT now(),
    trial_end timestamp without time zone,
    session_token character varying(128),
    session_expires timestamp without time zone,
    last_dataset_id integer,
    assistant_mode character varying(16) DEFAULT 'simple'::character varying
);
CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id);
CREATE UNIQUE INDEX users_username_key ON public.users USING btree (username);
CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);
CREATE INDEX ix_users_id ON public.users USING btree (id);
CREATE INDEX ix_users_session_token ON public.users USING btree (session_token);
