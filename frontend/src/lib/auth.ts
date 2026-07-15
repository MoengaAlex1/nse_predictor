import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  signOut,
  onAuthStateChanged,
  type User,
} from "firebase/auth";
import { doc, setDoc, serverTimestamp } from "firebase/firestore";
import { auth, db } from "./firebase";
import { useAuthStore } from "../store/useAuthStore";

const googleProvider = new GoogleAuthProvider();

export async function loginWithEmail(email: string, password: string): Promise<void> {
  await signInWithEmailAndPassword(auth, email, password);
}

export async function registerWithEmail(email: string, password: string): Promise<void> {
  const cred = await createUserWithEmailAndPassword(auth, email, password);
  await createUserDoc(cred.user);
}

export async function loginWithGoogle(): Promise<void> {
  const cred = await signInWithPopup(auth, googleProvider);
  await createUserDoc(cred.user);
}

export async function logout(): Promise<void> {
  await signOut(auth);
}

async function createUserDoc(user: User): Promise<void> {
  const ref = doc(db, "users", user.uid);
  await setDoc(
    ref,
    { watchlist: [], plan: "free", created_at: serverTimestamp() },
    { merge: true }
  );
}

export function initAuthListener(): () => void {
  return onAuthStateChanged(auth, (user) => {
    useAuthStore.getState().setUser(user);
  });
}
