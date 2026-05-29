-- Add hospital_id to admin_users for hospital-scoped admin logins
-- NULL = global/super_admin access, Non-NULL = restricted to this hospital

ALTER TABLE admin_users
ADD COLUMN hospital_id uuid REFERENCES hospitals(id) ON DELETE SET NULL;

CREATE INDEX idx_admin_users_hospital_id ON admin_users(hospital_id)
WHERE hospital_id IS NOT NULL;

COMMENT ON COLUMN admin_users.hospital_id IS
  'Hospital scope. NULL = global/super_admin access. Non-NULL = restricted to this hospital.';
