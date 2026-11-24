
import React, { useEffect, useState } from "react";
import {
  Headphones,
  UserRound,
  Mail,
  LockKeyhole,
  UserPlus,
  Eye,
  EyeOff,
  CheckCircle2,
  Circle,
} from "lucide-react";

import {
  registerCustomer,
  loginCustomer,
  resendVerificationEmail,
} from "../services/api";

export default function Register({ onLogin, onSignIn }) {
  // ==========================================
  // 01. FORM STATE
  // ==========================================

  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [registrationComplete, setRegistrationComplete] =
    useState(false);
  const [registeredEmail, setRegisteredEmail] = useState("");
  const [resendToken, setResendToken] = useState(null);
  const [resendBusy, setResendBusy] = useState(false);
  const [resendMessage, setResendMessage] = useState("");
  const [secondsRemaining, setSecondsRemaining] = useState(0);

  useEffect(() => {
    if (secondsRemaining <= 0) return;

    const timer = window.setTimeout(() => {
      setSecondsRemaining((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [secondsRemaining]);


  // Password visibility
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] =
    useState(false);

  // ==========================================
  // 02. PASSWORD VALIDATION RULES
  // ==========================================

  const passwordRules = [
    {
      label: "12 to 128 characters",
      valid:
        form.password.length >= 12 &&
        form.password.length <= 128,
    },
    {
      label: "One uppercase letter (A-Z)",
      valid: /[A-Z]/.test(form.password),
    },
    {
      label: "One lowercase letter (a-z)",
      valid: /[a-z]/.test(form.password),
    },
    {
      label: "One number (0-9)",
      valid: /[0-9]/.test(form.password),
    },
    {
      label: "One special character (!@#$)",
      valid: /[^A-Za-z0-9]/.test(form.password),
    },
  ];

  const isPasswordValid = passwordRules.every(
    (rule) => rule.valid
  );

  const passwordsMatch =
    form.confirmPassword.length > 0 &&
    form.password === form.confirmPassword;

  // ==========================================
  // 03. FORM HANDLERS
  // ==========================================

  function updateField(event) {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));

    if (error) setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (loading) return;

    setError("");
    setSuccess("");

    const name = form.name.trim();
    const email = form.email.trim();

    if (name.length < 2) {
      setError("Name must contain at least 2 characters.");
      return;
    }

    if (!isPasswordValid) {
      setError("Please complete all password requirements.");
      return;
    }

    if (!passwordsMatch) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    // Registration and verification queue are atomic on the backend.
    try {
      await registerCustomer({
        name,
        email,
        password: form.password,
      });

      // Obtain an authenticated token without navigating to chat.
      // Keep it in component memory only, for the resend API.
      let temporaryToken = null;

      try {
        const session = await loginCustomer({
          email,
          password: form.password,
        });
        temporaryToken = session.access_token || null;
      } catch {
        // Registration succeeded; sign-in can be retried separately.
      }

      setResendToken(temporaryToken);
      setRegisteredEmail(email);
      setRegistrationComplete(true);
      setSecondsRemaining(60);
      setSuccess("Account created successfully.");

      // Do not retain passwords in the registration form state.
      setForm({
        name: "",
        email: "",
        password: "",
        confirmPassword: "",
      });
    } catch (err) {
      setError(err.message || "Registration failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (!resendToken || resendBusy || secondsRemaining > 0) {
      return;
    }

    setResendBusy(true);
    setResendMessage("");

    try {
      await resendVerificationEmail(resendToken);
      setResendMessage("New verification request queued.");
      setSecondsRemaining(60);
    } catch (err) {
      const message = err.message || "Unable to request a new email.";
      setResendMessage(message);

      // Respect the backend cooldown, including on HTTP 429.
      if (/wait|429|too many/i.test(message)) {
        setSecondsRemaining(60);
      }
    } finally {
      setResendBusy(false);
    }
  }

  // ==========================================
  // 04. REGISTRATION PAGE UI
  // ==========================================

  if (registrationComplete) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-brand">
            <Headphones size={28} />
            <h2>SupportFlow <span>AI</span></h2>
          </div>

          <div className="auth-heading">
            <h1>Check your email</h1>
            <p>Your account was created successfully.</p>
          </div>

          <div className="auth-success" role="status">
            <CheckCircle2 size={20} aria-hidden="true" />
            <span>
              Verification has been queued for{" "}
              <strong>{registeredEmail}</strong>.
            </span>
          </div>

          <p>
            Open your verification link when email delivery is
            enabled. The link expires after 30 minutes.
          </p>

          {resendMessage && (
            <div role="status" aria-live="polite">
              {resendMessage}
            </div>
          )}

          <button
            type="button"
            className="auth-submit"
            onClick={handleResend}
            disabled={
              !resendToken || resendBusy || secondsRemaining > 0
            }
          >
            <Mail size={18} />
            {resendBusy
              ? "Requesting..."
              : secondsRemaining > 0
                ? `Resend available in ${secondsRemaining}s`
                : "Resend verification email"}
          </button>

          {!resendToken && (
            <p>
              To request another link, sign in to your account.
            </p>
          )}

          <p className="auth-footer">
            Already verified?{" "}
            <button type="button" onClick={onSignIn}>
              Sign in
            </button>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">

        {/* Brand */}
        <div className="auth-brand">
          <Headphones size={28} />
          <h2>
            SupportFlow <span>AI</span>
          </h2>
        </div>

        {/* Heading */}
        <div className="auth-heading">
          <h1>Create your account</h1>
          <p>
            Get started with intelligent customer support.
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>

          {/* Full name */}
          <label htmlFor="register-name">Full name</label>

          <div className="auth-input">
            <UserRound size={18} />

            <input
              id="register-name"
              name="name"
              type="text"
              placeholder="Your full name"
              autoComplete="name"
              minLength={2}
              maxLength={120}
              value={form.name}
              onChange={updateField}
              required
            />
          </div>

          {/* Email */}
          <label htmlFor="register-email">
            Email address
          </label>

          <div className="auth-input">
            <Mail size={18} />

            <input
              id="register-email"
              name="email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              value={form.email}
              onChange={updateField}
              required
            />
          </div>

          {/* Password */}
          <label htmlFor="register-password">
            Password
          </label>

          <div className="auth-input">
            <LockKeyhole size={18} />

            <input
              id="register-password"
              name="password"
              type={showPassword ? "text" : "password"}
              placeholder="Create a strong password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              value={form.password}
              onChange={updateField}
              aria-describedby="password-requirements"
              required
            />

            <button
              type="button"
              className="password-toggle"
              onClick={() =>
                setShowPassword((previous) => !previous)
              }
              aria-label={
                showPassword
                  ? "Hide password"
                  : "Show password"
              }
              aria-pressed={showPassword}
            >
              {showPassword ? (
                <EyeOff size={18} />
              ) : (
                <Eye size={18} />
              )}
            </button>
          </div>

          {/* Live password requirements */}
          <div
            id="password-requirements"
            className="password-requirements"
          >
            <p>Password must include:</p>

            {passwordRules.map((rule) => (
              <div
                key={rule.label}
                className={`password-rule ${
                  rule.valid ? "valid" : ""
                }`}
              >
                {rule.valid ? (
                  <CheckCircle2 size={15} />
                ) : (
                  <Circle size={15} />
                )}

                <span>{rule.label}</span>
              </div>
            ))}
          </div>

          {/* Confirm password */}
          <label htmlFor="register-confirm">
            Confirm password
          </label>

          <div className="auth-input">
            <LockKeyhole size={18} />

            <input
              id="register-confirm"
              name="confirmPassword"
              type={
                showConfirmPassword
                  ? "text"
                  : "password"
              }
              placeholder="Repeat your password"
              autoComplete="new-password"
              value={form.confirmPassword}
              onChange={updateField}
              required
            />

            <button
              type="button"
              className="password-toggle"
              onClick={() =>
                setShowConfirmPassword(
                  (previous) => !previous
                )
              }
              aria-label={
                showConfirmPassword
                  ? "Hide confirm password"
                  : "Show confirm password"
              }
              aria-pressed={showConfirmPassword}
            >
              {showConfirmPassword ? (
                <EyeOff size={18} />
              ) : (
                <Eye size={18} />
              )}
            </button>
          </div>

          {/* Password match feedback */}
          {form.confirmPassword.length > 0 && (
            <div
              className={`password-rule ${
                passwordsMatch ? "valid" : ""
              }`}
              aria-live="polite"
            >
              {passwordsMatch ? (
                <CheckCircle2 size={15} />
              ) : (
                <Circle size={15} />
              )}

              <span>
                {passwordsMatch
                  ? "Passwords match"
                  : "Passwords do not match"}
              </span>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}

          {/* Success message */}
          {success && (
            <div className="auth-success" role="status">
              {success}
            </div>
          )}

          {/* Submit */}
          <button
            className="auth-submit"
            type="submit"
            disabled={loading}
          >
            <UserPlus size={18} />

            {loading
              ? "Creating account..."
              : "Create account"}
          </button>
        </form>

        {/* Sign in navigation */}
        <p className="auth-footer">
          Already have an account?{" "}
          <button type="button" onClick={onSignIn}>
            Sign in
          </button>
        </p>

      </div>
    </div>
  );
}
