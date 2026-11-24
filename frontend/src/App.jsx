
import React, { useEffect, useState } from "react";

import Login from "./pages/Login";
import Register from "./pages/Register";
import VerifyEmail from "./pages/VerifyEmail";
import CustomerChat from "./pages/CustomerChat";
import AdminDashboard from "./pages/AdminDashboard";

import {
  loginCustomer,
  getCustomerVerificationStatus,
} from "./services/api";


function captureVerificationLink() {
  if (window.location.pathname !== "/verify-email") {
    return { isVerificationPage: false, token: null };
  }

  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");

  // Remove token from address bar/history immediately.
  window.history.replaceState(null, "", "/");

  return {
    isVerificationPage: true,
    token,
  };
}


const SESSION_KEY = "supportflow_customer_session_v1";
const SESSION_MAX_AGE_MS = 30 * 60 * 1000;

function saveCustomerSession(token) {
  try {
    sessionStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ token, createdAt: Date.now() })
    );
  } catch {
    // Private browsing can block browser storage.
  }
}

function clearCustomerSession() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // Storage may be unavailable.
  }
}

function readCustomerSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;

    const session = JSON.parse(raw);

    if (
      typeof session.token !== "string" ||
      !session.token ||
      !Number.isFinite(session.createdAt) ||
      session.createdAt > Date.now() ||
      Date.now() - session.createdAt >= SESSION_MAX_AGE_MS
    ) {
      clearCustomerSession();
      return null;
    }

    return session.token;
  } catch {
    clearCustomerSession();
    return null;
  }
}

const initialVerificationLink = captureVerificationLink();

function routeFromLocation() {
  const path = window.location.pathname;
  const chat = path.match(/^\/chat\/(\d+)$/);
  if (chat) return { page: "chat", ticketId: Number(chat[1]) };
  if (path === "/admin" || path === "/admin/dashboard") return { page: "admin", section: "overview" };
  if (path.startsWith("/admin/")) {
    const section = path.slice("/admin/".length);
    const allowed = {
      customers: "customers", tickets: "tickets", administrators: "staff",
      approvals: "approvals", approved: "approved", rejected: "rejected",
    };
    return { page: "admin", section: allowed[section] || "overview" };
  }
  return { page: "chat", ticketId: null };
}

export default function App() {
  // ==========================================
  // 01. APPLICATION STATE
  // ==========================================

  const initialRoute = routeFromLocation();
  const [route, setRoute] = useState(initialRoute);
  const [checkingSession, setCheckingSession] = useState(
    !initialVerificationLink.isVerificationPage && initialRoute.page === "chat"
  );
  const page = initialVerificationLink.isVerificationPage
    ? "verify-email"
    : checkingSession
      ? "checking-session"
      : route.page;
  const [customerToken, setCustomerToken] = useState(null);

  useEffect(() => {
    const onPopState = () => setRoute(routeFromLocation());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (initialVerificationLink.isVerificationPage || initialRoute.page === "admin") {
      setCheckingSession(false);
      return;
    }

    let cancelled = false;

    async function restoreSession() {
      const token = readCustomerSession();

      if (!token) {
        if (!cancelled) {
          setCheckingSession(false);
          setRoute({ page: "login" });
        }
        return;
      }

      try {
        const status = await getCustomerVerificationStatus(token);

        if (cancelled) return;

        if (status?.email_verified === true) {
          setCustomerToken(token);
          setCheckingSession(false);
          setRoute(routeFromLocation());
        } else {
          clearCustomerSession();
          setCheckingSession(false);
          setRoute({ page: "login" });
        }
      } catch {
        if (!cancelled) {
          clearCustomerSession();
          setCheckingSession(false);
          setRoute({ page: "login" });
        }
      }
    }

    restoreSession();

    return () => {
      cancelled = true;
    };
  }, []);

  // ==========================================
  // 02. CUSTOMER AUTHENTICATION
  // ==========================================

  function handleLogin(token) {
    saveCustomerSession(token);
    setCustomerToken(token);
    setCheckingSession(false);
    window.history.pushState(null, "", "/");
    setRoute({ page: "chat", ticketId: null });
  }

  async function handleRegisterLogin(credentials) {
    const result = await loginCustomer(credentials);

    if (!result.access_token) {
      throw new Error(
        "Authentication token was not returned."
      );
    }

    handleLogin(result.access_token);
  }

  function handleCustomerLogout() {
    clearCustomerSession();
    setCustomerToken(null);
    setCheckingSession(false);
    setRoute({ page: "login" });
  }

  // ==========================================
  // 03. ADMIN NAVIGATION
  // ==========================================

  function openAdminPortal() {
    window.history.pushState(null, "", "/admin");
    setRoute({ page: "admin", section: "overview" });
  }

  function closeAdminPortal() {
    window.history.replaceState(null, "", "/");
    setRoute({ page: "login" });
  }

  // ==========================================
  // 04. APPLICATION ROUTING
  // ==========================================

  if (page === "checking-session") {
    return (
      <div className="auth-page">
        <div className="auth-card" role="status">
          Checking your session...
        </div>
      </div>
    );
  }

  if (page === "verify-email") {
    return (
      <VerifyEmail
        token={initialVerificationLink.token}
        onSignIn={() => setRoute({ page: "login" })}
      />
    );
  }

  if (page === "login") {
    return (
      <>
        <Login
          onLogin={handleLogin}
          onRegister={() => setRoute({ page: "register" })}
        />

        {/* JWT admin portal is accessible from /admin in deployed builds. */}
        {(import.meta.env.DEV || import.meta.env.VITE_ADMIN_AUTH_MODE === "jwt") && (
          <button
            type="button"
            className="dev-admin-link"
            onClick={openAdminPortal}
          >
            Admin Access
          </button>
        )}
      </>
    );
  }

  if (page === "register") {
    return (
      <Register
        onLogin={handleRegisterLogin}
        onSignIn={() => setRoute({ page: "login" })}
      />
    );
  }

  if (page === "chat" && customerToken) {
    return (
      <CustomerChat
        customerToken={customerToken}
        onLogout={handleCustomerLogout}
        initialTicketId={route.ticketId}
        onNavigate={(ticketId) => {
          const path = ticketId ? `/chat/${ticketId}` : "/";
          if (window.location.pathname !== path) {
            window.history.pushState(null, "", path);
          }
          setRoute({ page: "chat", ticketId: ticketId || null });
        }}
      />
    );
  }

  if (page === "admin" && (import.meta.env.DEV || import.meta.env.VITE_ADMIN_AUTH_MODE === "jwt")) {
    return (
      <AdminDashboard
        onExit={closeAdminPortal}
        initialSection={route.section}
        onNavigate={(section) => {
          const path = section === "overview" ? "/admin" : `/admin/${section === "staff" ? "administrators" : section}`;
          if (window.location.pathname !== path) {
            window.history.pushState(null, "", path);
          }
          setRoute({ page: "admin", section });
        }}
      />
    );
  }

  return null;
}
