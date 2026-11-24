
import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Menu,
  MessageSquareText,
} from "lucide-react";

import ChatPanel from "../components/ChatPanel";
import CustomerNotificationCenter from "../components/CustomerNotificationCenter";
import Sidebar from "../components/Sidebar";
import AccountSettings from "../components/AccountSettings";

import {
  sendChatMessage,
  getCustomerTickets,
  getCustomerTicketMessages,
  deleteCustomerTicket,
} from "../services/api";

export default function CustomerChat({
  customerToken,
  onLogout,
  initialTicketId = null,
  onNavigate = () => {},
}) {
  // ==========================================
  // 01. CHAT STATE
  // ==========================================

  const [messages, setMessages] = useState([]);
  const [accountSettingsOpen, setAccountSettingsOpen] =
    useState(false);
  const [ticketId, setTicketId] = useState(null);
  const [ticketStatus, setTicketStatus] = useState("open");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ==========================================
  // 02. CONVERSATION HISTORY STATE
  // ==========================================

  const [tickets, setTickets] = useState([]);
  const [historyLoading, setHistoryLoading] =
    useState(false);

  const [historyError, setHistoryError] = useState("");
  const [deletingTicketId, setDeletingTicketId] = useState(null);
  const [pendingDeleteTicketId, setPendingDeleteTicketId] = useState(null);
  const [conversationLoading, setConversationLoading] =
    useState(false);

  // Track conversation selection to prevent stale responses
  const conversationVersion = useRef(0);
  const historyRequestVersion = useRef(0);
  const sendingRef = useRef(false);

  // ==========================================
  // 03. SIDEBAR STATE
  // ==========================================

  const [sidebarCollapsed, setSidebarCollapsed] =
    useState(false);

  const [mobileSidebarOpen, setMobileSidebarOpen] =
    useState(false);

  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 800px)").matches
  );

  // Detect screen size changes
  useEffect(() => {
    const mediaQuery = window.matchMedia(
      "(max-width: 800px)"
    );

    function handleScreenChange(event) {
      setIsMobile(event.matches);
      setMobileSidebarOpen(false);
    }

    setIsMobile(mediaQuery.matches);

    mediaQuery.addEventListener(
      "change",
      handleScreenChange
    );

    return () => {
      mediaQuery.removeEventListener(
        "change",
        handleScreenChange
      );
    };
  }, []);

  // Close mobile sidebar using Escape
  useEffect(() => {
    if (!mobileSidebarOpen) return;

    function handleEscape(event) {
      if (event.key === "Escape") {
        setMobileSidebarOpen(false);
      }
    }

    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener(
        "keydown",
        handleEscape
      );
    };
  }, [mobileSidebarOpen]);

  // Prevent background scroll when mobile sidebar opens
  useEffect(() => {
    if (!isMobile || !mobileSidebarOpen) return;

    const previousOverflow =
      document.body.style.overflow;

    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow =
        previousOverflow;
    };
  }, [isMobile, mobileSidebarOpen]);

  // ==========================================
  // 04. FETCH CUSTOMER TICKETS
  // ==========================================

  const loadTickets = useCallback(async () => {
    const requestVersion = ++historyRequestVersion.current;

    setHistoryLoading(true);
    setHistoryError("");

    try {
      const result = await getCustomerTickets(customerToken);

      if (requestVersion !== historyRequestVersion.current) {
        return;
      }

      setTickets(Array.isArray(result) ? result : []);
    } catch (err) {
      if (requestVersion !== historyRequestVersion.current) {
        return;
      }

      setHistoryError(
        err.message || "Unable to load conversations."
      );
    } finally {
      if (requestVersion === historyRequestVersion.current) {
        setHistoryLoading(false);
      }
    }
  }, [customerToken]);

  // Load conversations when customer logs in
  useEffect(() => {
    loadTickets();

    return () => {
      historyRequestVersion.current += 1;
      conversationVersion.current += 1;
    };
  }, [loadTickets]);

  // ==========================================
  // 05. OPEN AN EXISTING CONVERSATION
  // ==========================================

  async function handleSelectTicket(selectedTicketId) {
    if (sendingRef.current || conversationLoading) {
      return;
    }

    const version = ++conversationVersion.current;

    setConversationLoading(true);
    setError("");
    setMobileSidebarOpen(false);

    try {
      const result = await getCustomerTicketMessages(
        customerToken,
        selectedTicketId
      );

      if (version !== conversationVersion.current) {
        return;
      }

      setTicketId(result.ticket_id);
      setTicketStatus(result.status);
      onNavigate(result.ticket_id);

      setMessages(
        Array.isArray(result.messages)
          ? result.messages
          : []
      );
    } catch (err) {
      if (version === conversationVersion.current) {
        setError(
          err.message ||
            "Unable to load conversation."
        );
      }
    } finally {
      if (version === conversationVersion.current) {
        setConversationLoading(false);
      }
    }
  }

  // ==========================================
  // CUSTOMER TICKET STATUS POLLING
  // ==========================================

  useEffect(() => {
    if (
      !customerToken ||
      !ticketId ||
      ticketStatus !== "pending_approval"
    ) {
      return;
    }

    let cancelled = false;
    let requestInFlight = false;

    async function checkTicketStatus() {
      if (
        cancelled ||
        requestInFlight ||
        sendingRef.current ||
        document.visibilityState !== "visible"
      ) {
        return;
      }

      requestInFlight = true;

      try {
        const result = await getCustomerTicketMessages(
          customerToken,
          ticketId
        );

        if (cancelled || !result) return;

        if (
          result.ticket_id !== ticketId ||
          !result.status
        ) {
          return;
        }

        if (result.status !== "pending_approval") {
          setTicketStatus(result.status);

          // Keep the sidebar status in sync.
          await loadTickets();
        }
      } catch {
        // Preserve the existing conversation if a
        // background request temporarily fails.
      } finally {
        requestInFlight = false;
      }
    }

    const interval = window.setInterval(
      checkTicketStatus,
      15000
    );

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        checkTicketStatus();
      }
    }

    document.addEventListener(
      "visibilitychange",
      handleVisibilityChange
    );

    return () => {
      cancelled = true;
      window.clearInterval(interval);

      document.removeEventListener(
        "visibilitychange",
        handleVisibilityChange
      );
    };
  }, [
    customerToken,
    ticketId,
    ticketStatus,
    loadTickets,
  ]);

  // ==========================================
  // 06. SEND CHAT MESSAGE
  // ==========================================

  async function handleSend(text) {
    if (
      sendingRef.current ||
      loading ||
      conversationLoading ||
      ticketStatus !== "open"
    ) {
      throw new Error("Conversation is not ready.");
    }

    sendingRef.current = true;
    setLoading(true);
    setError("");

    const version = conversationVersion.current;

    try {
      const result = await sendChatMessage(
        customerToken,
        text,
        ticketId
      );

      if (version !== conversationVersion.current) {
        return;
      }

      setMessages((previous) => [
        ...previous,
        {
          role: "user",
          content: text,
        },
        {
          role: "assistant",
          content: result.reply,
        },
      ]);

      setTicketId(result.ticket_id);
      setTicketStatus(result.status);
      onNavigate(result.ticket_id);

      // Refresh sidebar after a successful chat request
      await loadTickets();
    } catch (err) {
      if (version === conversationVersion.current) {
        setError(
          err.message ||
            "Unable to send message. Please try again."
        );
      }

      throw err;
    } finally {
      sendingRef.current = false;
      setLoading(false);
    }
  }

  // ==========================================
  // 07. START NEW CONVERSATION
  // ==========================================

  function handleNewConversation() {
    if (sendingRef.current || conversationLoading) {
      return;
    }

    conversationVersion.current += 1;

    setMessages([]);
    setTicketId(null);
    setTicketStatus("open");
    setError("");
    setMobileSidebarOpen(false);
    onNavigate(null);
  }

  useEffect(() => {
    if (conversationLoading) return;
    if (!initialTicketId) {
      if (ticketId !== null) {
        conversationVersion.current += 1;
        setTicketId(null);
        setTicketStatus("open");
        setMessages([]);
        setError("");
      }
      return;
    }
    if (Number(ticketId) !== Number(initialTicketId)) {
      handleSelectTicket(initialTicketId);
    }
  }, [initialTicketId, ticketId, conversationLoading]);

  // Remove from customer history, not permanent data erasure.
  function handleDeleteTicket(selectedTicketId) {
    if (
      sendingRef.current ||
      loading ||
      conversationLoading ||
      deletingTicketId !== null ||
      pendingDeleteTicketId !== null
    ) {
      return;
    }

    setHistoryError("");
    setPendingDeleteTicketId(selectedTicketId);
  }

  async function confirmDeleteTicket() {
    const selectedTicketId = pendingDeleteTicketId;

    if (
      selectedTicketId === null ||
      deletingTicketId !== null ||
      sendingRef.current ||
      loading ||
      conversationLoading
    ) {
      return;
    }

    setDeletingTicketId(selectedTicketId);
    setHistoryError("");

    try {
      await deleteCustomerTicket(customerToken, selectedTicketId);

      historyRequestVersion.current += 1;
      setHistoryLoading(false);

      setTickets((previous) =>
        previous.filter(
          (ticket) => Number(ticket.id) !== Number(selectedTicketId)
        )
      );

      if (Number(ticketId) === Number(selectedTicketId)) {
        conversationVersion.current += 1;
        setConversationLoading(false);
        setMessages([]);
        setTicketId(null);
        setTicketStatus("open");
        setError("");
      }

      setPendingDeleteTicketId(null);
      setMobileSidebarOpen(false);
    } catch (err) {
      setHistoryError(
        err.message || "Unable to remove conversation."
      );
    } finally {
      setDeletingTicketId(null);
    }
  }

  function handleDeleteModalKeyDown(event) {
    if (deletingTicketId !== null) return;

    if (event.key === "Escape") {
      event.preventDefault();
      setPendingDeleteTicketId(null);
      return;
    }

    if (event.key === "Tab") {
      const buttons = Array.from(
        event.currentTarget.querySelectorAll(
          "button:not([disabled])"
        )
      );

      if (!buttons.length) return;

      const first = buttons[0];
      const last = buttons[buttons.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        document.activeElement === last
      ) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  // ==========================================
  // 08. SIDEBAR CONTROLS
  // ==========================================

  function handleSidebarToggle() {
    if (isMobile) {
      setMobileSidebarOpen(false);
    } else {
      setSidebarCollapsed((previous) => !previous);
    }
  }

  function handleLogout() {
    setMobileSidebarOpen(false);
    onLogout();
  }

  const shellClass = [
    "shell",
    sidebarCollapsed ? "sidebar-collapsed" : "",
    mobileSidebarOpen ? "mobile-sidebar-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // ==========================================
  // 09. CUSTOMER DASHBOARD UI
  // ==========================================

  return (
    <div className={shellClass}>
      {/* Mobile navigation overlay */}
      {mobileSidebarOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Close navigation menu"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Sidebar with previous conversations */}
      <Sidebar
        tickets={tickets}
        activeTicketId={ticketId}
        onSelectTicket={handleSelectTicket}
        onDeleteTicket={handleDeleteTicket}
        onNewConversation={handleNewConversation}
        onLogout={handleLogout}
        onAccountSettings={() => setAccountSettingsOpen(true)}
        onRefresh={loadTickets}
        loading={loading || conversationLoading || deletingTicketId !== null}
        historyLoading={historyLoading}
        historyError={historyError}
        collapsed={sidebarCollapsed}
        isMobile={isMobile}
        onToggle={handleSidebarToggle}
      />

      {/* Custom confirmation modal */}
      {pendingDeleteTicketId !== null && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            background: "rgba(12, 12, 16, 0.66)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="remove-chat-title"
            aria-describedby="remove-chat-description"
            onKeyDown={handleDeleteModalKeyDown}
            style={{
              width: "100%",
              maxWidth: 440,
              maxHeight: "calc(100dvh - 32px)",
              overflowY: "auto",
              borderRadius: 20,
              padding: "28px",
              background: "#fffdfb",
              color: "#252326",
              boxShadow: "0 24px 80px rgba(0, 0, 0, 0.24)",
              border: "1px solid #eae4dd",
              boxSizing: "border-box",
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                display: "grid",
                placeItems: "center",
                background: "#f8eae7",
                color: "#a04437",
                fontSize: 23,
                marginBottom: 18,
              }}
              aria-hidden="true"
            >
              &#128465;
            </div>

            <h2
              id="remove-chat-title"
              style={{
                margin: "0 0 10px",
                fontSize: 23,
                fontWeight: 700,
                color: "#252326",
              }}
            >
              Remove conversation?
            </h2>

            <p
              id="remove-chat-description"
              style={{
                margin: 0,
                fontSize: 14,
                lineHeight: 1.7,
                color: "#69636a",
              }}
            >
              Conversation #{pendingDeleteTicketId} will disappear
              from your history. Support and audit records may
              still be retained.
            </p>

            <div
              style={{
                marginTop: 18,
                padding: 14,
                background: "#f7f1ea",
                border: "1px solid #e9dfd3",
                borderRadius: 12,
                fontSize: 13,
                lineHeight: 1.6,
                color: "#776453",
              }}
            >
              This removes the conversation from your account
              history. It is not permanent data erasure.
            </div>

            {historyError && (
              <p
                role="alert"
                style={{
                  color: "#aa332c",
                  fontSize: 13,
                  marginBottom: 0,
                }}
              >
                {historyError}
              </p>
            )}

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                justifyContent: "flex-end",
                gap: 10,
                marginTop: 24,
              }}
            >
              <button
                type="button"
                autoFocus
                disabled={deletingTicketId !== null}
                onClick={() => setPendingDeleteTicketId(null)}
                style={{
                  padding: "12px 20px",
                  borderRadius: 10,
                  background: "#fff",
                  border: "1px solid #ded7d1",
                  color: "#252326",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                disabled={deletingTicketId !== null}
                onClick={confirmDeleteTicket}
                style={{
                  padding: "12px 20px",
                  borderRadius: 10,
                  background: "#a64436",
                  color: "#fff",
                  border: "none",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {deletingTicketId !== null
                  ? "Removing..."
                  : "Remove"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="customer-main">
        {/* Dashboard header */}
        <header className="dashboard-header">
          <div className="dashboard-header-left">
            {isMobile && (
              <button
                type="button"
                className="sidebar-toggle"
                onClick={() => setMobileSidebarOpen(true)}
                aria-label="Open sidebar"
                aria-expanded={mobileSidebarOpen}
                aria-controls="customer-sidebar"
              >
                <Menu size={21} />
              </button>
            )}

            <div className="dashboard-heading">
              <span className="eyebrow">
                CUSTOMER SUPPORT
              </span>

              <h1>Support Assistant</h1>

              <p>
                Get help with orders, refunds,
                cancellations and deliveries.
              </p>
            </div>
          </div>

          <div
            className="customer-header-actions"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
              gap: 10,
              flexWrap: "nowrap",
              minWidth: 0,
            }}
          >
            <div className="status" style={{ whiteSpace: "nowrap" }}>
              <i />
              AI Assistant
            </div>

            <CustomerNotificationCenter
              customerToken={customerToken}
              onOpenTicket={handleSelectTicket}
            />

            <AccountSettings
              customerToken={customerToken}
              onDeactivated={onLogout}
              open={accountSettingsOpen}
              setOpen={setAccountSettingsOpen}
            />
          </div>
        </header>

        {/* Loading conversation feedback */}
        {conversationLoading && (
          <div className="chat-loading" role="status">
            Loading conversation...
          </div>
        )}

        {/* Chat messages and composer */}
        <ChatPanel
          key={ticketId ?? "new-conversation"}
          messages={messages}
          onSend={handleSend}
          loading={loading || conversationLoading}
          ticketId={ticketId}
          ticketStatus={ticketStatus}
        />

        {/* API feedback */}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {/* Footer */}
        <div className="customer-chat-footer">
          <MessageSquareText size={16} />

          <span>
            Conversations are associated with your
            authenticated customer account.
          </span>
        </div>
      </main>
    </div>
  );
}
