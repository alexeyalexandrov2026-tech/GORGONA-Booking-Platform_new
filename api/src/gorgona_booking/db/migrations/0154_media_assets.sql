-- 0154_media_assets.sql
-- Brand media assets backed by Cloudflare R2 (invoker-only, FORCE RLS).

CREATE TABLE gba.media_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('logo', 'cover', 'service_photo', 'gallery')),
    object_key text NOT NULL CHECK (char_length(object_key) BETWEEN 8 AND 300),
    filename text NOT NULL CHECK (char_length(filename) BETWEEN 1 AND 180),
    content_type text NOT NULL CHECK (content_type IN ('image/png', 'image/jpeg', 'image/webp')),
    size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
    sha256 text NOT NULL CHECK (char_length(sha256) = 64),
    storage_backend text NOT NULL CHECK (storage_backend IN ('r2', 'inline')),
    inline_data bytea,
    uploaded_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX media_assets_tenant_kind_idx
    ON gba.media_assets (tenant_id, kind, created_at DESC);

ALTER TABLE gba.media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.media_assets FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS media_assets_tenant_isolation ON gba.media_assets;
CREATE POLICY media_assets_tenant_isolation ON gba.media_assets
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, DELETE ON TABLE gba.media_assets TO gba_runtime;
