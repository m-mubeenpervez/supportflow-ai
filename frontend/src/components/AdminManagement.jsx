import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Users,
  Plus,
  Search,
  RefreshCw,
  ShieldCheck,
  Activity,
  Eye,
  EyeOff,
  X,
  LockKeyhole,
  UserCog,
  UserRoundCheck,
  UserRoundX,
  Trash2,
  RotateCcw,
} from "lucide-react";
import {
  listManagedAdmins,
  createManagedAdmin,
  setManagedAdminStatus,
  deleteManagedAdmin,
  getManagedAdminActivity,
} from "../services/api";
import "./AdminManagement.css";

const PAGE_SIZE = 25;

const pakistanTime = (date) =>
  date
    ? new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Karachi",
      }).format(new Date(date))
    : "—";

function getPasswordChecks(password) {
  return {
    length: password.length >= 12 && password.length <= 72,
    uppercase: /[A-Z]/.test(password),
    lowercase: /[a-z]/.test(password),
    number: /\d/.test(password),
    special: /[^A-Za-z0-9]/.test(password),
  };
}

function adminActionMeta(action) {
  switch (action) {
    case "activate":
      return {
        title: "Activate Support Administrator",
        eyebrow: "STAFF ACTION",
        icon: UserRoundCheck,
        helper:
          "Restore admin access so this staff member can sign in and resume managed support operations.",
        confirmLabel: "Activate Administrator",
        buttonClass: "staff-primary-button",
      };
    case "deactivate":
      return {
        title: "Deactivate Support Administrator",
        eyebrow: "STAFF ACTION",
        icon: UserRoundX,
        helper:
          "Temporarily stop this staff member from signing in while keeping the account and activity history.",
        confirmLabel: "Deactivate Administrator",
        buttonClass: "staff-secondary-danger",
      };
    case "delete":
    default:
      return {
        title: "Delete Support Administrator",
        eyebrow: "STAFF ACTION",
        icon: Trash2,
        helper:
          "Permanently remove this deactivated staff account. This action should be used only when the account is no longer needed.",
        confirmLabel: "Delete Administrator",
        buttonClass: "staff-danger-button",
      };
  }
}

export default function AdminManagement({ adminToken }) {
  const [admins, setAdmins] = useState([]);
  const [activity, setActivity] = useState([]);
  const [total, setTotal] = useState(0);
  const [activityTotal, setActivityTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [activityAdmin, setActivityAdmin] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showCreate, setShowCreate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const [createConfirmOpen, setCreateConfirmOpen] = useState(false);
  const [actionModal, setActionModal] = useState(null);

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    Promise.all([
      listManagedAdmins(adminToken, {
        search,
        status,
        date_from: from,
        date_to: to,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
      getManagedAdminActivity(adminToken, {
        admin_id: activityAdmin,
        date_from: from,
        date_to: to,
        limit: 50,
      }),
    ])
      .then(([adminResult, events]) => {
        if (!mounted) return;
        setAdmins(adminResult.admins || []);
        setTotal(adminResult.total || 0);
        setActivity(events.events || []);
        setActivityTotal(events.total || 0);
        setError("");
      })
      .catch((err) => {
        if (mounted) {
          setError(err.message || "Unable to load administrators.");
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [adminToken, search, status, from, to, page, activityAdmin, revision]);

  useEffect(() => {
    const modalOpen = createConfirmOpen || Boolean(actionModal);
    if (!modalOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onEscape(event) {
      if (event.key === "Escape" && !busy) {
        setCreateConfirmOpen(false);
        setActionModal(null);
      }
    }

    document.addEventListener("keydown", onEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onEscape);
    };
  }, [createConfirmOpen, actionModal, busy]);

  const passwordChecks = useMemo(() => getPasswordChecks(password), [password]);
  const passwordValid = Object.values(passwordChecks).every(Boolean);
  const maxPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const actionMeta = actionModal ? adminActionMeta(actionModal.action) : null;

  function resetFilters() {
    setSearch("");
    setStatus("all");
    setFrom("");
    setTo("");
    setPage(0);
  }

  function requestCreate(event) {
    event.preventDefault();
    if (busy) return;

    if (!email.trim()) {
      setError("Administrator email is required.");
      return;
    }

    if (!passwordValid) {
      setError("Please satisfy all password guidelines before creating the administrator.");
      return;
    }

    setError("");
    setNotice("");
    setCreateConfirmOpen(true);
  }

  async function createAdministrator() {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      await createManagedAdmin(adminToken, {
        email: email.trim(),
        password,
      });
      setEmail("");
      setPassword("");
      setShowPassword(false);
      setCreateConfirmOpen(false);
      setShowCreate(false);
      setNotice("Support administrator created.");
      refresh();
    } catch (err) {
      setError(err.message || "Unable to create administrator.");
    } finally {
      setBusy(false);
    }
  }

  function openActionModal(action, admin) {
    setError("");
    setNotice("");
    setActionModal({ action, admin, reason: "" });
  }

  async function performAction() {
    if (!actionModal || busy) return;
    const reason = actionModal.reason.trim();

    if (reason.length < 5) {
      setError("Reason must be at least 5 characters.");
      return;
    }

    setBusy(true);
    setError("");
    setNotice("");

    try {
      if (actionModal.action === "delete") {
        await deleteManagedAdmin(
          adminToken,
          actionModal.admin.id,
          reason
        );
      } else {
        await setManagedAdminStatus(
          adminToken,
          actionModal.admin.id,
          actionModal.action === "activate",
          reason
        );
      }

      setNotice(`Administrator ${actionModal.action} completed.`);
      setActionModal(null);
      refresh();
    } catch (err) {
      setError(err.message || "Unable to complete administrator action.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="staff-manage" aria-label="Support administrator management">
      <div className="staff-section-header">
        <div>
          <span className="eyebrow">ROLE-BASED ACCESS</span>
          <h2>
            <Users size={22} />
            Support Administrators
          </h2>
          <p>
            Manage internal staff accounts, access status and recorded activity.
          </p>
        </div>
        <div className="staff-toolbar-actions">
          <button
            type="button"
            className="staff-toolbar-button"
            onClick={refresh}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <button
            type="button"
            className="staff-toolbar-button"
            onClick={() => setShowCreate((value) => !value)}
          >
            <Plus size={16} />
            {showCreate ? "Hide Form" : "New Administrator"}
          </button>
        </div>
      </div>

      {error && (
        <p className="staff-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="staff-notice" role="status">
          {notice}
        </p>
      )}

      {showCreate && (
        <form onSubmit={requestCreate} className="staff-create-form">
          <div className="staff-create-header">
            <div>
              <span className="eyebrow">STAFF PROVISIONING</span>
              <h3>Create a Support Administrator</h3>
              <p>
                Create a staff account that can work in the Admin Workspace through
                the same Admin Access login.
              </p>
            </div>
            <div className="staff-create-header-icon">
              <LockKeyhole size={20} />
            </div>
          </div>

          <div className="staff-form-row staff-form-row-wide">
            <label>
              <span>Administrator email</span>
              <input
                type="email"
                required
                maxLength={255}
                autoComplete="off"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@example.com"
              />
            </label>

            <label className="staff-password-field">
              <span>Temporary password</span>
              <div className="staff-password-input-wrap">
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={12}
                  maxLength={72}
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Create a secure temporary password"
                />
                <button
                  type="button"
                  className="staff-password-toggle"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>
          </div>

          <div className="staff-guidelines">
            <strong>Password guidelines</strong>
            <ul>
              <li className={passwordChecks.length ? "met" : ""}>12 to 72 characters</li>
              <li className={passwordChecks.uppercase ? "met" : ""}>At least one uppercase letter</li>
              <li className={passwordChecks.lowercase ? "met" : ""}>At least one lowercase letter</li>
              <li className={passwordChecks.number ? "met" : ""}>At least one number</li>
              <li className={passwordChecks.special ? "met" : ""}>At least one special character</li>
            </ul>
          </div>

          <div className="staff-create-actions">
            <button type="submit" className="staff-primary-button" disabled={busy}>
              Create Support Administrator
            </button>
          </div>
        </form>
      )}

      <div className="staff-filter-panel">
        <div className="staff-filter-grid">
          <label className="staff-search-field">
            <span>Search email</span>
            <div className="staff-search-input-wrap">
              <Search size={15} />
              <input
                aria-label="Search admin email"
                value={search}
                onChange={(event) => {
                  setPage(0);
                  setSearch(event.target.value);
                }}
                placeholder="Email address..."
              />
            </div>
          </label>
          <label>
            <span>Status</span>
            <select
              value={status}
              onChange={(event) => {
                setPage(0);
                setStatus(event.target.value);
              }}
            >
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
          <label>
            <span>From date (PKT)</span>
            <input
              type="date"
              value={from}
              max={to || undefined}
              onChange={(event) => {
                setPage(0);
                setFrom(event.target.value);
              }}
            />
          </label>
          <label>
            <span>To date (PKT)</span>
            <input
              type="date"
              value={to}
              min={from || undefined}
              onChange={(event) => {
                setPage(0);
                setTo(event.target.value);
              }}
            />
          </label>
          <button type="button" className="staff-reset-button" onClick={resetFilters}>
            <RotateCcw size={15} />
            Reset Filters
          </button>
        </div>
      </div>

      <div className="staff-table-wrap">
        <table className="staff-table">
          <thead>
            <tr>
              <th>Administrator</th>
              <th>Role</th>
              <th>Status</th>
              <th>Created (PKT)</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {admins.map((admin) => (
              <tr key={admin.id}>
                <td>
                  <strong>{admin.email}</strong>
                  <small>Administrator #{admin.id}</small>
                </td>
                <td>Support Administrator</td>
                <td>
                  <span className={admin.is_active ? "staff-badge active" : "staff-badge inactive"}>
                    {admin.is_active ? "Active" : "Deactivated"}
                  </span>
                </td>
                <td>{pakistanTime(admin.created_at)}</td>
                <td>
                  <div className="staff-row-actions">
                    <button
                      type="button"
                      className="staff-row-button"
                      disabled={busy}
                      onClick={() => {
                        setActivityAdmin(String(admin.id));
                        document
                          .getElementById("admin-activity-section")
                          ?.scrollIntoView({ behavior: "smooth" });
                      }}
                    >
                      View Work
                    </button>
                    <button
                      type="button"
                      className="staff-row-button"
                      disabled={busy}
                      onClick={() =>
                        openActionModal(
                          admin.is_active ? "deactivate" : "activate",
                          admin
                        )
                      }
                    >
                      {admin.is_active ? "Deactivate" : "Activate"}
                    </button>
                    {!admin.is_active && (
                      <button
                        type="button"
                        className="staff-row-button danger"
                        disabled={busy}
                        onClick={() => openActionModal("delete", admin)}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && admins.length === 0 && (
              <tr>
                <td colSpan={5} className="staff-empty">
                  No administrators match your filters.
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={5} className="staff-empty">
                  Loading administrators...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="staff-pagination">
        <span>
          Showing {admins.length} of {total} administrators
        </span>
        <div>
          <button disabled={page === 0} onClick={() => setPage((value) => value - 1)}>
            Previous
          </button>
          <span>Page {page + 1} of {maxPage + 1}</span>
          <button
            disabled={(page + 1) * PAGE_SIZE >= total}
            onClick={() => setPage((value) => value + 1)}
          >
            Next
          </button>
        </div>
      </div>

      <div className="staff-section-header" id="admin-activity-section">
        <div>
          <span className="eyebrow">ACCOUNTABILITY</span>
          <h2>
            <Activity size={22} />
            Administrator Activity
          </h2>
          <p>
            Review approval decisions and account-management operations performed by staff.
          </p>
        </div>
        <ShieldCheck size={24} />
      </div>

      <label className="staff-activity-select">
        <span>Activity by staff member</span>
        <select
          value={activityAdmin}
          onChange={(event) => setActivityAdmin(event.target.value)}
        >
          <option value="">All administrators</option>
          {admins.map((admin) => (
            <option key={admin.id} value={String(admin.id)}>
              {admin.email}
            </option>
          ))}
        </select>
      </label>

      <div className="staff-table-wrap">
        <table className="staff-table">
          <thead>
            <tr>
              <th>When (PKT)</th>
              <th>Administrator</th>
              <th>Action</th>
              <th>Target</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {activity.map((item) => (
              <tr key={item.id}>
                <td>{pakistanTime(item.created_at)}</td>
                <td>{item.actor_email}</td>
                <td>{item.action.replaceAll("_", " ")}</td>
                <td>
                  {item.entity_type} #{item.entity_id}
                </td>
                <td>{item.description}</td>
              </tr>
            ))}
            {!activity.length && (
              <tr>
                <td colSpan={5} className="staff-empty">
                  No recorded activity for these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="staff-muted">
        Latest {activity.length} of {activityTotal} recorded events. Historical
        actions from before this patch cannot be reconstructed.
      </p>

      {createConfirmOpen && (
        <div
          className="staff-modal-backdrop"
          role="presentation"
          onClick={() => {
            if (!busy) setCreateConfirmOpen(false);
          }}
        >
          <div
            className="staff-modal-card"
            role="dialog"
            aria-modal="true"
            aria-label="Create support administrator"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="staff-modal-header">
              <div className="staff-modal-title-stack">
                <div>
                  <span className="eyebrow">STAFF ACTION</span>
                  <h3>Create Support Administrator</h3>
                </div>
                <div className="staff-modal-icon-shell">
                  <UserCog size={20} />
                </div>
              </div>
              <button
                type="button"
                className="staff-modal-close"
                onClick={() => !busy && setCreateConfirmOpen(false)}
                aria-label="Close create administrator confirmation"
              >
                <X size={18} />
              </button>
            </div>
            <div className="staff-modal-body">
              <div className="staff-modal-account-card">
                <strong>{email.trim()}</strong>
                <p>This account will be created as a Support Administrator.</p>
              </div>
              <p className="staff-modal-helper">
                The temporary password meets the current security rules and is not
                stored in the browser after creation.
              </p>
            </div>
            <div className="staff-modal-footer">
              <button
                type="button"
                className="staff-toolbar-button"
                onClick={() => !busy && setCreateConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="staff-primary-button"
                onClick={createAdministrator}
                disabled={busy}
              >
                {busy ? "Creating..." : "Create Administrator"}
              </button>
            </div>
          </div>
        </div>
      )}

      {actionModal && actionMeta && (
        <div
          className="staff-modal-backdrop"
          role="presentation"
          onClick={() => {
            if (!busy) setActionModal(null);
          }}
        >
          <div
            className="staff-modal-card"
            role="dialog"
            aria-modal="true"
            aria-label={actionMeta.title}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="staff-modal-header">
              <div className="staff-modal-title-stack">
                <div>
                  <span className="eyebrow">{actionMeta.eyebrow}</span>
                  <h3>{actionMeta.title}</h3>
                </div>
                <div className="staff-modal-icon-shell">
                  <actionMeta.icon size={20} />
                </div>
              </div>
              <button
                type="button"
                className="staff-modal-close"
                onClick={() => !busy && setActionModal(null)}
                aria-label={`Close ${actionMeta.title}`}
              >
                <X size={18} />
              </button>
            </div>
            <div className="staff-modal-body">
              <div className="staff-modal-account-card">
                <strong>{actionModal.admin.email}</strong>
                <p>Administrator #{actionModal.admin.id}</p>
                <span className={actionModal.admin.is_active ? "staff-badge active" : "staff-badge inactive"}>
                  {actionModal.admin.is_active ? "Currently active" : "Currently deactivated"}
                </span>
              </div>
              <p className="staff-modal-helper">{actionMeta.helper}</p>
              <label className="staff-modal-field">
                <span>Reason</span>
                <textarea
                  rows={5}
                  value={actionModal.reason}
                  onChange={(event) =>
                    setActionModal((current) =>
                      current
                        ? { ...current, reason: event.target.value }
                        : current
                    )
                  }
                  placeholder={`Why are you choosing to ${actionModal.action} this administrator?`}
                />
                <small>Minimum 5 characters. This note is recorded for accountability.</small>
              </label>
            </div>
            <div className="staff-modal-footer">
              <button
                type="button"
                className="staff-toolbar-button"
                onClick={() => !busy && setActionModal(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className={actionMeta.buttonClass}
                onClick={performAction}
                disabled={busy}
              >
                {busy ? "Saving..." : actionMeta.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
