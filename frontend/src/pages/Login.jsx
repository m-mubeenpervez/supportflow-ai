
import React, { useEffect, useState } from "react";
import { Headphones, LockKeyhole, Mail, LogIn, Eye, EyeOff, } from "lucide-react";
import {
  loginCustomer,
  resendVerificationEmail,
  getCustomerVerificationStatus,
} from "../services/api";

export default function Login({ onLogin, onRegister }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendStatus, setResendStatus] = useState("");
  const [resendError, setResendError] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    if (resendCooldown <= 0) return;

    const timeout = window.setTimeout(() => {
      setResendCooldown((value) => Math.max(0, value - 1));
    }, 1000);

    return () => window.clearTimeout(timeout);
  }, [resendCooldown]);

  async function handleSubmit(event) {
    event.preventDefault();

    if (loading) return;

    setLoading(true);
    setError("");

    try {
      const result = await loginCustomer({
        email: email.trim(),
        password,
      });

      if (!result.access_token) {
        throw new Error("Authentication token was not returned.");
      }

      const verification = await getCustomerVerificationStatus(
        result.access_token
      );

      if (verification?.email_verified === false) {
        setError(
          "Email verification required. Please verify your email " +
          "before accessing chat. You can resend the verification " +
          "email using the option below."
        );
        return;
      }

      // Unknown or failed verification responses must not
      // grant access to the chat dashboard.
      if (verification?.email_verified !== true) {
        throw new Error(
          "Unable to confirm email verification. Please try again."
        );
      }

      onLogin(result.access_token);
    } catch (err) {
      setError(err.message || "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResendVerification() {
    if (resendLoading || loading || resendCooldown > 0) return;

    setResendError("");
    setResendStatus("");

    if (!email.trim() || !password) {
      setResendError("Enter your email and password first.");
      return;
    }

    setResendLoading(true);

    try {
      // Authenticate without navigating to the dashboard.
      const session = await loginCustomer({
        email: email.trim(),
        password,
      });

      if (!session.access_token) {
        throw new Error("Authentication token was not returned.");
      }

      await resendVerificationEmail(session.access_token);

      setResendStatus(
        "Verification email request queued. Check your inbox when delivery is enabled."
      );
      setResendCooldown(60);
    } catch (err) {
      setResendError(
        err.message || "Unable to request verification email."
      );
    } finally {
      setResendLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <Headphones size={28} />
          <h2>
            SupportFlow <span>AI</span>
          </h2>
        </div>

        <div className="auth-heading">
          <h1>Welcome back</h1>
          <p>Sign in to access your AI-powered support assistant.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="login-email">Email address</label>

          <div className="auth-input">
            <Mail size={18} />
            <input
              id="login-email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>

          <label htmlFor="login-password">Password</label>


          <div className="auth-input">
            <LockKeyhole size={18} />

            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              placeholder="Enter your password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />

            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword((previous) => !previous)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>


          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}

          <button
            className="auth-submit"
            type="submit"
            disabled={loading}
          >
            <LogIn size={18} />
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div style={{ marginTop: 16, textAlign: "center" }}>
          <button
            type="button"
            onClick={handleResendVerification}
            disabled={resendLoading || loading || resendCooldown > 0}
            style={{
              background: "none",
              border: "none",
              cursor: resendLoading || resendCooldown > 0
                ? "not-allowed"
                : "pointer",
              color: "inherit",
              textDecoration: "underline",
              font: "inherit",
            }}
          >
            {resendLoading
              ? "Requesting verification..."
              : resendCooldown > 0
                ? `Resend available in ${resendCooldown}s`
                : "Resend verification email"}
          </button>
        </div>

        {resendStatus && (
          <div className="auth-success" role="status">
            {resendStatus}
          </div>
        )}

        {resendError && (
          <div className="auth-error" role="alert">
            {resendError}
          </div>
        )}

        <p className="auth-footer">
          Don't have an account?{" "}
          <button type="button" onClick={onRegister}>
            Create account
          </button>
        </p>
      </div>
    </div>
  );
}
