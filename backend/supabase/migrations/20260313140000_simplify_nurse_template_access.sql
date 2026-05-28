-- Simplify nurse template access: remove access_level gating
-- All nurse_templates entries are now 'use' access; is_active is a soft-delete flag

-- Set all nurse_templates to access_level='use' and is_active=true
UPDATE nurse_templates SET access_level = 'use', is_active = true WHERE access_level = 'view';

-- Soft-delete nurse_templates whose parent template is soft-deleted
UPDATE nurse_templates nt SET is_active = false
FROM templates t
WHERE nt.template_id = t.id AND t.is_active = false;
