import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Bell,
  Check,
  Inbox,
  X,
} from "lucide-react";

import {
  getAdminNotifications,
  markAdminNotificationRead,
} from "../services/api";

const POLL_INTERVAL_MS = 15000;

export default function AdminNotificationCenter({
  adminToken,
  onOpenTicket,
}) {
  const [notifications, setNotifications] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const containerRef = useRef(null);
  const requestIdRef = useRef(0);
  const fetchBusyRef = useRef(false);
  const readInFlightRef = useRef(new Set());

  const unreadCount = notifications.filter(
    (item) => !item.read_at
  ).length;

  const loadNotifications = useCallback(async () => {
    if (!adminToken || fetchBusyRef.current) return;

    const requestId = ++requestIdRef.current;
    fetchBusyRef.current = true;

    try {
      const result = await getAdminNotifications(adminToken);

      if (requestId !== requestIdRef.current) return;

      setNotifications((previous) => {
        const existing = new Map(
          previous.map((item) => [item.id, item])
        );

        return (Array.isArray(result) ? result : []).map(
          (item) => {
            const saved = existing.get(item.id);

            if (
              !item.read_at &&
              (saved?.read_at ||
                readInFlightRef.current.has(item.id))
            ) {
              return {
                ...item,
                read_at:
                  saved?.read_at || new Date().toISOString(),
              };
            }

            return item;
          }
        );
      });
      setError("");
    } catch {
      if (requestId === requestIdRef.current) {
        setError("Unable to load notifications.");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        fetchBusyRef.current = false;
        setLoading(false);
      }
    }
  }, [adminToken]);

  useEffect(() => {
    if (!adminToken) {
      setNotifications([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    loadNotifications();

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        loadNotifications();
      }
    }, POLL_INTERVAL_MS);

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        loadNotifications();
      }
    }

    document.addEventListener(
      "visibilitychange",
      handleVisibilityChange
    );

    return () => {
      window.clearInterval(interval);
      document.removeEventListener(
        "visibilitychange",
        handleVisibilityChange
      );
      requestIdRef.current += 1;
      fetchBusyRef.current = false;
    };
  }, [adminToken, loadNotifications]);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener(
      "pointerdown",
      handlePointerDown
    );
    document.addEventListener(
      "keydown",
      handleKeyDown
    );

    return () => {
      document.removeEventListener(
        "pointerdown",
        handlePointerDown
      );
      document.removeEventListener(
        "keydown",
        handleKeyDown
      );
    };
  }, [open]);

  async function handleNotificationClick(notification) {
    if (busyId !== null) return;

    setBusyId(notification.id);
    setError("");

    if (!notification.read_at) {
      readInFlightRef.current.add(notification.id);
    }

    try {
      if (!notification.read_at) {
        const updated = await markAdminNotificationRead(
          adminToken,
          notification.id
        );

        setNotifications((previous) =>
          previous.map((item) =>
            item.id === updated.id ? updated : item
          )
        );
      }

      setOpen(false);

      if (typeof onOpenTicket === "function") {
        onOpenTicket(notification.ticket_id);
      }
    } catch {
      setError("Unable to open notification. Please retry.");
    } finally {
      readInFlightRef.current.delete(notification.id);
      setBusyId(null);
    }
  }

  return (
    <div
      className="admin-notification-center"
      ref={containerRef}
    >
      <button
        type="button"
        className="admin-notification-trigger"
        aria-label={
          unreadCount
            ? `${unreadCount} unread notifications`
            : "Notifications"
        }
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((previous) => !previous)}
      >
        <Bell size={19} />

        {unreadCount > 0 && (
          <span className="admin-notification-count">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="admin-notification-panel"
          role="dialog"
          aria-label="Admin notifications"
        >
          <div className="admin-notification-panel-header">
            <div>
              <strong>Notifications</strong>
              <span>
                {unreadCount} unread
              </span>
            </div>

            <button
              type="button"
              className="admin-notification-close"
              aria-label="Close notifications"
              onClick={() => setOpen(false)}
            >
              <X size={17} />
            </button>
          </div>

          <div className="admin-notification-list">
            {error && (
              <p
                className="admin-notification-error"
                role="alert"
              >
                {error}
              </p>
            )}

            {loading && notifications.length === 0 && (
              <p className="admin-notification-empty">
                Loading notifications...
              </p>
            )}

            {!loading && notifications.length === 0 && (
              <div className="admin-notification-empty">
                <Inbox size={25} />
                <strong>You're all caught up</strong>
                <span>No notifications yet.</span>
              </div>
            )}

            {notifications.map((notification) => (
              <button
                key={notification.id}
                type="button"
                className={[
                  "admin-notification-item",
                  !notification.read_at ? "unread" : "",
                ].filter(Boolean).join(" ")}
                disabled={busyId !== null}
                onClick={() =>
                  handleNotificationClick(notification)
                }
              >
                <span className="admin-notification-item-icon">
                  {notification.read_at ? (
                    <Check size={16} />
                  ) : (
                    <Bell size={16} />
                  )}
                </span>

                <span className="admin-notification-item-body">
                  <strong>{notification.title}</strong>
                  <span>{notification.body}</span>
                  <small>
                    Ticket #{notification.ticket_id}
                  </small>
                </span>

                {!notification.read_at && (
                  <span
                    className="admin-notification-unread-dot"
                    aria-label="Unread"
                  />
                )}
              </button>
            ))}
          </div>

          <div className="admin-notification-footer">
            Updates automatically every 15 seconds
          </div>
        </div>
      )}
    </div>
  );
}
