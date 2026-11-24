import React from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import Login from "./Login";
import {
  loginCustomer,
  resendVerificationEmail,
  getCustomerVerificationStatus,
} from "../services/api";

vi.mock("../services/api", () => ({
  loginCustomer: vi.fn(),
  resendVerificationEmail: vi.fn(),
  getCustomerVerificationStatus: vi.fn(),
}));

const credentials = {
  email: "customer@example.com",
  password: "StrongPass123!",
};

function setup() {
  const onLogin = vi.fn();
  const onRegister = vi.fn();

  const view = render(
    <Login
      onLogin={onLogin}
      onRegister={onRegister}
    />
  );

  return { ...view, onLogin, onRegister };
}

function fillCredentials() {
  fireEvent.change(
    screen.getByLabelText(/email address/i),
    { target: { value: credentials.email } }
  );

  fireEvent.change(
    screen.getByLabelText(/^password$/i),
    { target: { value: credentials.password } }
  );
}

function resendButton() {
  return screen.getByRole("button", {
    name: /resend verification email/i,
  });
}

async function clickResend() {
  await act(async () => {
    fireEvent.click(resendButton());
  });
}

describe("Login and email verification resend", () => {
  beforeEach(() => {
    vi.resetAllMocks();

    // Existing normal-login tests represent verified customers.
    getCustomerVerificationStatus.mockResolvedValue({
      email_verified: true,
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("blocks unverified customers from opening chat", async () => {
    loginCustomer.mockResolvedValue({
      access_token: "unverified-customer-token",
    });

    getCustomerVerificationStatus.mockResolvedValue({
      email_verified: false,
    });

    const view = setup();
    fillCredentials();

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", {
          name: /^sign in$/i,
        })
      );
    });

    expect(getCustomerVerificationStatus).toHaveBeenCalledWith(
      "unverified-customer-token"
    );

    expect(view.onLogin).not.toHaveBeenCalled();

    expect(
      screen.getByRole("alert").textContent
    ).toMatch(/email verification required/i);

    expect(resendButton()).toBeTruthy();
  });

  it("does not open chat when verification status fails", async () => {
    loginCustomer.mockResolvedValue({
      access_token: "status-check-token",
    });

    getCustomerVerificationStatus.mockRejectedValue(
      new Error("Verification status unavailable")
    );

    const view = setup();
    fillCredentials();

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", {
          name: /^sign in$/i,
        })
      );
    });

    expect(view.onLogin).not.toHaveBeenCalled();

    expect(
      screen.getByRole("alert").textContent
    ).toMatch(/verification status unavailable/i);
  });

  it("preserves normal customer login", async () => {
    loginCustomer.mockResolvedValue({
      access_token: "normal-login-token",
      token_type: "bearer",
    });

    const view = setup();
    fillCredentials();

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", {
          name: /^sign in$/i,
        })
      );
    });

    expect(loginCustomer).toHaveBeenCalledWith(credentials);
    expect(view.onLogin).toHaveBeenCalledWith(
      "normal-login-token"
    );

    expect(getCustomerVerificationStatus).toHaveBeenCalledWith(
      "normal-login-token"
    );
    expect(resendVerificationEmail).not.toHaveBeenCalled();
  });

  it("rejects resend without email and password", async () => {
    setup();

    await clickResend();

    expect(
      screen.getByText(
        /enter your email and password first/i
      )
    ).toBeTruthy();

    expect(loginCustomer).not.toHaveBeenCalled();
    expect(resendVerificationEmail).not.toHaveBeenCalled();
  });

  it("displays incorrect credentials error", async () => {
    loginCustomer.mockRejectedValue(
      new Error("Invalid email or password")
    );

    const view = setup();
    fillCredentials();

    await clickResend();

    expect(
      screen.getByText(/invalid email or password/i)
    ).toBeTruthy();

    expect(resendVerificationEmail).not.toHaveBeenCalled();
    expect(view.onLogin).not.toHaveBeenCalled();
  });

  it("requests verification without opening dashboard", async () => {
    loginCustomer.mockResolvedValue({
      access_token: "resend-session-token",
      token_type: "bearer",
    });

    resendVerificationEmail.mockResolvedValue({
      message: "Verification email queued",
    });

    const view = setup();
    fillCredentials();

    await clickResend();

    expect(loginCustomer).toHaveBeenCalledWith(credentials);

    expect(resendVerificationEmail).toHaveBeenCalledWith(
      "resend-session-token"
    );

    expect(
      screen.getByText(/verification email request queued/i)
    ).toBeTruthy();

    expect(view.onLogin).not.toHaveBeenCalled();

    expect(
      screen.getByRole("button", {
        name: /resend available in 60s/i,
      }).disabled
    ).toBe(true);
  });

  it("shows resend API errors", async () => {
    loginCustomer.mockResolvedValue({
      access_token: "resend-session-token",
    });

    resendVerificationEmail.mockRejectedValue(
      new Error("Verification cooldown active")
    );

    const view = setup();
    fillCredentials();

    await clickResend();

    expect(
      screen.getByText(/verification cooldown active/i)
    ).toBeTruthy();

    expect(view.onLogin).not.toHaveBeenCalled();
    expect(resendVerificationEmail).toHaveBeenCalledTimes(1);
  });

  it("re-enables resend after the 60-second countdown", async () => {
    // Fake timers must start before React schedules
    // the first countdown timeout.
    vi.useFakeTimers();

    loginCustomer.mockResolvedValue({
      access_token: "resend-session-token",
    });

    resendVerificationEmail.mockResolvedValue({
      message: "Verification email queued",
    });

    const view = setup();
    fillCredentials();

    await clickResend();

    expect(
      screen.getByRole("button", {
        name: /resend available in 60s/i,
      }).disabled
    ).toBe(true);

    for (let second = 0; second < 59; second++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }

    expect(resendVerificationEmail).toHaveBeenCalledTimes(1);

    expect(
      screen.getByRole("button", {
        name: /resend available in 1s/i,
      }).disabled
    ).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(resendButton().disabled).toBe(false);
    expect(view.onLogin).not.toHaveBeenCalled();
  });
});
