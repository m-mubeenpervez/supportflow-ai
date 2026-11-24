import React, { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import VerifyEmail from "./VerifyEmail";
import { verifyCustomerEmail } from "../services/api";

vi.mock("../services/api", () => ({
  verifyCustomerEmail: vi.fn(),
}));

describe("VerifyEmail", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows success after valid verification", async () => {
    verifyCustomerEmail.mockResolvedValue({
      message: "Email verified successfully",
    });

    render(
      <VerifyEmail
        token="valid-test-token"
        onSignIn={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          /Your email address has been verified successfully/i
        )
      ).toBeTruthy();
    });

    expect(verifyCustomerEmail).toHaveBeenCalledExactlyOnceWith(
      "valid-test-token"
    );
  });

  it("shows an error for an invalid token", async () => {
    verifyCustomerEmail.mockRejectedValue(
      new Error("Invalid or expired verification link")
    );

    render(
      <VerifyEmail
        token="invalid-test-token"
        onSignIn={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText(/verification link is invalid/i)
      ).toBeTruthy();
    });

    expect(verifyCustomerEmail).toHaveBeenCalledTimes(1);
  });

  it("does not call the API when token is missing", async () => {
    render(
      <VerifyEmail
        token={null}
        onSignIn={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText(/verification link is invalid/i)
      ).toBeTruthy();
    });

    expect(verifyCustomerEmail).not.toHaveBeenCalled();
  });

  it("avoids duplicate requests under Strict Mode", async () => {
    verifyCustomerEmail.mockResolvedValue({
      message: "Email verified successfully",
    });

    render(
      <StrictMode>
        <VerifyEmail
          token="strict-mode-test-token"
          onSignIn={vi.fn()}
        />
      </StrictMode>
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          /Your email address has been verified successfully/i
        )
      ).toBeTruthy();
    });

    expect(verifyCustomerEmail).toHaveBeenCalledTimes(1);
  });
});
