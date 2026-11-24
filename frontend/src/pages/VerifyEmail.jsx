import React, { useEffect, useRef, useState } from "react";
import { Headphones, MailCheck, AlertCircle, LoaderCircle } from "lucide-react";
import { verifyCustomerEmail } from "../services/api";

export default function VerifyEmail({ token, onSignIn }) {
  const started = useRef(false);
  const [status, setStatus] = useState("loading");

  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;

    if (!started.current) {
      started.current = true;

      if (!token) {
        setStatus("invalid");
      } else {
        verifyCustomerEmail(token)
          .then(() => {
            if (mounted.current) {
              setStatus("success");
            }
          })
          .catch(() => {
            if (mounted.current) {
              setStatus("invalid");
            }
          });
      }
    }

    return () => {
      mounted.current = false;
    };
  }, [token]);

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <Headphones size={28} />
          <h2>SupportFlow <span>AI</span></h2>
        </div>

        <div className="auth-heading">
          <h1>Email verification</h1>
          <p>Secure account confirmation</p>
        </div>

        {status === "loading" && (
          <div className="auth-success" role="status">
            <LoaderCircle size={20} aria-hidden="true" />
            <p>Verifying your email address...</p>
          </div>
        )}

        {status === "success" && (
          <div className="auth-success" role="status">
            <MailCheck size={22} aria-hidden="true" />
            <p>Your email address has been verified successfully.</p>
          </div>
        )}

        {status === "invalid" && (
          <div className="auth-error" role="alert">
            <AlertCircle size={20} aria-hidden="true" />
            <p>
              This verification link is invalid, expired, or already used.
              Sign in to request another verification email.
            </p>
          </div>
        )}

        <button
          type="button"
          className="auth-submit"
          onClick={onSignIn}
          style={{ marginTop: 20, width: "100%" }}
        >
          Go to Sign In
        </button>
      </div>
    </div>
  );
}
