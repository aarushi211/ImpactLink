import { createContext, useContext, useState, useEffect, useCallback } from "react";
import api from "../services/api";

/**
 * AuthContext — global NGO auth state
 *
 * profile  — full NGO profile object or null
 * loading  — true during initial hydration
 * login()  — calls /api/auth/login, stores in sessionStorage
 * register() — calls /api/auth/register
 * logout() — clears state
 * updateProfile() — calls PATCH /api/profile, updates state
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  // Hydrate from sessionStorage on mount
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("ngo_profile");
      if (stored) setProfile(JSON.parse(stored));
    } catch (_) {}
    setLoading(false);
  }, []);

  const _persist = (p) => {
    setProfile(p);
    sessionStorage.setItem("ngo_profile", JSON.stringify(p));
  };

  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/api/auth/login", { email, password });
    _persist(data.profile);
    return data.profile;
  }, []);

  const register = useCallback(async (email, password, org_name) => {
    const { data } = await api.post("/api/auth/register", { email, password, org_name });
    _persist(data.profile);
    return data.profile;
  }, []);

  const logout = useCallback(() => {
    setProfile(null);
    sessionStorage.removeItem("ngo_profile");
  }, []);

  const updateProfile = useCallback(async (updates) => {
    if (!profile) return;
    const { data } = await api.patch("/api/profile", { ngo_id: profile.id, updates });
    _persist(data);
    return data;
  }, [profile]);

  return (
    <AuthContext.Provider value={{ profile, loading, login, register, logout, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}