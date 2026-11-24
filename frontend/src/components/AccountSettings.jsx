import React, { useEffect, useRef, useState } from "react";
import {
  Settings, X, Mail, LockKeyhole, UserRoundX,
  ChevronRight, ArrowLeft,
  Eye, EyeOff, Check, Circle,
} from "lucide-react";

import "./AccountSettings.css";
import {
  getCustomerAccount,
  deactivateCustomerAccount,
  changeCustomerPassword,
} from "../services/api";

const fieldStyle = {
  width: "100%",
  boxSizing: "border-box",
  padding: "12px 14px",
  borderRadius: 10,
  border: "1px solid #ded7d1",
  background: "#fff",
  color: "#252326",
  fontSize: 14,
};

const actionStyle = {
  width: "100%",
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "15px 12px",
  background: "#fff",
  color: "#28252a",
  border: "1px solid #eee7df",
  borderRadius: 12,
  textAlign: "left",
  cursor: "pointer",
};


function PasswordField({
  id,
  label,
  value,
  onChange,
  disabled,
  autoComplete,
  inputRef,
  minLength,
  maxLength,
}) {
  const [visible, setVisible] = useState(false);

  return (
    <div style={{ marginTop: 18 }}>
      <label
        htmlFor={id}
        style={{
          display: "block",
          fontSize: 13,
          fontWeight: 600,
          marginBottom: 7,
        }}
      >
        {label}
      </label>

      <div style={{ position: "relative" }}>
        <input
          ref={inputRef}
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          required
          disabled={disabled}
          minLength={minLength}
          maxLength={maxLength}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          style={{
            ...fieldStyle,
            paddingRight: 52,
          }}
        />

        <button
          type="button"
          disabled={disabled}
          aria-label={visible ? `Hide ${label}` : `Show ${label}`}
          aria-pressed={visible}
          title={visible ? "Hide password" : "Show password"}
          onClick={() => setVisible((previous) => !previous)}
          style={{
            position: "absolute",
            right: 9,
            top: "50%",
            transform: "translateY(-50%)",
            display: "grid",
            placeItems: "center",
            width: 36,
            height: 36,
            border: 0,
            borderRadius: 8,
            background: "transparent",
            color: "#716b69",
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          {visible ? <EyeOff size={19} /> : <Eye size={19} />}
        </button>
      </div>
    </div>
  );
}

function PasswordRequirement({ passed, children }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        fontSize: 13,
        lineHeight: 1.6,
        color: passed ? "#28734d" : "#79716e",
      }}
    >
      {passed ? (
        <Check size={17} aria-hidden="true" />
      ) : (
        <Circle size={16} aria-hidden="true" />
      )}
      <span>{children}</span>
    </div>
  );
}

export default function AccountSettings({
  customerToken,
  onDeactivated,
  open,
  setOpen,
}) {
  const [view, setView] = useState("overview");
  const [profile, setProfile] = useState(null);
  const [profileError, setProfileError] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const passwordRules = {
    length: newPassword.length >= 12 && newPassword.length <= 128,
    uppercase: /[A-Z]/.test(newPassword),
    lowercase: /[a-z]/.test(newPassword),
    number: /[0-9]/.test(newPassword),
    special: /[!@#$]/.test(newPassword),
  };

  const passwordStrong = Object.values(passwordRules).every(Boolean);
  const passwordsMatch =
    confirmNewPassword.length > 0 &&
    newPassword === confirmNewPassword;

  const dialogRef = useRef(null);
  const triggerRef = useRef(null);
  const passwordRef = useRef(null);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;

    setProfile(null);
    setProfileError("");

    getCustomerAccount(customerToken)
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .catch(() => {
        if (!cancelled) {
          setProfileError("Unable to load account information.");
        }
      });

    return () => { cancelled = true; };
  }, [open, customerToken]);

  useEffect(() => {
    if (open && view === "deactivate") {
      passwordRef.current?.focus();
    }
  }, [open, view]);

  function resetForm() {
    setPassword("");
    setConfirmation("");
    setCurrentPassword("");
    setNewPassword("");
    setConfirmNewPassword("");
    setError("");
  }

  function closeModal() {
    if (busy) return;
    resetForm();
    setView("overview");
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  }

  function handleKeys(event) {
    if (busy) return;

    if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
      return;
    }

    if (event.key !== "Tab") return;

    const controls = Array.from(
      dialogRef.current?.querySelectorAll(
        'button:not([disabled]), input:not([disabled])'
      ) || []
    );

    if (!controls.length) return;

    const first = controls[0];
    const last = controls[controls.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (
      !event.shiftKey && document.activeElement === last
    ) {
      event.preventDefault();
      first.focus();
    }
  }

  async function submitPasswordChange(event) {
    event.preventDefault();

    if (busy) return;

    if (newPassword.length < 12 || newPassword.length > 128) {
      setError("New password must contain 12 to 128 characters.");
      return;
    }

    if (!passwordStrong) {
      setError("Please complete all password requirements.");
      return;
    }

    if (newPassword !== confirmNewPassword) {
      setError("New passwords do not match.");
      return;
    }

    if (!currentPassword || newPassword === currentPassword) {
      setError("New password must be different.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      const result = await changeCustomerPassword(
        customerToken,
        currentPassword,
        newPassword,
        confirmNewPassword
      );

      if (result?.password_changed !== true) {
        throw new Error("Password update was not confirmed.");
      }

      resetForm();

      // Existing logout clears the saved customer session.
      onDeactivated();
    } catch (err) {
      setError(err.message || "Unable to change password.");
    } finally {
      setBusy(false);
    }
  }

  async function submitDeactivation(event) {
    event.preventDefault();

    if (busy || !password || confirmation !== "DEACTIVATE") {
      return;
    }

    setBusy(true);
    setError("");

    try {
      const result = await deactivateCustomerAccount(
        customerToken,
        password
      );

      if (result?.deactivated !== true) {
        throw new Error("Deactivation was not confirmed.");
      }

      resetForm();
      onDeactivated();
    } catch (err) {
      setError(err.message || "Unable to deactivate account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => {
          setView("overview");
          setOpen(true);
        }}
        title="Account settings"
        aria-label="Account settings"
        style={{
          width: 44,
          height: 44,
          flexShrink: 0,
          display: "grid",
          placeItems: "center",
          borderRadius: 14,
          border: "1px solid #e2e6ed",
          background: "#fff",
          color: "#35333a",
          cursor: "pointer",
        }}
      >
        <Settings size={19} />
      </button>

      {open && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 10000,
            background: "rgba(12,12,16,.70)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
            boxSizing: "border-box",
          }}
        >
          <section
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="account-settings-title"
            onKeyDown={handleKeys}
            style={{
              width: "100%",
              maxWidth: 460,
              maxHeight: "calc(100dvh - 32px)",
              overflow: "hidden",
              boxSizing: "border-box",
              padding: 8,
              borderRadius: 20,
              background: "#fffdfb",
              color: "#252326",
              boxShadow: "0 24px 80px rgba(0,0,0,.25)",
            }}
          >
            <div className="account-settings-scroll-content">
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 18,
              }}
            >
              <div
                style={{
                  width: 46,
                  height: 46,
                  display: "grid",
                  placeItems: "center",
                  borderRadius: 14,
                  background: "#f7eee7",
                  color: "#a76c49",
                }}
              >
                <Settings size={23} />
              </div>

              <button
                type="button"
                aria-label="Close account settings"
                disabled={busy}
                onClick={closeModal}
                style={{
                  border: 0,
                  background: "transparent",
                  cursor: "pointer",
                  color: "#615b61",
                }}
              >
                <X size={21} />
              </button>
            </div>

            {view === "overview" ? (
              <>
                <h2
                  id="account-settings-title"
                  style={{ margin: "0 0 8px", fontSize: 24 }}
                >
                  Account Settings
                </h2>
                <p style={{
                  color: "#777077",
                  fontSize: 14,
                  marginBottom: 20,
                }}>
                  Manage your SupportFlow AI account.
                </p>

                <div style={{
                  padding: 16,
                  background: "#f7f2ec",
                  border: "1px solid #e9dfd3",
                  borderRadius: 12,
                  marginBottom: 18,
                }}>
                  <div style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontWeight: 600,
                    marginBottom: 8,
                    fontSize: 14,
                  }}>
                    <Mail size={17} />
                    Registered Email
                  </div>
                  <div style={{
                    fontSize: 14,
                    overflowWrap: "anywhere",
                  }}>
                    {profile?.email ||
                      (profileError || "Loading email...")}
                  </div>
                  {profile?.email_verified && (
                    <div style={{
                      fontSize: 12,
                      color: "#337554",
                      marginTop: 8,
                    }}>
                      Verified account
                    </div>
                  )}
                </div>

                <div style={{ display: "grid", gap: 10 }}>
                  <button
                    type="button"
                    onClick={() => {
                      resetForm();
                      setView("password");
                    }}
                    style={actionStyle}
                  >
                    <LockKeyhole size={19} />
                    <span style={{ flex: 1 }}>
                      <strong>Change Password</strong>
                      <span style={{
                        display: "block",
                        fontSize: 12,
                        color: "#777077",
                        marginTop: 4,
                      }}>
                        Update your account password securely
                      </span>
                    </span>
                    <ChevronRight size={18} />
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      resetForm();
                      setView("deactivate");
                    }}
                    style={actionStyle}
                  >
                    <UserRoundX size={19} color="#a64436" />
                    <span style={{ flex: 1 }}>
                      <strong>Deactivate Account</strong>
                      <span style={{
                        display: "block",
                        fontSize: 12,
                        color: "#777077",
                        marginTop: 4,
                      }}>
                        Disable sign-in access
                      </span>
                    </span>
                    <ChevronRight size={18} />
                  </button>
                </div>
              </>
            ) : view === "password" ? (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    resetForm();
                    setView("overview");
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    background: "transparent",
                    border: 0,
                    cursor: "pointer",
                    marginBottom: 15,
                    color: "#69636a",
                  }}
                >
                  <ArrowLeft size={17} /> Back to Settings
                </button>

                <h2
                  id="account-settings-title"
                  style={{ fontSize: 23, margin: "0 0 12px" }}
                >
                  Change Password
                </h2>

                <p style={{
                  fontSize: 14,
                  lineHeight: 1.7,
                  color: "#69636a",
                }}>
                  Choose a new password with at least 12 characters.
                  After updating, you will need to sign in again.
                  All previous customer sessions will be invalidated.
                </p>

                <form onSubmit={submitPasswordChange}>
                  <PasswordField
                    id="change-current-password"
                    label="Current Password"
                    value={currentPassword}
                    onChange={setCurrentPassword}
                    autoComplete="current-password"
                    disabled={busy}
                  />

                  <PasswordField
                    id="change-new-password"
                    label="New Password"
                    value={newPassword}
                    onChange={setNewPassword}
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    disabled={busy}
                  />

                  <div
                    aria-label="Password requirements"
                    style={{
                      border: "1px solid #e8dfd5",
                      borderRadius: 12,
                      background: "#faf7f3",
                      padding: 16,
                      marginTop: 14,
                      display: "grid",
                      gap: 8,
                    }}
                  >
                    <strong
                      style={{
                        fontSize: 13,
                        marginBottom: 4,
                      }}
                    >
                      Password must include:
                    </strong>

                    <PasswordRequirement passed={passwordRules.length}>
                      12 to 128 characters
                    </PasswordRequirement>

                    <PasswordRequirement passed={passwordRules.uppercase}>
                      One uppercase letter (A-Z)
                    </PasswordRequirement>

                    <PasswordRequirement passed={passwordRules.lowercase}>
                      One lowercase letter (a-z)
                    </PasswordRequirement>

                    <PasswordRequirement passed={passwordRules.number}>
                      One number (0-9)
                    </PasswordRequirement>

                    <PasswordRequirement passed={passwordRules.special}>
                      One special character (!@#$)
                    </PasswordRequirement>
                  </div>

                  <PasswordField
                    id="change-confirm-password"
                    label="Confirm New Password"
                    value={confirmNewPassword}
                    onChange={setConfirmNewPassword}
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    disabled={busy}
                  />

                  {confirmNewPassword.length > 0 && (
                    <div
                      role="status"
                      aria-live="polite"
                      style={{
                        marginTop: 9,
                        display: "flex",
                        alignItems: "center",
                        gap: 7,
                        fontSize: 13,
                        color: passwordsMatch ? "#28734d" : "#a64436",
                      }}
                    >
                      {passwordsMatch ? (
                        <Check size={16} aria-hidden="true" />
                      ) : (
                        <Circle size={15} aria-hidden="true" />
                      )}
                      {passwordsMatch
                        ? "Passwords match"
                        : "Passwords do not match"}
                    </div>
                  )}

                  {error && (
                    <p
                      role="alert"
                      style={{
                        color: "#a64436",
                        fontSize: 13,
                        lineHeight: 1.5,
                        marginTop: 14,
                      }}
                    >
                      {error}
                    </p>
                  )}

                  <div
                    className="account-password-actions"
                    style={{
                      display: "flex",
                      justifyContent: "flex-end",
                      flexWrap: "wrap",
                      gap: 10,
                      marginTop: 24,
                    }}
                  >
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        resetForm();
                        setView("overview");
                      }}
                      style={{
                        padding: "12px 18px",
                        border: "1px solid #ded7d1",
                        borderRadius: 10,
                        background: "#fff",
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>

                    <button
                      type="submit"
                      disabled={
                        busy ||
                        !currentPassword ||
                        !passwordStrong ||
                        !passwordsMatch ||
                        newPassword === currentPassword
                      }
                      style={{
                        padding: "12px 18px",
                        border: 0,
                        borderRadius: 10,
                        background: "#a76c49",
                        color: "#fff",
                        fontWeight: 600,
                        cursor: "pointer",
                        opacity:
                          busy ||
                          !currentPassword ||
                          !passwordStrong ||
                          !passwordsMatch ||
                          newPassword === currentPassword
                            ? 0.55 : 1,
                      }}
                    >
                      {busy ? "Updating..." : "Update Password"}
                    </button>
                  </div>
                </form>
              </>
            ) : (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    resetForm();
                    setView("overview");
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    background: "transparent",
                    border: 0,
                    cursor: "pointer",
                    marginBottom: 15,
                    color: "#69636a",
                  }}
                >
                  <ArrowLeft size={17} /> Back to Settings
                </button>

                <h2
                  id="account-settings-title"
                  style={{ fontSize: 23, margin: "0 0 12px" }}
                >
                  Deactivate Account
                </h2>

                <p style={{
                  fontSize: 14,
                  lineHeight: 1.7,
                  color: "#69636a",
                }}>
                  This disables your account and future sign-ins.
                  Support and audit records may be retained.
                  This is not permanent data erasure.
                </p>

                <form onSubmit={submitDeactivation}>
                  <PasswordField
                    id="deactivate-password"
                    label="Confirm your password"
                    value={password}
                    onChange={setPassword}
                    autoComplete="current-password"
                    inputRef={passwordRef}
                    disabled={busy}
                  />

                  <label
                    htmlFor="deactivate-confirmation"
                    style={{
                      display: "block",
                      fontSize: 13,
                      fontWeight: 600,
                      margin: "18px 0 7px",
                    }}
                  >
                    Type DEACTIVATE to confirm
                  </label>

                  <input
                    id="deactivate-confirmation"
                    type="text"
                    required
                    disabled={busy}
                    autoComplete="off"
                    spellCheck={false}
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                    placeholder="DEACTIVATE"
                    style={fieldStyle}
                  />

                  {error && (
                    <p role="alert" style={{
                      color: "#a64436",
                      fontSize: 13,
                    }}>
                      {error}
                    </p>
                  )}

                  <div style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    gap: 10,
                    flexWrap: "wrap",
                    marginTop: 24,
                  }}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        resetForm();
                        setView("overview");
                      }}
                      style={{
                        padding: "12px 18px",
                        border: "1px solid #ded7d1",
                        borderRadius: 10,
                        background: "#fff",
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>

                    <button
                      type="submit"
                      disabled={
                        busy ||
                        !password ||
                        confirmation !== "DEACTIVATE"
                      }
                      style={{
                        padding: "12px 18px",
                        border: 0,
                        borderRadius: 10,
                        background: "#a64436",
                        color: "#fff",
                        fontWeight: 600,
                        cursor: "pointer",
                        opacity:
                          busy ||
                          !password ||
                          confirmation !== "DEACTIVATE"
                            ? 0.55 : 1,
                      }}
                    >
                      {busy ? "Deactivating..." : "Deactivate Account"}
                    </button>
                  </div>
                </form>
              </>
            )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
