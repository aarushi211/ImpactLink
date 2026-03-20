// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth"
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyA69k2YafZv2CH3qjAaPmKufgyzcl0a6Wc",
    authDomain: "impactlink-710f2.firebaseapp.com",
    projectId: "impactlink-710f2",
    storageBucket: "impactlink-710f2.firebasestorage.app",
    messagingSenderId: "440329721233",
    appId: "1:440329721233:web:ad2ed90bba1247bfdff630"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);