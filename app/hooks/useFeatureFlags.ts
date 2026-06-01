/**
 * React Hook for School Feature Flags
 *
 * Fetches feature flags for the current user's school.
 * Super admins (no school_id) get all features enabled by default.
 *
 * Usage:
 * ```tsx
 * const { featureFlags, hasFeature, loading } = useFeatureFlags();
 *
 * if (hasFeature('billing')) {
 *   // Show billing tab
 * }
 * ```
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { getSchoolFeatures } from '@/services/schoolApi';
import { DEFAULT_FEATURE_FLAGS, type FeatureFlags } from '@lib/types';

// All-true flags for super admins
const ALL_ENABLED_FLAGS: FeatureFlags = Object.fromEntries(
  Object.keys(DEFAULT_FEATURE_FLAGS).map(k => [k, true])
) as FeatureFlags;

export function useFeatureFlags() {
  const { getAccessToken, isSuperAdmin, adminSchoolId } = useAuth();
  const [featureFlags, setFeatureFlags] = useState<FeatureFlags>(
    isSuperAdmin ? ALL_ENABLED_FLAGS : DEFAULT_FEATURE_FLAGS
  );
  const [loading, setLoading] = useState(!isSuperAdmin && !!adminSchoolId);
  const fetchedRef = useRef(false);
  const getTokenRef = useRef(getAccessToken);
  getTokenRef.current = getAccessToken;

  useEffect(() => {
    // Super admin: all features enabled, no API call needed
    if (isSuperAdmin) {
      setFeatureFlags(ALL_ENABLED_FLAGS);
      setLoading(false);
      return;
    }

    // No school ID: use defaults
    if (!adminSchoolId) {
      setFeatureFlags(DEFAULT_FEATURE_FLAGS);
      setLoading(false);
      return;
    }

    // Already fetched
    if (fetchedRef.current) return;

    let cancelled = false;

    const fetchFlags = async () => {
      try {
        const token = getTokenRef.current();
        const flags = await getSchoolFeatures(adminSchoolId, token);
        if (!cancelled) {
          setFeatureFlags({ ...DEFAULT_FEATURE_FLAGS, ...flags } as FeatureFlags);
          fetchedRef.current = true;
        }
      } catch (err) {
        console.error('useFeatureFlags: failed to fetch', err);
        // Fall back to defaults on error
        if (!cancelled) setFeatureFlags(DEFAULT_FEATURE_FLAGS);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchFlags();
    return () => { cancelled = true; };
  }, [isSuperAdmin, adminSchoolId]);

  const hasFeature = useCallback(
    (key: string): boolean => {
      return featureFlags[key] ?? false;
    },
    [featureFlags]
  );

  return { featureFlags, hasFeature, loading };
}
