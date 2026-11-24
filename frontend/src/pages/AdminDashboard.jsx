
import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Headphones,
  LayoutDashboard,
  Users,
  Ticket,
  Clock3,
  CheckCircle2,
  XCircle,
  MessageSquareText,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
  X,
  LockKeyhole,
  Eye,
  EyeOff,
  Search,
  CalendarDays,
  SlidersHorizontal,
  RotateCcw,
  ChevronRight,
} from "lucide-react";

import TicketTable from "../components/TicketTable";
import AdminNotificationCenter from "../components/AdminNotificationCenter";
import AdminCustomers from "../components/AdminCustomers";
import AdminManagement from "../components/AdminManagement";

import {
  getTickets,
  getTicketMessages,
  decideTicket,
  loginAdmin,
  getAdminProfile,
  logoutAdmin,
} from "../services/api";

// Admin JWTs expire after 15 minutes. Keep an authenticated session through
// page refresh in this tab, but never persist the password or use localStorage.
const ADMIN_SESSION_KEY = "supportflow_admin_session_v1";

function adminTokenExpiry(token) {
  try {
    const payloadPart = token.split(".")[1];
    if (!payloadPart) return 0;
    const base64 = payloadPart.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "=")));
    return payload.type === "admin_access" && Number.isFinite(payload.exp)
      ? payload.exp * 1000
      : 0;
  } catch {
    return 0;
  }
}

function clearAdminSession() {
  try { window.sessionStorage.removeItem(ADMIN_SESSION_KEY); } catch { /* storage blocked */ }
}

function readAdminSession() {
  try {
    const token = window.sessionStorage.getItem(ADMIN_SESSION_KEY);
    if (token && adminTokenExpiry(token) > Date.now()) return token;
  } catch { /* storage blocked */ }
  clearAdminSession();
  return null;
}

function saveAdminSession(token) {
  try { window.sessionStorage.setItem(ADMIN_SESSION_KEY, token); } catch { /* storage blocked */ }
}

// ==========================================
// HELPERS
// ==========================================

function formatStatus(status) {
  return (status || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

// Backend's now() writes UTC. Convert ticket timestamps to
// Asia/Karachi for display AND all date/time comparisons.
// PostgreSQL may return a timezone-naive ISO value; the UTC
// default in our backend makes interpreting that as UTC appropriate.
const KARACHI_TIMEZONE = "Asia/Karachi";

function parseTicketTimestamp(value) {
  if (!value || typeof value !== "string") return null;
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
    ? value
    : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function karachiParts(value) {
  const date = parseTicketTimestamp(value);
  if (!date) return null;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: KARACHI_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const field = (name) => parts.find((item) => item.type === name)?.value;
  return {
    date: `${field("year")}-${field("month")}-${field("day")}`,
    time: `${field("hour")}:${field("minute")}`,
  };
}

function karachiToday() {
  return karachiParts(new Date().toISOString()).date;
}

function dayNumber(ymd) {
  const [y, m, d] = ymd.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 86400000;
}

export default function AdminDashboard({ onExit, initialSection = "overview", onNavigate = () => {} }) {
  // ==========================================
  // 01. AUTHENTICATION
  // ==========================================

  const jwtMode = import.meta.env.VITE_ADMIN_AUTH_MODE === "jwt";
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [adminTokenInput, setAdminTokenInput] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [adminProfile, setAdminProfile] = useState(null);
  const [checkingAdminSession, setCheckingAdminSession] = useState(jwtMode);
  const [showAdminToken, setShowAdminToken] = useState(false);

  // ==========================================
  // 02. DASHBOARD STATE
  // ==========================================

  const [tickets, setTickets] = useState([]);
  const [selectedTicketId, setSelectedTicketId] =
    useState(null);

  const [messages, setMessages] = useState([]);

  const [loading, setLoading] = useState(false);
  const [messagesLoading, setMessagesLoading] =
    useState(false);
  const [decisionLoading, setDecisionLoading] =
    useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [decisionNote, setDecisionNote] = useState("");
  const [pendingDecision, setPendingDecision] = useState(null);
  const confirmationRef = useRef(null);
  const cancelConfirmationRef = useRef(null);
  const confirmationTriggerRef = useRef(null);
  const decisionBusyRef = useRef(false);


  // ==========================================
  // 03. NAVIGATION STATE
  // ==========================================

  // The URL-derived section is authoritative. Local state here previously
  // competed with popstate updates and could reset repeated Back/Forward
  // navigation to overview.
  const activePage = initialSection || "overview";
  const [search, setSearch] = useState("");
  const [datePreset, setDatePreset] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [timeFrom, setTimeFrom] = useState("");
  const [timeTo, setTimeTo] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [sidebarCollapsed, setSidebarCollapsed] =
    useState(false);

  const [mobileSidebarOpen, setMobileSidebarOpen] =
    useState(false);

  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 800px)").matches
  );

  const mainRef = useRef(null);
  const messageRequestId = useRef(0);
  const ticketRequestId = useRef(0);
  const tokenRef = useRef("");

  // Restore only a still-valid JWT; the backend remains authoritative.
  useEffect(() => {
    if (!jwtMode) return;
    const token = readAdminSession();
    if (!token) {
      setCheckingAdminSession(false);
      return;
    }
    let cancelled = false;
    async function restore() {
      try {
        const profile = await getAdminProfile(token);
        const result = await getTickets(token);
        if (cancelled) return;
        if (adminTokenExpiry(token) <= Date.now()) throw new Error("Expired admin session");
        tokenRef.current = token;
        setAdminProfile(profile);
        setAdminToken(token);
        setTickets(Array.isArray(result) ? result : []);
      } catch {
        if (!cancelled) clearAdminSession();
      } finally {
        if (!cancelled) setCheckingAdminSession(false);
      }
    }
    restore();
    return () => { cancelled = true; };
  }, [jwtMode]);

  // Expire the session at the actual JWT expiry time (never extend it client-side).
  useEffect(() => {
    if (!jwtMode || !adminToken) return;
    const expiresIn = adminTokenExpiry(adminToken) - Date.now();
    if (expiresIn <= 0) {
      clearAdminSession();
      tokenRef.current = "";
      setAdminToken("");
      setAdminProfile(null);
      return;
    }
    const timer = window.setTimeout(() => {
      clearAdminSession();
      tokenRef.current = "";
      setAdminToken("");
      setAdminProfile(null);
      setTickets([]);
    }, Math.min(expiresIn, 2147483647));
    return () => window.clearTimeout(timer);
  }, [jwtMode, adminToken]);

  // ==========================================
  // 04. RESPONSIVE SIDEBAR
  // ==========================================

  useEffect(() => {
    const media = window.matchMedia("(max-width: 800px)");

    function handleChange(event) {
      setIsMobile(event.matches);
      setMobileSidebarOpen(false);
    }

    setIsMobile(media.matches);
    media.addEventListener("change", handleChange);

    return () => {
      media.removeEventListener("change", handleChange);
    };
  }, []);

  useEffect(() => {
    if (!mobileSidebarOpen) return;

    function closeOnEscape(event) {
      if (event.key === "Escape") {
        setMobileSidebarOpen(false);
      }
    }

    document.addEventListener("keydown", closeOnEscape);

    return () => {
      document.removeEventListener(
        "keydown",
        closeOnEscape
      );
    };
  }, [mobileSidebarOpen]);

  useEffect(() => {
    if (!isMobile || !mobileSidebarOpen) return;

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previous;
    };
  }, [isMobile, mobileSidebarOpen]);

  // ==========================================
  // 05. FETCH TICKETS
  // ==========================================

  const loadTickets = useCallback(async (token) => {
    if (!token) return;

    const requestId = ++ticketRequestId.current;

    setLoading(true);
    setError("");

    try {
      const result = await getTickets(token);

      if (
        requestId !== ticketRequestId.current ||
        tokenRef.current !== token
      ) {
        return;
      }

      setTickets(Array.isArray(result) ? result : []);
    } catch (err) {
      if (requestId === ticketRequestId.current) {
        setError(
          err.message || "Unable to load support tickets."
        );
      }
    } finally {
      if (requestId === ticketRequestId.current) {
        setLoading(false);
      }
    }
  }, []);

  function handleRefresh() {
    if (adminToken && !decisionLoading) {
      loadTickets(adminToken);
    }
  }

  // ==========================================
  // 06. ADMIN LOGIN
  // ==========================================

  async function handleAdminLogin(event) {
    event.preventDefault();

    if (loading) return;
    if (jwtMode ? (!adminEmail.trim() || !adminPassword) : !adminTokenInput.trim()) {
      return;
    }

    setLoading(true);
    setError("");

    try {
      let token;
      let profile = null;
      if (jwtMode) {
        const session = await loginAdmin(adminEmail.trim(), adminPassword);
        token = session?.access_token;
        if (!token) throw new Error("Admin session was not returned.");
        profile = await getAdminProfile(token);
      } else {
        token = adminTokenInput.trim();
      }
      const result = await getTickets(token);

      tokenRef.current = token;
      if (jwtMode) {
        saveAdminSession(token);
        setAdminProfile(profile);
      }
      setAdminToken(token);
      setTickets(Array.isArray(result) ? result : []);
      setAdminTokenInput("");
      setAdminPassword("");
      setShowAdminToken(false);
      onNavigate("overview");
    } catch (err) {
      setAdminPassword("");
      setError(err.message || "Administrator authorization failed.");
    } finally {
      setLoading(false);
    }
  }

  function handleAdminLogout() {
    const tokenToRevoke = tokenRef.current;
    // Clear the browser session immediately; logout revokes all server JWTs.
    if (jwtMode && tokenToRevoke) {
      logoutAdmin(tokenToRevoke).catch(() => {
        // The local token is discarded even if the network is offline.
      });
    }
    clearAdminSession();
    setAdminProfile(null);
    tokenRef.current = "";
    ticketRequestId.current += 1;
    messageRequestId.current += 1;

    setAdminToken("");
    setAdminTokenInput("");
    setAdminEmail("");
    setAdminPassword("");
    setShowAdminToken(false);
    setTickets([]);
    setSelectedTicketId(null);
    setMessages([]);
    setDecisionNote("");
    setError("");
    setSuccess("");
    setLoading(false);
    setMessagesLoading(false);
    setDecisionLoading(false);
    setMobileSidebarOpen(false);
    onNavigate("overview");
    setSearch("");
    setDatePreset("all");
    setDateFrom("");
    setDateTo("");
    setTimeFrom("");
    setTimeTo("");
    setStatusFilter("all");
  }

  // ==========================================
  // 07. NAVIGATION
  // ==========================================

  function navigateTo(page) {
    // Each section starts clean; no ticket details leak between tabs.
    messageRequestId.current += 1;
    setSelectedTicketId(null);
    setMessages([]);
    setMessagesLoading(false);
    setDecisionNote("");
    onNavigate(page);
    setMobileSidebarOpen(false);
    setSearch("");
    setDatePreset("all");
    setDateFrom("");
    setDateTo("");
    setTimeFrom("");
    setTimeTo("");
    setStatusFilter("all");
    setError("");
    setSuccess("");

    if (mainRef.current) {
      mainRef.current.scrollTop = 0;
    }
  }

  function toggleSidebar() {
    if (isMobile) {
      setMobileSidebarOpen(false);
    } else {
      setSidebarCollapsed((previous) => !previous);
    }
  }

  // ==========================================
  // 08. SELECT TICKET
  // ==========================================

  async function handleSelectTicket(id) {
    if (
      !adminToken ||
      messagesLoading ||
      decisionLoading
    ) {
      return;
    }

    const requestId = ++messageRequestId.current;

    // Overview is a summary page. Its View action opens All Tickets.
    if (activePage === "overview") {
      navigateTo("tickets");
      setSearch("");
    }

    setSelectedTicketId(id);
    setMessages([]);
    setMessagesLoading(true);
    setDecisionNote("");
    setError("");
    setSuccess("");

    try {
      const result = await getTicketMessages(
        adminToken,
        id
      );

      if (requestId !== messageRequestId.current) {
        return;
      }

      const records = Array.isArray(result)
        ? result
        : result?.messages;

      setMessages(
        Array.isArray(records) ? records : []
      );
    } catch (err) {
      if (requestId === messageRequestId.current) {
        setError(
          err.message || "Unable to load conversation."
        );
      }
    } finally {
      if (requestId === messageRequestId.current) {
        setMessagesLoading(false);
      }
    }
  }

  // ==========================================
  // 09. APPROVAL DECISIONS
  // ==========================================

  // Open a branded confirmation dialog without executing a decision.
  function handleDecision(approve) {
    const selectedTicket = tickets.find(
      (ticket) => ticket.id === selectedTicketId
    );

    if (
      !adminToken ||
      !selectedTicket ||
      selectedTicket.status !== "pending_approval" ||
      decisionLoading ||
      decisionBusyRef.current ||
      messagesLoading
    ) {
      return;
    }

    confirmationTriggerRef.current = document.activeElement;

    setPendingDecision({
      ticketId: selectedTicket.id,
      approve,
    });
  }

  // Keep keyboard focus inside the confirmation dialog.
  useEffect(() => {
    if (!pendingDecision) return;

    cancelConfirmationRef.current?.focus();

    function handleConfirmationKeydown(event) {
      if (event.key === "Escape") {
        event.preventDefault();

        if (!decisionBusyRef.current) {
          setPendingDecision(null);
        }
        return;
      }

      if (event.key !== "Tab") return;

      const dialog = confirmationRef.current;
      if (!dialog) return;

      const buttons = Array.from(
        dialog.querySelectorAll("button:not(:disabled)")
      );

      if (buttons.length === 0) {
        event.preventDefault();
        return;
      }

      const first = buttons[0];
      const last = buttons[buttons.length - 1];

      if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleConfirmationKeydown);

    return () => {
      document.removeEventListener(
        "keydown",
        handleConfirmationKeydown
      );

      const trigger = confirmationTriggerRef.current;

      if (trigger?.isConnected) {
        trigger.focus();
      }
    };
  }, [pendingDecision]);

  // Execute only after explicit confirmation.
  async function confirmDecision() {
    if (
      !pendingDecision ||
      decisionBusyRef.current ||
      decisionLoading ||
      !adminToken
    ) {
      return;
    }

    const { ticketId, approve } = pendingDecision;

    const selectedTicket = tickets.find(
      (ticket) => ticket.id === ticketId
    );

    if (
      !selectedTicket ||
      selectedTicket.status !== "pending_approval" ||
      selectedTicketId !== ticketId
    ) {
      setPendingDecision(null);
      setError("Ticket selection changed. Please review again.");
      return;
    }

    decisionBusyRef.current = true;
    setDecisionLoading(true);
    setError("");
    setSuccess("");

    try {
      const result = await decideTicket(
        adminToken,
        ticketId,
        approve,
        decisionNote.trim()
      );

      const newStatus =
        result?.status || (approve ? "approved" : "rejected");

      setTickets((previous) =>
        previous.map((ticket) =>
          ticket.id === ticketId
            ? { ...ticket, status: newStatus }
            : ticket
        )
      );

      setSuccess(
        `Ticket #${ticketId} marked as ` +
        `${formatStatus(newStatus)}. ` +
        "No refund or cancellation was executed."
      );

      setDecisionNote("");
      setPendingDecision(null);
      navigateTo(approve ? "approved" : "rejected");
      await loadTickets(adminToken);
    } catch (err) {
      setError(
        err.message || "Unable to record decision."
      );
      setPendingDecision(null);
    } finally {
      decisionBusyRef.current = false;
      setDecisionLoading(false);
    }
  }

  // ==========================================
  // 10. DASHBOARD DATA
  // ==========================================

  const totalTickets = tickets.length;

  const pendingTickets = tickets.filter(
    (ticket) => ticket.status === "pending_approval"
  ).length;

  const approvedTickets = tickets.filter(
    (ticket) => ticket.status === "approved"
  ).length;

  const rejectedTickets = tickets.filter(
    (ticket) => ticket.status === "rejected"
  ).length;

  const selectedTicket = tickets.find(
    (ticket) => ticket.id === selectedTicketId
  );

  const todayInKarachi = karachiToday();
  const hasDateFilter = datePreset !== "all";
  const hasTimeFilter = Boolean(timeFrom || timeTo);
  const invalidCustomRange =
    datePreset === "custom" &&
    Boolean(dateFrom && dateTo && dateFrom > dateTo);

  function resetFilters() {
    setSearch("");
    setStatusFilter("all");
    setDatePreset("all");
    setDateFrom("");
    setDateTo("");
    setTimeFrom("");
    setTimeTo("");
  }

  const filteredTickets = tickets.filter((ticket) => {
    const statusByPage = {
      approvals: "pending_approval",
      approved: "approved",
      rejected: "rejected",
    };
    const requiredStatus = statusByPage[activePage];
    if (requiredStatus && ticket.status !== requiredStatus) return false;
    if (
      activePage === "tickets" &&
      statusFilter !== "all" &&
      ticket.status !== statusFilter
    ) return false;

    const term = search.trim().toLowerCase();
    if (term) {
      const searchable = [
        ticket.id,
        ticket.customer_id,
        ticket.summary,
        ticket.intent,
        ticket.status,
        ticket.order_id,
      ];
      if (!searchable.some((value) =>
        String(value ?? "").toLowerCase().includes(term)
      )) return false;
    }

    // Overview intentionally stays a lightweight recent-tickets list.
    if (activePage === "overview") return true;

    if (!hasDateFilter && !hasTimeFilter) return true;
    const local = karachiParts(ticket.created_at);
    if (!local || invalidCustomRange) return false;

    if (datePreset === "today" && local.date !== todayInKarachi) return false;
    if (datePreset === "7days" || datePreset === "30days") {
      const days = dayNumber(todayInKarachi) - dayNumber(local.date);
      const limit = datePreset === "7days" ? 7 : 30;
      if (days < 0 || days >= limit) return false;
    }
    if (datePreset === "custom") {
      if (dateFrom && local.date < dateFrom) return false;
      if (dateTo && local.date > dateTo) return false;
    }
    if (timeFrom && timeTo && timeFrom > timeTo) {
      // An overnight interval, e.g. 22:00 through 06:00.
      if (local.time < timeFrom && local.time > timeTo) return false;
    } else {
      if (timeFrom && local.time < timeFrom) return false;
      if (timeTo && local.time > timeTo) return false;
    }
    return true;
  });

  const metrics = [
    {
      label: "Total Tickets",
      value: totalTickets,
      icon: Ticket,
    },
    {
      label: "Pending Approval",
      value: pendingTickets,
      icon: Clock3,
    },
    {
      label: "Approved",
      value: approvedTickets,
      icon: CheckCircle2,
    },
    {
      label: "Rejected",
      value: rejectedTickets,
      icon: XCircle,
    },
  ];

  // ==========================================
  // 11. AUTHENTICATION SCREEN
  // ==========================================

  if (checkingAdminSession) {
    return <div className="auth-page"><div className="auth-card" role="status">Checking administrator session...</div></div>;
  }

  if (adminToken && activePage === "staff" && adminProfile?.role !== "super_admin") {
    return (
      <div className="auth-page">
        <div className="auth-card" role="alert">
          Access denied. Administrator management is restricted to Super Admins.
        </div>
      </div>
    );
  }

  if (!adminToken) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-brand">
            <Headphones size={24} />

            <h2>
              SupportFlow <span>AI</span>
            </h2>
          </div>

          <div className="auth-heading">
            <h1>Admin Access</h1>
            <p>
              {jwtMode
                ? "Sign in with your administrator email and password."
                : "Enter your administrator token to access the support management dashboard."}
            </p>
          </div>

          <form
            className="auth-form"
            onSubmit={handleAdminLogin}
          >
            {jwtMode && (
              <>
                <label htmlFor="admin-email">Administrator Email</label>
                <div className="auth-input">
                  <input
                    id="admin-email"
                    type="email"
                    value={adminEmail}
                    onChange={(event) => setAdminEmail(event.target.value)}
                    placeholder="admin@example.com"
                    autoComplete="username"
                    required
                  />
                </div>
              </>
            )}

            <label htmlFor="admin-token">
              {jwtMode ? "Administrator Password" : "Administrator Token"}
            </label>

            <div className="auth-input">
              <LockKeyhole size={18} />

              <input
                id="admin-token"
                type={showAdminToken ? "text" : "password"}
                value={jwtMode ? adminPassword : adminTokenInput}
                onChange={(event) => jwtMode
                  ? setAdminPassword(event.target.value)
                  : setAdminTokenInput(event.target.value)
                }
                placeholder={jwtMode ? "Enter admin password" : "Enter admin token"}
                autoComplete={jwtMode ? "current-password" : "off"}
                spellCheck={false}
                required
              />

              <button
                type="button"
                className="password-toggle"
                onClick={() =>
                  setShowAdminToken((previous) => !previous)
                }
                aria-label={
                  showAdminToken
                    ? "Hide administrator token"
                    : "Show administrator token"
                }
              >
                {showAdminToken ? (
                  <EyeOff size={18} />
                ) : (
                  <Eye size={18} />
                )}
              </button>
            </div>

            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="auth-submit"
              disabled={loading}
            >
              <ShieldCheck size={18} />
              {loading
                ? "Verifying..."
                : "Access Dashboard"}
            </button>
          </form>

          <p className="auth-footer">
            {jwtMode ? "Protected administrator portal" : "Development administration interface"}
          </p>

          {onExit && (
            <button
              type="button"
              className="textbutton"
              onClick={onExit}
            >
              Return to customer login
            </button>
          )}
        </div>
      </div>
    );
  }

  // ==========================================
  // 12. DASHBOARD INTERFACE
  // ==========================================

  const layoutClass = [
    "admin-layout",
    sidebarCollapsed ? "admin-sidebar-collapsed" : "",
    mobileSidebarOpen ? "admin-mobile-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={layoutClass}>

      {/* MOBILE SIDEBAR OVERLAY */}
      {mobileSidebarOpen && (
        <button
          type="button"
          className="admin-sidebar-overlay"
          aria-label="Close admin navigation"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* SIDEBAR */}
      <aside className="admin-sidebar">
        <div className="admin-sidebar-top">
          <div className="admin-brand">
            <div className="admin-brand-icon">
              <Headphones size={21} />
            </div>

            <div className="admin-sidebar-label">
              <strong>
                SupportFlow <span>AI</span>
              </strong>
              <small>ADMIN PORTAL</small>
            </div>
          </div>

          <button
            type="button"
            className="admin-collapse-button"
            onClick={toggleSidebar}
            title="Toggle sidebar"
            aria-label="Toggle admin sidebar"
          >
            {isMobile ? (
              <X size={19} />
            ) : sidebarCollapsed ? (
              <PanelLeftOpen size={19} />
            ) : (
              <PanelLeftClose size={19} />
            )}
          </button>
        </div>

        <div className="admin-sidebar-menu">
          <span className="admin-sidebar-section admin-sidebar-label">
            WORKSPACE
          </span>

          <button
            type="button"
            className={
              activePage === "overview" ? "active" : ""
            }
            onClick={() => navigateTo("overview")}
            title="Overview"
          >
            <LayoutDashboard size={19} />
            <span className="admin-sidebar-label">
              Overview
            </span>
          </button>

          <button
            type="button"
            className={
              activePage === "tickets" ? "active" : ""
            }
            onClick={() => navigateTo("tickets")}
            title="All Tickets"
          >
            <Ticket size={19} />
            <span className="admin-sidebar-label">
              All Tickets
            </span>
            <span className="admin-nav-count admin-sidebar-label">
              {totalTickets}
            </span>
          </button>

          <button
            type="button"
            className={activePage === "customers" ? "active" : ""}
            onClick={() => navigateTo("customers")}
            title="Customers"
          >
            <Users size={19} />
            <span className="admin-sidebar-label">
              Customers
            </span>
          </button>

          {jwtMode && adminProfile?.role === "super_admin" && (
            <button type="button" className={activePage === "staff" ? "active" : ""}
              onClick={() => navigateTo("staff")} title="Manage Administrators">
              <Users size={19} />
              <span className="admin-sidebar-label">Administrators</span>
            </button>
          )}

          <button
            type="button"
            className={
              activePage === "approvals" ? "active" : ""
            }
            onClick={() => navigateTo("approvals")}
            title="Pending Approvals"
          >
            <ShieldAlert size={19} />
            <span className="admin-sidebar-label">
              Pending Approvals
            </span>
            <span className="admin-nav-count admin-sidebar-label">
              {pendingTickets}
            </span>
          </button>

          <button
            type="button"
            className={activePage === "approved" ? "active" : ""}
            onClick={() => navigateTo("approved")}
            title="Approved Tickets"
          >
            <CheckCircle2 size={19} />
            <span className="admin-sidebar-label">Approved</span>
            <span className="admin-nav-count admin-sidebar-label">
              {approvedTickets}
            </span>
          </button>

          <button
            type="button"
            className={activePage === "rejected" ? "active" : ""}
            onClick={() => navigateTo("rejected")}
            title="Rejected Tickets"
          >
            <XCircle size={19} />
            <span className="admin-sidebar-label">Rejected</span>
            <span className="admin-nav-count admin-sidebar-label">
              {rejectedTickets}
            </span>
          </button>
        </div>

        <div className="admin-sidebar-bottom">
          <div className="admin-session">
            <ShieldCheck size={18} />
            <span className="admin-sidebar-label">
              {adminProfile?.role === "super_admin" ? "Super administrator" : "Authorized admin session"}
            </span>
          </div>

          <button
            type="button"
            className="admin-signout"
            onClick={handleAdminLogout}
            title="Sign Out"
          >
            <LogOut size={18} />
            <span className="admin-sidebar-label">
              Sign Out
            </span>
          </button>
        </div>
      </aside>

      {/* MAIN AREA */}
      <div className="admin-main" ref={mainRef}>

        {/* TOP HEADER */}
        <header className="admin-topbar">
          <div className="admin-topbar-left">
            {isMobile && (
              <button
                type="button"
                className="admin-mobile-menu"
                onClick={() => setMobileSidebarOpen(true)}
                aria-label="Open admin navigation"
              >
                <Menu size={21} />
              </button>
            )}

            <div>
              <span className="eyebrow">SUPPORTFLOW AI / ADMIN WORKSPACE</span>
            </div>
          </div>

          <div className="admin-topbar-actions">
            <span className="admin-online-indicator">
              <span />
              {adminProfile?.role === "super_admin" ? "Super Admin" : "Admin Session"}
            </span>

            <AdminNotificationCenter
              adminToken={adminToken}
              onOpenTicket={(id) => {
                navigateTo("tickets");
                handleSelectTicket(id);
              }}
            />

            <button
              type="button"
              className="admin-refresh-button"
              onClick={handleRefresh}
              disabled={loading || decisionLoading}
            >
              <RefreshCw
                size={17}
                className={loading ? "loading-icon" : ""}
              />
              <span>Refresh</span>
            </button>
          </div>
        </header>

        {/* MAIN CONTENT */}
        <div className="admin-content">

          {/* PAGE INTRO */}
          <div className="admin-page-intro">
            <div>
              <span className="eyebrow">
                CUSTOMER SUPPORT MANAGEMENT
              </span>
              <h1 className="admin-section-title">
                {activePage === "approvals"
                  ? "Review Requests"
                  : activePage === "approved"
                    ? "Approved Requests"
                    : activePage === "rejected"
                      ? "Rejected Requests"
                      : activePage === "tickets"
                        ? "Ticket Management"
                        : activePage === "customers"
                          ? "Customer Directory"
                          : activePage === "staff"
                            ? "Administrator Management"
                            : "Support Overview"}
              </h1>
              <p>
                {activePage === "approvals"
                  ? "Review tickets waiting for a human decision."
                  : activePage === "approved" || activePage === "rejected"
                    ? "Read-only history of completed review decisions."
                    : activePage === "customers"
                      ? "Browse registered customers and account status."
                      : activePage === "staff"
                        ? "Manage normal administrators and review their work."
                        : "Monitor customer conversations and support activity."}
              </p>
            </div>

            <div className="admin-page-indicator">
              <ShieldCheck size={17} />
              Internal Workspace
            </div>
          </div>

          {activePage === "customers" && (
            <AdminCustomers adminToken={adminToken} isSuperAdmin={adminProfile?.role === "super_admin"} />
          )}
          {activePage === "staff" && adminProfile?.role === "super_admin" && (
            <AdminManagement adminToken={adminToken} />
          )}

          {activePage !== "customers" && activePage !== "staff" && (
            <>
          {/* OVERVIEW CARDS */}
          {activePage === "overview" && (
            <div className="admin-stats">
              {metrics.map((metric) => {
                const IconComponent = metric.icon;

                return (
                  <div
                    className="admin-stat-card"
                    key={metric.label}
                  >
                    <div className="admin-stat-top">
                      <span>{metric.label}</span>
                      <div className="admin-stat-icon">
                        <IconComponent size={20} />
                      </div>
                    </div>

                    <strong>{metric.value}</strong>
                    <small>
                      {metric.label === "Total Tickets"
                        ? "Customer conversations"
                        : "Support requests"}
                    </small>
                  </div>
                );
              })}
            </div>
          )}

          {/* FEEDBACK */}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}

          {success && (
            <div className="auth-success" role="status">
              {success}
            </div>
          )}

          {/* TICKET LIST */}
          <section className="admin-tickets-section">
            <div className="admin-section-top">
              <div>
                <h2>
                  <Ticket size={20} />
                  {activePage === "approvals"
                    ? "Awaiting Human Review"
                    : activePage === "approved"
                      ? "Approved Tickets"
                      : activePage === "rejected"
                        ? "Rejected Tickets"
                        : activePage === "overview"
                          ? "Recent Support Tickets"
                          : "Support Tickets"}
                </h2>
                <p>
                  {activePage === "overview"
                    ? `${Math.min(filteredTickets.length, 5)} most recent conversations`
                    : `${filteredTickets.length} tickets displayed`}
                </p>
              </div>

              <label className="admin-ticket-search">
                <Search size={17} />

                <input
                  type="search"
                  placeholder="Search tickets..."
                  aria-label="Search tickets"
                  value={search}
                  onChange={(event) =>
                    setSearch(event.target.value)
                  }
                />
              </label>
            </div>

            {activePage !== "overview" && (
              <div className="admin-filter-panel">
                <div className="admin-filter-title">
                  <span><SlidersHorizontal size={17} /> Advanced Filters</span>
                  <small>Dates and times use Pakistan Standard Time (PKT)</small>
                </div>
                <div className="admin-filter-grid">
                  <label className="admin-filter-field">
                    <span><CalendarDays size={14} /> Date Range</span>
                    <select
                      value={datePreset}
                      onChange={(event) => setDatePreset(event.target.value)}
                    >
                      <option value="all">All Time</option>
                      <option value="today">Today</option>
                      <option value="7days">Last 7 Days</option>
                      <option value="30days">Last 30 Days</option>
                      <option value="custom">Custom Range</option>
                    </select>
                  </label>
                  {activePage === "tickets" && (
                    <label className="admin-filter-field">
                      <span>Ticket Status</span>
                      <select
                        value={statusFilter}
                        onChange={(event) => setStatusFilter(event.target.value)}
                      >
                        <option value="all">All Statuses</option>
                        <option value="open">Open</option>
                        <option value="pending_approval">Pending Approval</option>
                        <option value="approved">Approved</option>
                        <option value="rejected">Rejected</option>
                      </select>
                    </label>
                  )}
                  <label className="admin-filter-field">
                    <span>From Time (PKT)</span>
                    <input
                      type="time"
                      value={timeFrom}
                      onChange={(event) => setTimeFrom(event.target.value)}
                    />
                  </label>
                  <label className="admin-filter-field">
                    <span>To Time (PKT)</span>
                    <input
                      type="time"
                      value={timeTo}
                      onChange={(event) => setTimeTo(event.target.value)}
                    />
                  </label>
                  {datePreset === "custom" && (
                    <>
                      <label className="admin-filter-field">
                        <span>From Date</span>
                        <input
                          type="date"
                          value={dateFrom}
                          max={dateTo || undefined}
                          onChange={(event) => setDateFrom(event.target.value)}
                        />
                      </label>
                      <label className="admin-filter-field">
                        <span>To Date</span>
                        <input
                          type="date"
                          value={dateTo}
                          min={dateFrom || undefined}
                          onChange={(event) => setDateTo(event.target.value)}
                        />
                      </label>
                    </>
                  )}
                </div>
                <div className="admin-filter-footer">
                  <span>
                    {invalidCustomRange
                      ? "Start date cannot be later than end date."
                      : `${filteredTickets.length} matching ticket(s) · PKT (UTC+05:00)`}
                  </span>
                  <button type="button" onClick={resetFilters}>
                    <RotateCcw size={15} /> Reset Filters
                  </button>
                </div>
              </div>
            )}

            <TicketTable
              tickets={activePage === "overview"
                ? filteredTickets.slice(0, 5)
                : filteredTickets}
              selectedTicketId={selectedTicketId}
              onSelectTicket={handleSelectTicket}
              loading={loading}
            />
          </section>

          {/* SELECTED TICKET */}
          {activePage !== "overview" &&
            selectedTicket &&
            filteredTickets.some((ticket) => ticket.id === selectedTicketId) && (
            <section className="admin-ticket-details">

              <div className="admin-ticket-details-header">
                <div>
                  <span className="eyebrow">
                    TICKET DETAILS
                  </span>
                  <h2>
                    Ticket #{selectedTicket.id}
                  </h2>

                  <p>
                    {selectedTicket.summary ||
                      "Customer support request"}
                  </p>
                </div>

                <span
                  className={`pill ${selectedTicket.status || ""}`}
                >
                  {formatStatus(selectedTicket.status)}
                </span>
              </div>

              <div className="admin-ticket-meta">
                <div>
                  <small>CUSTOMER</small>
                  <strong>
                    Customer #{selectedTicket.customer_id}
                  </strong>
                </div>

                <div>
                  <small>REQUEST TYPE</small>
                  <strong>
                    {formatStatus(selectedTicket.intent)}
                  </strong>
                </div>

                <div>
                  <small>ORDER REFERENCE</small>
                  <strong>
                    {selectedTicket.order_id || "Not provided"}
                  </strong>
                </div>
              </div>

              <div className="admin-section-heading">
                <MessageSquareText size={19} />
                <h3>Conversation History</h3>
              </div>

              <div className="admin-ticket-messages">
                {messagesLoading ? (
                  <div className="admin-messages-empty">
                    Loading conversation...
                  </div>
                ) : messages.length === 0 ? (
                  <div className="admin-messages-empty">
                    No messages available.
                  </div>
                ) : (
                  messages.map((message, index) => (
                    <div
                      key={message.id ?? index}
                      className={`admin-message ${
                        message.role === "user"
                          ? "user"
                          : "assistant"
                      }`}
                    >
                      <strong>
                        {message.role === "user"
                          ? "CUSTOMER"
                          : "SUPPORTFLOW AI"}
                      </strong>

                      <p>{message.content}</p>
                    </div>
                  ))
                )}
              </div>

              {/* APPROVAL PANEL */}
              {selectedTicket.status ===
                "pending_approval" && (
                <div className="admin-approval">

                  <div className="admin-section-heading">
                    <ShieldAlert size={20} />
                    <h3>Human Approval Required</h3>
                  </div>

                  <p>
                    Review the customer request and
                    conversation before making a decision.
                  </p>

                  <label htmlFor="decision-note">
                    Decision Note (Optional)
                  </label>

                  <textarea
                    id="decision-note"
                    rows={3}
                    maxLength={500}
                    value={decisionNote}
                    onChange={(event) =>
                      setDecisionNote(event.target.value)
                    }
                    placeholder="Add an internal note..."
                  />

                  <div className="admin-approval-actions">
                    <button
                      type="button"
                      onClick={() => handleDecision(true)}
                      disabled={
                        decisionLoading || messagesLoading
                      }
                    >
                      <CheckCircle2 size={18} />
                      Approve
                    </button>

                    <button
                      type="button"
                      onClick={() => handleDecision(false)}
                      disabled={
                        decisionLoading || messagesLoading
                      }
                    >
                      <XCircle size={18} />
                      Reject
                    </button>
                  </div>

                  <p className="admin-approval-disclaimer">
                    A decision is recorded only.
                    Refunds and cancellations are not
                    automatically executed.
                  </p>
                </div>
              )}
            </section>
          )}

          {/* EMPTY SELECTION */}
          {activePage !== "overview" &&
            !selectedTicket &&
            !loading &&
            filteredTickets.length > 0 && (
            <div className="admin-select-hint">
              <MessageSquareText size={20} />
              <span>
                Select <strong>View</strong> on a ticket
                to inspect its conversation.
              </span>
              <ChevronRight size={16} />
            </div>
          )}

                  </>
          )}

</div>

        {/* FOOTER */}
        <footer className="admin-footer">
          <span>
            © {new Date().getFullYear()} SupportFlow AI
          </span>
          <span>
            Admin Workspace · Development Environment
          </span>
        </footer>

      </div>

      {/* CUSTOM HUMAN APPROVAL CONFIRMATION */}
      {pendingDecision && (
        <div
          className="admin-confirm-backdrop"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              !decisionBusyRef.current
            ) {
              setPendingDecision(null);
            }
          }}
        >
          <div
            className="admin-confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-confirm-title"
            aria-describedby="admin-confirm-description"
            ref={confirmationRef}
          >
            <div className="admin-confirm-heading">
              <div className="admin-confirm-icon">
                <ShieldAlert size={24} />
              </div>

              <div>
                <span className="admin-confirm-eyebrow">
                  HUMAN REVIEW
                </span>
                <h2 id="admin-confirm-title">
                  {pendingDecision.approve
                    ? "Approve Support Request?"
                    : "Reject Support Request?"}
                </h2>
              </div>
            </div>

            <div className="admin-confirm-body">
              <div className="admin-confirm-ticket">
                <span>Ticket</span>
                <strong>#{pendingDecision.ticketId}</strong>
              </div>

              <p id="admin-confirm-description">
                {pendingDecision.approve
                  ? "You are about to approve this customer support request."
                  : "You are about to reject this customer support request."}
                {" "}Your decision will be recorded in the ticket history.
              </p>

              <div className="admin-confirm-warning">
                <ShieldCheck size={19} />
                <span>
                  This action records a human review decision only.
                  No refund payment or order cancellation will
                  be executed automatically.
                </span>
              </div>
            </div>

            <div className="admin-confirm-actions">
              <button
                ref={cancelConfirmationRef}
                type="button"
                className="admin-confirm-cancel"
                disabled={decisionLoading}
                onClick={() => setPendingDecision(null)}
              >
                Cancel
              </button>

              <button
                type="button"
                className={
                  pendingDecision.approve
                    ? "admin-confirm-submit"
                    : "admin-confirm-submit admin-confirm-reject"
                }
                disabled={decisionLoading}
                onClick={confirmDecision}
              >
                {decisionLoading
                  ? "Recording Decision..."
                  : pendingDecision.approve
                    ? "Confirm Approval"
                    : "Confirm Rejection"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
