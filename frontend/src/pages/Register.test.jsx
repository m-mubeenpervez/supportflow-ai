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

import Register from "./Register";
import {
  registerCustomer,
  loginCustomer,
  resendVerificationEmail,
} from "../services/api";

vi.mock("../services/api", () => ({
  registerCustomer: vi.fn(),
  loginCustomer: vi.fn(),
  resendVerificationEmail: vi.fn(),
}));

const validData = {
  name: "Test Customer",
  email: "customer@example.com",
  password: "StrongPass123!",
  confirmPassword: "StrongPass123!",
};

function setup() {
  const onLogin = vi.fn();
  const onSignIn = vi.fn();

  const view = render(
    <Register onLogin={onLogin} onSignIn={onSignIn} />
  );

  return { ...view, onLogin, onSignIn };
}

function fillForm(container, data = validData) {
  for (const [name, value] of Object.entries(data)) {
    const field = container.querySelector(
      `input[name="${name}"]`
    );

    if (!field) {
      throw new Error(`Registration field missing: ${name}`);
    }

    fireEvent.change(field, {
      target: { value },
    });
  }
}

function submitForm(container) {
  const form = container.querySelector("form");

  if (!form) {
    throw new Error("Registration form missing");
  }

  fireEvent.submit(form);
}

async function registerSuccessfully() {
  registerCustomer.mockResolvedValue({
    message: "Account created",
  });

  loginCustomer.mockResolvedValue({
    access_token: "mock-session-token",
    token_type: "bearer",
  });

  const view = setup();
  fillForm(view.container);
  submitForm(view.container);

  await screen.findByRole("heading", {
    name: /check your email/i,
  });

  return view;
}


async function registerSuccessfullyWithFakeTimers() {
  // Start fake timers BEFORE React renders and schedules
  // the first registration countdown timeout.
  vi.useFakeTimers();

  registerCustomer.mockResolvedValue({
    message: "Account created",
  });

  loginCustomer.mockResolvedValue({
    access_token: "mock-session-token",
    token_type: "bearer",
  });

  const view = setup();
  fillForm(view.container);

  // Flush registration/login promises without relying on
  // Testing Library waitFor under fake timers.
  await act(async () => {
    submitForm(view.container);
  });

  expect(
    screen.getByRole("heading", {
      name: /check your email/i,
    })
  ).toBeTruthy();

  return view;
}

describe("Register verification workflow", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("rejects invalid password without API calls", async () => {
    const view = setup();

    fillForm(view.container, {
      ...validData,
      password: "weak",
      confirmPassword: "weak",
    });

    submitForm(view.container);

    expect(registerCustomer).not.toHaveBeenCalled();

    expect(
      screen.getByText(/complete all password requirements/i)
    ).toBeTruthy();
  });

  it("shows confirmation after successful registration", async () => {
    const view = await registerSuccessfully();

    expect(registerCustomer).toHaveBeenCalledWith({
      name: validData.name,
      email: validData.email,
      password: validData.password,
    });

    expect(loginCustomer).toHaveBeenCalledWith({
      email: validData.email,
      password: validData.password,
    });

    expect(
      screen.getByText(validData.email)
    ).toBeTruthy();

    expect(view.onLogin).not.toHaveBeenCalled();

    const resend = screen.getByRole("button", {
      name: /resend available in/i,
    });

    expect(resend.disabled).toBe(true);
    expect(resendVerificationEmail).not.toHaveBeenCalled();
  });

  it("shows registration API errors without success screen", async () => {
    registerCustomer.mockRejectedValue(
      new Error("Email already registered")
    );

    const view = setup();
    fillForm(view.container);
    submitForm(view.container);

    await screen.findByText(/email already registered/i);

    expect(
      screen.queryByRole("heading", {
        name: /check your email/i,
      })
    ).toBeNull();

    expect(loginCustomer).not.toHaveBeenCalled();
    expect(view.onLogin).not.toHaveBeenCalled();
  });

  it("preserves confirmation when temporary login fails", async () => {
    registerCustomer.mockResolvedValue({
      message: "Account created",
    });

    loginCustomer.mockRejectedValue(
      new Error("Temporary login unavailable")
    );

    const view = setup();
    fillForm(view.container);
    submitForm(view.container);

    await screen.findByRole("heading", {
      name: /check your email/i,
    });

    expect(
      screen.getByText(
        /to request another link, sign in/i
      )
    ).toBeTruthy();

    expect(
      screen.getByRole("button", {
        name: /resend available in/i,
      }).disabled
    ).toBe(true);

    expect(view.onLogin).not.toHaveBeenCalled();
  });

  it("respects countdown then queues a resend", async () => {
    await registerSuccessfullyWithFakeTimers();

    for (let second = 0; second < 60; second++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }

    const resend = screen.getByRole("button", {
      name: /resend verification email/i,
    });

    expect(resend.disabled).toBe(false);

    resendVerificationEmail.mockResolvedValue({
      message: "Verification email queued",
    });

    await act(async () => {
      fireEvent.click(resend);
    });

    expect(resendVerificationEmail).toHaveBeenCalledWith(
      "mock-session-token"
    );

    expect(
      screen.getByText(/new verification request queued/i)
    ).toBeTruthy();

    expect(
      screen.getByRole("button", {
        name: /resend available in/i,
      }).disabled
    ).toBe(true);
  });

  it("displays resend API errors", async () => {
    await registerSuccessfullyWithFakeTimers();

    for (let second = 0; second < 60; second++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }

    resendVerificationEmail.mockRejectedValue(
      new Error("Service temporarily unavailable")
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", {
          name: /resend verification email/i,
        })
      );
    });

    expect(resendVerificationEmail).toHaveBeenCalledTimes(1);

    expect(
      screen.getByText(/service temporarily unavailable/i)
    ).toBeTruthy();
  });
});
