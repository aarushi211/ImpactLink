// src/context/AuthContext.js
import { createContext, useContext, useState, useEffect, useCallback } from "react";
import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  GoogleAuthProvider,
  signInWithPopup
} from "firebase/auth";
import { auth } from "../firebase"; // Import the auth instance you created earlier
import api from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null); // Firebase Identity
  const [profile, setProfile] = useState(null);         // Backend NGO Profile
  const [loading, setLoading] = useState(true);

  // Firebase automatically manages the session state
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      setCurrentUser(user);
      if (user) {
        try {
          // Get a fresh token from Firebase
          const token = await user.getIdToken();

          // Pass the token explicitly in the header for this call
          const { data } = await api.get(`/api/profile/me`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          setProfile(data);
        } catch (err) {
          console.error("Failed to fetch NGO profile", err);
          // If it's a 401, it means the user exists in Firebase but not in your DB
        }
      } else {
        setProfile(null);
      }
      setLoading(false);
    });
    return unsubscribe;
  }, []);
  const login = useCallback(async (email, password) => {
    // 1. Authenticate with Firebase
    await signInWithEmailAndPassword(auth, email, password);

    // 2. Fetch the corresponding profile from your backend
    const { data } = await api.get(`/api/profile/me`);
    setProfile(data);
    return data;
  }, []);

  const register = useCallback(async (email, password, org_name) => {
    // 1. Create the secure account in Firebase
    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    const user = userCredential.user;

    // 2. Tell your backend to create a database entry for this new NGO
    const { data } = await api.post("/api/auth/register", {
      uid: user.uid, // Pass the Firebase ID so the backend uses it as the primary key
      email,
      org_name
    });

    setProfile(data.profile);
    return data.profile;
  }, []);

  const loginWithGoogle = useCallback(async () => {
    const provider = new GoogleAuthProvider();
    const userCredential = await signInWithPopup(auth, provider);
    const user = userCredential.user;

    try {
      // 1. Check if they already have an ImpactLink profile
      const { data } = await api.get(`/api/profile/me`);
      setProfile(data);
      // Return a flag so the UI knows they are an existing user
      return { profile: data, isNewUser: false };
    } catch (err) {
      // 2. If the backend says 404, register them automatically.
      if (err.response && err.response.status === 404) {
        const defaultOrgName = user.displayName || "My Organization";

        const { data } = await api.post("/api/auth/register", {
          uid: user.uid,
          email: user.email,
          org_name: defaultOrgName
        });

        setProfile(data.profile);
        // Return a flag so the UI knows to ask for Step 2 details
        return { profile: data.profile, isNewUser: true };
      }
      throw err;
    }
  }, []);

  const updateProfile = useCallback(async (updates) => {
    // FIX: Rely on Firebase's instantaneous session, not React's delayed state
    const user = auth.currentUser;
    if (!user) return;

    const { data } = await api.patch("/api/profile", {
      updates
    });
    setProfile(data);
    return data;
  }, []); // We can remove 'profile' from the dependency array now

  const logout = useCallback(async () => {
    await signOut(auth);
    setProfile(null);
  }, []);

  // FIX 1: This is where loginWithGoogle belongs
  return (
    <AuthContext.Provider value={{
      currentUser, profile, loading,
      login, register, logout, updateProfile, loginWithGoogle
    }}>
      {!loading && children}
    </AuthContext.Provider>
  );
}

// FIX 2: This should purely read the context, not provide it
export function useAuth() {
  return useContext(AuthContext);
}