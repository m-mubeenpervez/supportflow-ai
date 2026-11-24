import React from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./services/api", () => ({
  loginCustomer: vi.fn(),
  getCustomerVerificationStatus: vi.fn(),
}));
vi.mock("./pages/Login", () => ({ default: () => <div>Login screen</div> }));
vi.mock("./pages/Register", () => ({ default: () => <div>Register screen</div> }));
vi.mock("./pages/VerifyEmail", () => ({ default: () => <div>Verify screen</div> }));
vi.mock("./pages/CustomerChat", () => ({ default: () => <div>Customer chat</div> }));
vi.mock("./pages/AdminDashboard", () => ({ default: () => <div>Admin dashboard</div> }));

import App from "./App";
import { getCustomerVerificationStatus } from "./services/api";

describe("authentication bootstrap", () => {
  beforeEach(() => {
    cleanup();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/");
    getCustomerVerificationStatus.mockReset();
  });

  afterEach(() => cleanup());

  it("leaves checking state after a valid verification response", async () => {
    sessionStorage.setItem(
      "supportflow_customer_session_v1",
      JSON.stringify({ token: "header.payload.signature", createdAt: Date.now() })
    );
    getCustomerVerificationStatus.mockResolvedValue({ email_verified: true });

    render(<App />);

    expect(screen.getByText("Checking your session...")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Customer chat")).toBeTruthy());
    expect(screen.queryByText("Checking your session...")).toBeNull();
  });

  it("ends bootstrap at login when no session exists", async () => {
    getCustomerVerificationStatus.mockResolvedValue({ email_verified: true });
    render(<App />);
    await waitFor(() => expect(screen.getByText("Login screen")).toBeTruthy());
    expect(getCustomerVerificationStatus).not.toHaveBeenCalled();
  });
});
