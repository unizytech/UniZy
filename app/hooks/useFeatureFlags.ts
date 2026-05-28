/**
 * React Hook for Hospital Feature Flags
 *
 * Fetches feature flags for the current user's hospital.
 * Super admins (no hospital_id) get all features enabled by default.
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
import { getHospitalFeatures } from '@/services/hospitalApi';
import { DEFAULT_FEATURE_FLAGS, type FeatureFlags } from '@lib/types';

// All-true flags for super admins
const ALL_ENABLED_FLAGS: FeatureFlags = Object.fromEntries(
  Object.keys(DEFAULT_FEATURE_FLAGS).map(k => [k, true])
) as FeatureFlags;

export function useFeatureFlags() {
  const { getAccessToken, isSuperAdmin, adminHospitalId } = useAuth();
  const [featureFlags, setFeatureFlags] = useState<FeatureFlags>(
    isSuperAdmin ? ALL_ENABLED_FLAGS : DEFAULT_FEATURE_FLAGS
  );
  const [loading, setLoading] = useState(!isSuperAdmin && !!adminHospitalId);
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

    // No hospital ID: use defaults
    if (!adminHospitalId) {
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
        const flags = await getHospitalFeatures(adminHospitalId, token);
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
  }, [isSuperAdmin, adminHospitalId]);

  const hasFeature = useCallback(
    (key: string): boolean => {
      return featureFlags[key] ?? false;
    },
    [featureFlags]
  );

  return { featureFlags, hasFeature, loading };
}
