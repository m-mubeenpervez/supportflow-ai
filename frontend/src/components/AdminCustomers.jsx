import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Users,
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock3,
  ShieldCheck,
  ShieldAlert,
  Ticket,
  CalendarDays,
  SlidersHorizontal,
  RotateCcw,
  Eye,
  Trash2,
  UserRoundX,
  UserRoundCheck,
  X,
} from "lucide-react";

import {
  getAdminCustomers,
  getManagedCustomerDetails,
  setManagedCustomerStatus,
  deleteManagedCustomer,
} from "../services/api";
import "./AdminCustomers.css";

function formatRegisteredAt(value) {
  if (!value) return "Not recorded";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";

  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Karachi",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

const PAGE_SIZE = 25;

function buildFallbackDetails(customer) {
  return {
    id: customer.id,
    name: customer.name || "Unnamed Customer",
    email: customer.email || "Not recorded",
    is_verified: customer.email_verified === true,
    is_active: customer.status === "active",
    ticket_count: customer.ticket_count ?? 0,
    order_count: customer.order_count ?? 0,
    created_at: customer.created_at || null,
  };
}

function actionMeta(action) {
  switch (action) {
    case "activate":
      return {
        title: "Activate Customer",
        eyebrow: "ACCOUNT ACTION",
        icon: UserRoundCheck,
        buttonClass: "admin-action-submit",
        buttonLabel: "Activate Customer",
        helper: "Restore access for this customer account and allow sign in again.",
      };
    case "deactivate":
      return {
        title: "Deactivate Customer",
        eyebrow: "ACCOUNT ACTION",
        icon: UserRoundX,
        buttonClass: "admin-action-submit admin-action-submit-warn",
        buttonLabel: "Deactivate Customer",
        helper: "Pause access to this customer account while preserving records.",
      };
    case "delete":
    default:
      return {
        title: "Delete Customer",
        eyebrow: "ACCOUNT ACTION",
        icon: Trash2,
        buttonClass: "admin-action-submit admin-action-submit-danger",
        buttonLabel: "Delete Customer",
        helper: "Remove the customer account and erase login credentials and profile identity. Existing tickets, orders and messages remain available for support history.",
      };
  }
}

export default function AdminCustomers({ adminToken, isSuperAdmin = false }) {
  const [customers, setCustomers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [verification, setVerification] = useState("all");
  const [datePreset, setDatePreset] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [timeFrom, setTimeFrom] = useState("");
  const [timeTo, setTimeTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [selectedDetails, setSelectedDetails] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionNotice, setActionNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [customerAction, setCustomerAction] = useState(null);

  useEffect(() => {
    let active = true;

    setLoading(true);
    setError("");
    setCustomers([]);

    getAdminCustomers(adminToken, PAGE_SIZE, page * PAGE_SIZE, {
      datePreset,
      dateFrom,
      dateTo,
      timeFrom,
      timeTo,
      search,
      status,
      verification,
    })
      .then((result) => {
        if (!active) return;

        if (
          !result ||
          !Array.isArray(result.customers) ||
          !Number.isFinite(Number(result.total))
        ) {
          throw new Error("Unexpected customer response.");
        }

        setCustomers(result.customers);
        setTotal(Number(result.total));
      })
      .catch((err) => {
        if (!active) return;
        setError(err?.message || "Unable to load customers.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [
    adminToken,
    page,
    revision,
    datePreset,
    dateFrom,
    dateTo,
    timeFrom,
    timeTo,
    search,
    status,
    verification,
  ]);

  useEffect(() => {
    const modalOpen = Boolean(selectedDetails || customerAction);
    if (!modalOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleEscape(event) {
      if (event.key === "Escape" && !actionBusy) {
        setSelectedDetails(null);
        setCustomerAction(null);
      }
    }

    document.addEventListener("keydown", handleEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleEscape);
    };
  }, [selectedDetails, customerAction, actionBusy]);

  function resetDateFilters() {
    setPage(0);
    setDatePreset("all");
    setDateFrom("");
    setDateTo("");
    setTimeFrom("");
    setTimeTo("");
  }

  const refresh = useCallback(() => {
    setRevision((value) => value + 1);
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();

    return customers.filter((customer) => {
      const matchesSearch =
        !query ||
        String(customer.name || "").toLowerCase().includes(query) ||
        String(customer.email || "").toLowerCase().includes(query) ||
        String(customer.id).includes(query);

      const matchesStatus =
        status === "all" || customer.status === status;

      const matchesVerification =
        verification === "all" ||
        (verification === "verified"
          ? customer.email_verified === true
          : customer.email_verified === false);

      return matchesSearch && matchesStatus && matchesVerification;
    });
  }, [customers, search, status, verification]);

  const maxPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  const start = total ? page * PAGE_SIZE + 1 : 0;
  const end = Math.min((page + 1) * PAGE_SIZE, total);

  async function viewCustomer(id) {
    setActionError("");
    try {
      setSelectedDetails(await getManagedCustomerDetails(adminToken, id));
    } catch (err) {
      setActionError(err.message || "Unable to load customer details.");
    }
  }

  async function openCustomerAction(customer, action) {
    setActionError("");
    const fallback = buildFallbackDetails(customer);
    setCustomerAction({ action, details: fallback, reason: "" });

    try {
      const details = await getManagedCustomerDetails(adminToken, customer.id);
      setCustomerAction({ action, details, reason: "" });
    } catch {
      // Fallback row data is good enough to proceed.
    }
  }

  async function submitCustomerAction() {
    if (!customerAction || actionBusy) return;
    const reason = customerAction.reason.trim();

    if (reason.length < 5) {
      setActionError("Reason must have at least 5 characters.");
      return;
    }

    setActionBusy(true);
    setActionError("");
    setActionNotice("");

    try {
      if (customerAction.action === "delete") {
        await deleteManagedCustomer(
          adminToken,
          customerAction.details.id,
          reason
        );
      } else {
        await setManagedCustomerStatus(
          adminToken,
          customerAction.details.id,
          customerAction.action === "activate",
          reason
        );
      }

      setActionNotice(
        customerAction.action === "delete"
          ? "Customer account removed and anonymized. Support history preserved."
          : `Customer ${customerAction.action} completed.`
      );
      setSelectedDetails(null);
      setCustomerAction(null);
      setRevision((value) => value + 1);
    } catch (err) {
      setActionError(err.message || "Unable to complete customer action.");
    } finally {
      setActionBusy(false);
    }
  }

  const currentActionMeta = customerAction
    ? actionMeta(customerAction.action)
    : null;

  return (
    <section className="admin-customers" aria-label="Customer directory">
      <div className="admin-customers-heading">
        <div>
          <span className="admin-customers-eyebrow">
            CUSTOMER MANAGEMENT
          </span>
          <h3>
            <Users size={22} aria-hidden="true" />
            Registered Customers
          </h3>
          <p>
            View accounts, email verification, account status and support activity.
          </p>
        </div>

        <button
          type="button"
          className="admin-customers-toolbar-button"
          onClick={refresh}
          disabled={loading}
        >
          <RefreshCw
            size={16}
            className={loading ? "admin-customers-spin" : ""}
            aria-hidden="true"
          />
          Refresh List
        </button>
      </div>

      <div className="admin-customers-summary">
        <div>
          <Users size={19} aria-hidden="true" />
          <span>
            <strong>{total}</strong>
            <small>Total Registered</small>
          </span>
        </div>
        <div>
          <ShieldCheck size={19} aria-hidden="true" />
          <span>
            <strong>
              {customers.filter((c) => c.email_verified).length}
            </strong>
            <small>Verified on This Page</small>
          </span>
        </div>
        <div>
          <CheckCircle2 size={19} aria-hidden="true" />
          <span>
            <strong>
              {customers.filter((c) => c.status === "active").length}
            </strong>
            <small>Active on This Page</small>
          </span>
        </div>
      </div>

      <div className="admin-customers-filters">
        <label className="admin-customers-search">
          <Search size={17} aria-hidden="true" />
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setPage(0);
              setSearch(event.target.value);
            }}
            placeholder="Search name, email or ID..."
            aria-label="Search customers across all records"
          />
        </label>

        <label>
          <span>Account</span>
          <select
            value={status}
            onChange={(event) => {
              setPage(0);
              setStatus(event.target.value);
            }}
            aria-label="Filter account status"
          >
            <option value="all">All Accounts</option>
            <option value="active">Active</option>
            <option value="deactivated">Deactivated</option>
          </select>
        </label>

        <label>
          <span>Verification</span>
          <select
            value={verification}
            onChange={(event) => {
              setPage(0);
              setVerification(event.target.value);
            }}
            aria-label="Filter verification status"
          >
            <option value="all">All Verification</option>
            <option value="verified">Verified</option>
            <option value="unverified">Unverified</option>
          </select>
        </label>
      </div>

      <div className="admin-customers-advanced">
        <div className="admin-customers-advanced-heading">
          <strong>
            <SlidersHorizontal size={18} />
            Advanced Filters
          </strong>
          <small>
            Registration dates and times use Pakistan Standard Time (PKT)
          </small>
        </div>

        <div className="admin-customers-date-grid">
          <label>
            <span>
              <CalendarDays size={15} />
              Date Range
            </span>
            <select
              aria-label="Registration date range"
              value={datePreset}
              onChange={(event) => {
                setPage(0);
                setDatePreset(event.target.value);
                setDateFrom("");
                setDateTo("");
              }}
            >
              <option value="all">All Time</option>
              <option value="today">Today</option>
              <option value="7days">Last 7 Days</option>
              <option value="30days">Last 30 Days</option>
              <option value="custom">Custom Range</option>
            </select>
          </label>

          <label>
            <span>From Time (PKT)</span>
            <input
              type="time"
              value={timeFrom}
              onChange={(event) => {
                setPage(0);
                setTimeFrom(event.target.value);
              }}
            />
          </label>

          <label>
            <span>To Time (PKT)</span>
            <input
              type="time"
              value={timeTo}
              onChange={(event) => {
                setPage(0);
                setTimeTo(event.target.value);
              }}
            />
          </label>

          {datePreset === "custom" && (
            <>
              <label>
                <span>Start Date (PKT)</span>
                <input
                  type="date"
                  value={dateFrom}
                  max={dateTo || undefined}
                  onChange={(event) => {
                    setPage(0);
                    setDateFrom(event.target.value);
                  }}
                />
              </label>

              <label>
                <span>End Date (PKT)</span>
                <input
                  type="date"
                  value={dateTo}
                  min={dateFrom || undefined}
                  onChange={(event) => {
                    setPage(0);
                    setDateTo(event.target.value);
                  }}
                />
              </label>
            </>
          )}
        </div>

        <div className="admin-customers-advanced-footer">
          <span>
            {loading ? "Loading..." : `${total} matching customer(s)`}
          </span>
          <button type="button" onClick={resetDateFilters}>
            <RotateCcw size={15} />
            Reset Date Filters
          </button>
        </div>
      </div>

      <p className="admin-customers-filter-note">
        Name, email, ID, account and registration filters search the full database.
        Older registration timestamps may be unavailable.
      </p>

      {error && (
        <div className="admin-customers-error" role="alert">
          <ShieldAlert size={18} aria-hidden="true" />
          <span>{error}</span>
          <button type="button" onClick={refresh}>
            Retry
          </button>
        </div>
      )}

      {actionError && (
        <p className="staff-error" role="alert">
          {actionError}
        </p>
      )}
      {actionNotice && (
        <p className="staff-notice" role="status">
          {actionNotice}
        </p>
      )}

      <div className="admin-customers-table-wrap">
        <table className="admin-customers-table">
          <thead>
            <tr>
              <th scope="col">Customer</th>
              <th scope="col">Email Verification</th>
              <th scope="col">Account Status</th>
              <th scope="col">Tickets</th>
              <th scope="col">Registered At (PKT)</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="admin-customers-empty">
                  <RefreshCw
                    size={20}
                    className="admin-customers-spin"
                    aria-hidden="true"
                  />
                  Loading customers...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="admin-customers-empty">
                  <Users size={22} aria-hidden="true" />
                  {error
                    ? "Customer list unavailable."
                    : customers.length === 0
                      ? "No customers on this page."
                      : "No matching customers on this page."}
                </td>
              </tr>
            ) : (
              filtered.map((customer) => (
                <tr key={customer.id}>
                  <td data-label="Customer">
                    <div className="admin-customers-identity">
                      <span className="admin-customers-avatar">
                        {String(customer.name || "?")
                          .charAt(0)
                          .toUpperCase()}
                      </span>
                      <span className="admin-customers-person">
                        <strong>
                          {customer.name || "Unnamed Customer"}
                        </strong>
                        <small>{customer.email}</small>
                        <small>Customer #{customer.id}</small>
                      </span>
                    </div>
                  </td>
                  <td data-label="Email Verification">
                    <span
                      className={
                        customer.email_verified
                          ? "admin-customers-badge verified"
                          : "admin-customers-badge unverified"
                      }
                    >
                      {customer.email_verified ? (
                        <CheckCircle2 size={14} aria-hidden="true" />
                      ) : (
                        <Clock3 size={14} aria-hidden="true" />
                      )}
                      {customer.email_verified ? "Verified" : "Unverified"}
                    </span>
                  </td>
                  <td data-label="Account Status">
                    <span
                      className={
                        customer.status === "active"
                          ? "admin-customers-badge active"
                          : "admin-customers-badge deactivated"
                      }
                    >
                      {customer.status === "active"
                        ? "Active"
                        : "Deactivated"}
                    </span>
                  </td>
                  <td data-label="Tickets">
                    <span className="admin-customers-tickets">
                      <Ticket size={15} aria-hidden="true" />
                      {customer.ticket_count}
                    </span>
                  </td>
                  <td data-label="Registered At (PKT)">
                    <span className="admin-customers-created">
                      {formatRegisteredAt(customer.created_at)}
                    </span>
                  </td>
                  <td data-label="Actions">
                    <div className="admin-customer-row-actions">
                      <button
                        type="button"
                        className="admin-customer-action-button"
                        onClick={() => viewCustomer(customer.id)}
                      >
                        <Eye size={14} />
                        Details
                      </button>
                      <button
                        type="button"
                        disabled={actionBusy}
                        className="admin-customer-action-button"
                        onClick={() =>
                          openCustomerAction(
                            customer,
                            customer.status === "active"
                              ? "deactivate"
                              : "activate"
                          )
                        }
                      >
                        {customer.status === "active" ? (
                          <>
                            <UserRoundX size={14} />
                            Deactivate
                          </>
                        ) : (
                          <>
                            <UserRoundCheck size={14} />
                            Activate
                          </>
                        )}
                      </button>
                      {customer.status === "deactivated" && (
                        <button
                          type="button"
                          disabled={actionBusy}
                          className="admin-customer-action-button danger"
                          onClick={() => openCustomerAction(customer, "delete")}
                        >
                          <Trash2 size={14} />
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="admin-customers-footer">
        <span>
          {loading
            ? "Loading records..."
            : `Showing ${start}-${end} of ${total} registered customers`}
        </span>

        <div className="admin-customers-pagination">
          <button
            type="button"
            aria-label="Previous customers page"
            disabled={loading || page === 0}
            onClick={() => setPage((value) => Math.max(0, value - 1))}
          >
            <ChevronLeft size={17} />
          </button>

          <span>
            Page {page + 1} of {maxPage + 1}
          </span>

          <button
            type="button"
            aria-label="Next customers page"
            disabled={loading || page >= maxPage}
            onClick={() => setPage((value) => value + 1)}
          >
            <ChevronRight size={17} />
          </button>
        </div>
      </div>

      <p className="admin-customers-readonly">
        <ShieldCheck size={15} aria-hidden="true" />
        {isSuperAdmin
          ? "Customer account actions are audited and require a reason."
          : "Account actions are audited and require a reason."}
      </p>

      {selectedDetails && (
        <div
          className="admin-modal-backdrop"
          role="presentation"
          onClick={() => setSelectedDetails(null)}
        >
          <div
            className="admin-modal-card admin-modal-card-medium"
            role="dialog"
            aria-modal="true"
            aria-label="Customer details"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="admin-modal-header">
              <div>
                <span className="admin-modal-eyebrow">CUSTOMER DETAILS</span>
                <h3>Customer Overview</h3>
              </div>
              <button
                type="button"
                className="admin-modal-close"
                onClick={() => setSelectedDetails(null)}
                aria-label="Close customer details"
              >
                <X size={18} />
              </button>
            </div>

            <div className="admin-modal-body">
              <div className="admin-customer-profile-card">
                <div className="admin-customer-profile-main">
                  <span className="admin-customers-avatar admin-customer-profile-avatar">
                    {String(selectedDetails.name || "?")
                      .charAt(0)
                      .toUpperCase()}
                  </span>
                  <div>
                    <strong>{selectedDetails.name || "Unnamed Customer"}</strong>
                    <p>{selectedDetails.email || "No email"}</p>
                    <small>Customer #{selectedDetails.id}</small>
                  </div>
                </div>
                <div className="admin-customer-profile-tags">
                  <span className={`admin-customers-badge ${selectedDetails.is_verified ? "verified" : "unverified"}`}>
                    {selectedDetails.is_verified ? "Verified email" : "Unverified email"}
                  </span>
                  <span className={`admin-customers-badge ${selectedDetails.is_active ? "active" : "deactivated"}`}>
                    {selectedDetails.is_active ? "Currently active" : "Currently deactivated"}
                  </span>
                </div>
              </div>

              <div className="admin-customer-stats-grid">
                <div>
                  <small>Tickets</small>
                  <strong>{selectedDetails.ticket_count ?? 0}</strong>
                </div>
                <div>
                  <small>Orders</small>
                  <strong>{selectedDetails.order_count ?? 0}</strong>
                </div>
                <div>
                  <small>Registered</small>
                  <strong>{formatRegisteredAt(selectedDetails.created_at)}</strong>
                </div>
              </div>
            </div>

            <div className="admin-modal-footer">
              <button
                type="button"
                className="admin-action-secondary"
                onClick={() => setSelectedDetails(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {customerAction && currentActionMeta && (
        <div
          className="admin-modal-backdrop"
          role="presentation"
          onClick={() => {
            if (!actionBusy) setCustomerAction(null);
          }}
        >
          <div
            className="admin-modal-card admin-modal-card-medium"
            role="dialog"
            aria-modal="true"
            aria-label={currentActionMeta.title}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="admin-modal-header">
              <div className="admin-modal-header-stack">
                <div>
                  <span className="admin-modal-eyebrow">
                    {currentActionMeta.eyebrow}
                  </span>
                  <h3>{currentActionMeta.title}</h3>
                </div>
                <div className="admin-modal-icon-shell">
                  <currentActionMeta.icon size={20} />
                </div>
              </div>
              <button
                type="button"
                className="admin-modal-close"
                onClick={() => !actionBusy && setCustomerAction(null)}
                aria-label={`Close ${currentActionMeta.title}`}
              >
                <X size={18} />
              </button>
            </div>

            <div className="admin-modal-body">
              <div className="admin-customer-profile-card compact">
                <div className="admin-customer-profile-main">
                  <div>
                    <strong>{customerAction.details.name}</strong>
                    <p>{customerAction.details.email}</p>
                    <small>Customer #{customerAction.details.id}</small>
                  </div>
                </div>
              </div>

              <p className="admin-modal-helper-text">{currentActionMeta.helper}</p>
              {customerAction.action === "delete" && (
                <p className="admin-modal-helper-text" role="note">
                  This is account removal with preserved history, not deletion of linked tickets, orders or messages.
                </p>
              )}

              <div className="admin-customer-profile-tags">
                <span className={`admin-customers-badge ${customerAction.details.is_verified ? "verified" : "unverified"}`}>
                  {customerAction.details.is_verified ? "Verified email" : "Unverified email"}
                </span>
                <span className={`admin-customers-badge ${customerAction.details.is_active ? "active" : "deactivated"}`}>
                  {customerAction.details.is_active ? "Currently active" : "Currently deactivated"}
                </span>
                <span className="admin-modal-pill">{customerAction.details.ticket_count ?? 0} ticket(s)</span>
                <span className="admin-modal-pill">{customerAction.details.order_count ?? 0} order(s)</span>
              </div>

              <label className="admin-modal-form-field">
                <span>Reason</span>
                <textarea
                  rows={5}
                  value={customerAction.reason}
                  onChange={(event) =>
                    setCustomerAction((current) =>
                      current
                        ? { ...current, reason: event.target.value }
                        : current
                    )
                  }
                  placeholder={
                    customerAction.action === "delete"
                      ? "Why are you choosing to delete this customer?"
                      : `Why are you choosing to ${customerAction.action} this customer?`
                  }
                />
                <small>
                  Minimum 5 characters. This note is recorded for accountability.
                </small>
              </label>
            </div>

            <div className="admin-modal-footer">
              <button
                type="button"
                className="admin-action-secondary"
                onClick={() => !actionBusy && setCustomerAction(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className={currentActionMeta.buttonClass}
                onClick={submitCustomerAction}
                disabled={actionBusy}
              >
                {actionBusy ? "Saving..." : currentActionMeta.buttonLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
