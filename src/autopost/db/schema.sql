CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- single-account service, one row ever
    tiktok_open_id TEXT,
    tiktok_username TEXT,
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expires_at TEXT,
    scopes TEXT,
    linked_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niche TEXT NOT NULL,
    title TEXT NOT NULL,
    dedupe_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'proposed',  -- proposed|used|rejected
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    hook_line TEXT NOT NULL,
    body TEXT NOT NULL,
    cta_line TEXT NOT NULL,
    scene_breakdown_json TEXT NOT NULL,
    estimated_duration_sec REAL,
    policy_check_status TEXT NOT NULL DEFAULT 'pending',  -- pending|pass|fail
    policy_check_notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER NOT NULL REFERENCES scripts(id),
    status TEXT NOT NULL DEFAULT 'draft',
    -- draft|pending_review|approved|rendering|ready_to_post|scheduled|publishing|posted|failed|rejected
    video_path TEXT,
    tts_audio_path TEXT,
    duration_sec REAL,
    caption_text TEXT,
    hashtags TEXT,
    scheduled_for TEXT,
    posted_at TEXT,
    tiktok_publish_id TEXT,
    tiktok_video_id TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id INTEGER NOT NULL REFERENCES content_items(id),
    asset_type TEXT NOT NULL,  -- video_clip|music
    provider TEXT NOT NULL,
    local_path TEXT NOT NULL,
    query_keyword TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posting_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id INTEGER NOT NULL REFERENCES content_items(id),
    tiktok_video_id TEXT,
    publish_id TEXT,
    posted_at TEXT NOT NULL,
    privacy_level TEXT NOT NULL,
    api_response_json TEXT
);

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id INTEGER NOT NULL REFERENCES content_items(id),
    tiktok_video_id TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    raw_json TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rewards_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    followers INTEGER,
    trailing_30d_views INTEGER,
    eligible_video_count INTEGER,
    is_eligible INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS rate_limit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    called_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',  -- running|ok|error
    detail TEXT
);
