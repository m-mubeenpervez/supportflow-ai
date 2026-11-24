
import React from "react";

import {
  Headphones,
  Plus,
  LogOut,
  Settings,
  ShieldCheck,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  MessageSquare,
  LoaderCircle,
  RefreshCw,
  Trash2,
} from "lucide-react";

export default function Sidebar({
  tickets = [],
  activeTicketId = null,
  onSelectTicket,
  onDeleteTicket,
  onNewConversation,
  onLogout,
  onAccountSettings,
  onRefresh,
  loading = false,
  historyLoading = false,
  historyError = "",
  collapsed = false,
  isMobile = false,
  onToggle,
}) {
  function getTicketTitle(ticket) {
    const summary = ticket.summary?.trim();

    if (summary) {
      return summary;
    }

    return `Conversation #${ticket.id}`;
  }

  function getTicketStatus(status) {
    return (status || "open")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) =>
        letter.toUpperCase()
      );
  }

  return (
    <aside
      id="customer-sidebar"
      className="sidebar"
      aria-label="Customer navigation"
    >
      {/* =====================================
          01. SIDEBAR HEADER
          ===================================== */}

      <div className="sidebar-top">
        <div className="brand">
          <div className="logo">
            <Headphones size={20} />
          </div>

          <div className="brand-text">
            SupportFlow <span>AI</span>
            <small>CUSTOMER PORTAL</small>
          </div>
        </div>

        <button
          type="button"
          className="sidebar-internal-toggle"
          onClick={onToggle}
          title={
            isMobile
              ? "Close sidebar"
              : collapsed
                ? "Expand sidebar"
                : "Collapse sidebar"
          }
          aria-label={
            isMobile
              ? "Close sidebar"
              : collapsed
                ? "Expand sidebar"
                : "Collapse sidebar"
          }
          aria-controls="customer-sidebar"
        >
          {isMobile ? (
            <X size={19} />
          ) : collapsed ? (
            <PanelLeftOpen size={19} />
          ) : (
            <PanelLeftClose size={19} />
          )}
        </button>
      </div>

      {/* =====================================
          02. NEW CONVERSATION
          ===================================== */}

      <nav className="nav" aria-label="Customer menu">
        <button
          type="button"
          onClick={onNewConversation}
          disabled={loading}
          title="New Conversation"
          aria-label="New Conversation"
        >
          <Plus size={19} />

          <span className="sidebar-label">
            New Conversation
          </span>
        </button>
      </nav>

      {/* =====================================
          03. PREVIOUS CONVERSATIONS
          ===================================== */}

      <section
        className="sidebar-history"
        aria-label="Previous conversations"
      >
        <div className="sidebar-history-heading">
          <span className="sidebar-label">
            RECENT CONVERSATIONS
          </span>

          <button
            type="button"
            className="sidebar-refresh"
            onClick={onRefresh}
            disabled={historyLoading}
            title="Refresh conversations"
            aria-label="Refresh conversations"
          >
            <RefreshCw size={15} />
          </button>
        </div>

        {historyLoading && (
          <div
            className="sidebar-history-feedback"
            role="status"
          >
            <LoaderCircle
              size={15}
              className="loading-icon"
            />

            <span className="sidebar-label">
              Loading conversations...
            </span>
          </div>
        )}

        {!historyLoading && historyError && (
          <div
            className="sidebar-history-error"
            role="alert"
          >
            {historyError}
          </div>
        )}

        {!historyLoading &&
          !historyError &&
          tickets.length === 0 && (
            <div className="sidebar-history-empty">
              <MessageSquare size={17} />

              <span className="sidebar-label">
                No previous conversations
              </span>
            </div>
          )}

        <div className="sidebar-ticket-list">
          {tickets.map((ticket) => {
            const active =
              Number(activeTicketId) === Number(ticket.id);

            return (
              <div
                key={ticket.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  minWidth: 0,
                }}
              >
              <button
                type="button"
                style={{ flex: 1, minWidth: 0 }}
                className={`sidebar-ticket ${
                  active ? "active" : ""
                }`}
                onClick={() => onSelectTicket(ticket.id)}
                disabled={loading}
                title={getTicketTitle(ticket)}
                aria-label={`Open conversation ${ticket.id}: ${getTicketTitle(ticket)}`}
                aria-current={active ? "page" : undefined}
              >
                <MessageSquare size={17} />

                <span className="sidebar-ticket-content sidebar-label">
                  <span className="sidebar-ticket-title">
                    {getTicketTitle(ticket)}
                  </span>

                  <span className="sidebar-ticket-status">
                    Ticket #{ticket.id} ·{" "}
                    {getTicketStatus(ticket.status)}
                  </span>
                </span>
              </button>
              <button
                type="button"
                aria-label={`Remove conversation ${ticket.id}`}
                title="Remove from my history"
                disabled={loading}
                onClick={() => onDeleteTicket(ticket.id)}
                style={{
                  flexShrink: 0,
                  display: "grid",
                  placeItems: "center",
                  width: 32,
                  height: 32,
                  background: "transparent",
                  border: "none",
                  borderRadius: 8,
                  color: "inherit",
                  cursor: loading ? "not-allowed" : "pointer",
                }}
              >
                <Trash2 size={16} />
              </button>
              </div>
            );
          })}
        </div>
      </section>

      {/* =====================================
          04. SIDEBAR FOOTER
          ===================================== */}

      <div className="sidebar-bottom">
        <div
          className="sidefoot"
          title="Secure customer session"
        >
          <ShieldCheck size={18} />

          <span className="sidebar-label">
            Secure customer session
          </span>
        </div>

        <button
          type="button"
          className="sidebar-logout"
          onClick={onAccountSettings}
          title="Account Settings"
          aria-label="Account Settings"
        >
          <Settings size={18} />
          <span className="sidebar-label">
            Account Settings
          </span>
        </button>

        <button
          type="button"
          className="sidebar-logout"
          onClick={onLogout}
          title="Logout"
          aria-label="Logout"
        >
          <LogOut size={18} />

          <span className="sidebar-label">
            Logout
          </span>
        </button>
      </div>
    </aside>
  );
}
