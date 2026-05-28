'use client';

/**
 * Authentication Context for Supabase Auth
 *
 * Simple auth provider with:
 * - Login/logout
 * - Session management
 * - Admin user lookup
 */

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { supabase } from './supabase';
import type { User, Session } from '@supabase/supabase-js';

export interface AdminUser {
  id: string;
  auth_user_id: string;
  email: string;
  full_name: string | null;
  role: 'super_admin' | 'admin' | 'viewer';
  hospital_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface AuthContextType {
  user: User | null;
  adminUser: AdminUser | null;
  session: Session | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
  getAccessToken: () => string | null;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  isHospitalAdmin: boolean;
  adminHospitalId: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [adminUser, setAdminUser] = useState<AdminUser | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Ref to track current adminUser inside closures without causing re-renders
  const adminUserRef = useRef<AdminUser | null>(null);

  // Fetch admin user details
  const fetchAdminUser = useCallback(async (authUserId: string) => {
    if (!supabase) return null;
    try {
      const { data, error } = await supabase
        .from('admin_users')
        .select('*')
        .eq('auth_user_id', authUserId)
        .eq('is_active', true)
        .single();
      if (error) return null;
      return data as AdminUser;
    } catch {
      return null;
    }
  }, []);

  // Initialize - check for existing session
  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }

    const sb = supabase; // Store reference for TypeScript narrowing
    let mounted = true;

    const init = async () => {
      try {
        const { data: { session } } = await sb.auth.getSession();
        if (!mounted) return;

        if (session?.user) {
          setSession(session);
          setUser(session.user);
          const admin = await fetchAdminUser(session.user.id);
          if (mounted) {
            setAdminUser(admin);
            adminUserRef.current = admin;
          }
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };

    init();

    // Listen for auth changes (for token refresh, etc.)
    const { data: { subscription } } = sb.auth.onAuthStateChange(
      async (event, newSession) => {
        if (!mounted) return;
        console.log('[Auth] State changed:', event);

        if (newSession?.user) {
          setSession(newSession);
          setUser(newSession.user);
          // Use ref to read current admin user without stale closure
          const currentAdmin = adminUserRef.current;
          if (!currentAdmin || currentAdmin.auth_user_id !== newSession.user.id) {
            const admin = await fetchAdminUser(newSession.user.id);
            if (mounted) {
              setAdminUser(admin);
              adminUserRef.current = admin;
            }
          }
        } else if (event === 'SIGNED_OUT') {
          setSession(null);
          setUser(null);
          setAdminUser(null);
          adminUserRef.current = null;
        }
      }
    );

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, [fetchAdminUser]);

  // Periodic session check - proactively refresh tokens to prevent expiry
  // Only logs out if refresh fails completely (e.g., 7+ days inactive)
  useEffect(() => {
    if (!supabase || !session) return;

    const sb = supabase; // Store reference for TypeScript narrowing
    const CHECK_INTERVAL = 10 * 60 * 1000; // Check every 10 minutes

    const checkSession = async () => {
      try {
        // Get current session from Supabase (this also triggers auto-refresh if needed)
        const { data: { session: currentSession }, error } = await sb.auth.getSession();

        // If session is gone completely (refresh token also expired), then logout
        if (error || !currentSession) {
          console.log('[Auth] Session completely invalid (refresh token may have expired)');
          setUser(null);
          setAdminUser(null);
          setSession(null);
          setError('Your session has expired. Please sign in again.');
          return;
        }

        // Check if access token is about to expire (within 5 minutes)
        const expiresAt = currentSession.expires_at;
        if (expiresAt) {
          const now = Math.floor(Date.now() / 1000);
          const timeUntilExpiry = expiresAt - now;

          // Proactively refresh if expiring within 5 minutes
          if (timeUntilExpiry < 300) {
            console.log('[Auth] Access token expiring soon, refreshing...');
            const { data: refreshData, error: refreshError } = await sb.auth.refreshSession();

            if (refreshError) {
              // Refresh failed - this means the refresh token is also invalid
              console.log('[Auth] Token refresh failed:', refreshError.message);
              setUser(null);
              setAdminUser(null);
              setSession(null);
              setError('Your session has expired. Please sign in again.');
            } else if (refreshData.session) {
              console.log('[Auth] Token refreshed successfully');
              setSession(refreshData.session);
            }
          }
        }
      } catch (err) {
        console.error('[Auth] Session check error:', err);
        // Don't logout on network errors - user might be temporarily offline
      }
    };

    // Run check periodically
    const interval = setInterval(checkSession, CHECK_INTERVAL);

    return () => clearInterval(interval);
  }, [session]);

  // Simple sign in
  const signIn = async (email: string, password: string): Promise<{ error: string | null }> => {
    if (!supabase) return { error: 'Not initialized' };

    setLoading(true);
    setError(null);

    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });

      if (error) {
        setError(error.message);
        setLoading(false);
        return { error: error.message };
      }

      if (data.user && data.session) {
        // Set state immediately
        setUser(data.user);
        setSession(data.session);

        // Check admin access
        const admin = await fetchAdminUser(data.user.id);
        if (!admin) {
          await supabase.auth.signOut();
          setUser(null);
          setSession(null);
          adminUserRef.current = null;
          setError('Not authorized as admin');
          setLoading(false);
          return { error: 'Not authorized as admin' };
        }
        setAdminUser(admin);
        adminUserRef.current = admin;
      }

      setLoading(false);
      return { error: null };
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Sign in failed';
      setError(msg);
      setLoading(false);
      return { error: msg };
    }
  };

  // Simple sign out
  const signOut = async () => {
    setUser(null);
    setAdminUser(null);
    adminUserRef.current = null;
    setSession(null);
    setError(null);
    if (supabase) {
      await supabase.auth.signOut().catch(() => {});
    }
  };

  const getAccessToken = useCallback((): string | null => session?.access_token ?? null, [session]);

  return (
    <AuthContext.Provider value={{
      user,
      adminUser,
      session,
      loading,
      error,
      signIn,
      signOut,
      getAccessToken,
      isAdmin: adminUser !== null && adminUser.is_active,
      isSuperAdmin: adminUser?.role === 'super_admin',
      isHospitalAdmin: adminUser !== null && adminUser.is_active && adminUser.hospital_id !== null,
      adminHospitalId: adminUser?.hospital_id ?? null,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}

export function useAuthHeaders(): Record<string, string> {
  const { getAccessToken } = useAuth();
  const token = getAccessToken();
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}
