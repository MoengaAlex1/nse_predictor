/// <reference types="vite/client" />
import { getDatabase } from "firebase/database";
import { app } from "./firebase";

export const rtdb = getDatabase(app, import.meta.env.VITE_FIREBASE_DATABASE_URL);
