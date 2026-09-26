import { initializeApp } from "firebase/app";
import { initializeFirestore, persistentLocalCache } from "firebase/firestore";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const app = initializeApp(firebaseConfig);

// Auto-detect long-polling and persistent cache. Long-polling fixes the
// WebChannel 503/404 retry storm the audit observed on the Home page cold
// load — some Cloudflare Pages POP + Firestore transport pairs never
// complete the streaming handshake and fall through to bare polling that
// TanStack Query interprets as an error. persistentLocalCache keeps the
// last-known state across reloads so users see something instantly.
export const db = initializeFirestore(app, {
  experimentalAutoDetectLongPolling: true,
  localCache: persistentLocalCache(),
});

export const auth = getAuth(app);
