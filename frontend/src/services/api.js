
const API_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

async function apiRequest(path, options = {}) {
  const {
    customerToken,
    adminToken,
    headers = {},
    ...fetchOptions
  } = options;

  const response = await fetch(`${API_URL}${path}`, {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      ...(customerToken
        ? { Authorization: `Bearer ${customerToken}` }
        : {}),
      ...(adminToken
        ? import.meta.env.VITE_ADMIN_AUTH_MODE === "jwt"
          ? { Authorization: `Bearer ${adminToken}` }
          : { "X-Admin-Token": adminToken }
        : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const error = await response.json();

      if (typeof error.detail === "string") {
        message = error.detail;
      } else if (Array.isArray(error.detail)) {
        message = error.detail
          .map((item) => item.msg || "Validation error")
          .join(", ");
      }
    } catch {
      // Use the default error message.
    }

    throw new Error(message);
  }

  return response.json();
}

export function registerCustomer(data) {
  return apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getCustomerAccount(customerToken) {
  return apiRequest("/auth/me", { customerToken });
}

export function changeCustomerPassword(
  customerToken,
  currentPassword,
  newPassword,
  confirmPassword
) {
  return apiRequest("/auth/change-password", {
    method: "POST",
    customerToken,
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  });
}

export function deactivateCustomerAccount(customerToken, password) {
  return apiRequest("/auth/deactivate-account", {
    method: "POST",
    customerToken,
    body: JSON.stringify({
      password,
      confirmation: "DEACTIVATE",
    }),
  });
}

export function loginCustomer(data) {
  return apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function sendChatMessage(customerToken, message, ticketId = null) {
  return apiRequest("/chat", {
    method: "POST",
    customerToken,
    body: JSON.stringify({
      message,
      ticket_id: ticketId,
    }),
  });
}

export function getTickets(adminToken) {
  return apiRequest("/tickets", {
    adminToken,
  });
}

export function getTicketMessages(adminToken, ticketId) {
  return apiRequest(`/tickets/${encodeURIComponent(ticketId)}/messages`, {
    adminToken,
  });
}

export function decideTicket(adminToken, ticketId, approve, note = "") {
  return apiRequest(
    `/tickets/${encodeURIComponent(ticketId)}/decision`,
    {
      method: "POST",
      adminToken,
      body: JSON.stringify({
        approve,
        note,
      }),
    }
  );
}



/* ==========================================================
   CUSTOMER CONVERSATION HISTORY
   ========================================================== */

/**
 * Get the authenticated customer's previous tickets.
 */
export function getCustomerTickets(customerToken) {
  return apiRequest("/customer/tickets", {
    customerToken,
  });
}

/**
 * Get messages for a ticket owned by the current customer.
 */
export function deleteCustomerTicket(customerToken, ticketId) {
  return apiRequest(
    `/customer/tickets/${encodeURIComponent(ticketId)}`,
    {
      method: "DELETE",
      customerToken,
    }
  );
}

export function getCustomerTicketMessages(
  customerToken,
  ticketId
) {
  return apiRequest(
    `/customer/tickets/${encodeURIComponent(ticketId)}/messages`,
    {
      customerToken,
    }
  );
}


// ==========================================
// NOTIFICATION API SERVICES
// ==========================================

export function getAdminNotifications(adminToken) {
  return apiRequest("/notifications/admin", {
    adminToken,
  });
}

export function markAdminNotificationRead(
  adminToken,
  notificationId
) {
  return apiRequest(
    `/notifications/admin/${encodeURIComponent(notificationId)}/read`,
    {
      method: "POST",
      adminToken,
    }
  );
}

export function getCustomerNotifications(customerToken) {
  return apiRequest("/notifications/customer", {
    customerToken,
  });
}

export function markCustomerNotificationRead(
  customerToken,
  notificationId
) {
  return apiRequest(
    `/notifications/customer/${encodeURIComponent(notificationId)}/read`,
    {
      method: "POST",
      customerToken,
    }
  );
}


// ==========================================
// EMAIL VERIFICATION
// ==========================================

/**
 * Consume a one-time email verification token.
 * The token is sent in the POST body, not the API URL.
 */
export function verifyCustomerEmail(token) {
  return apiRequest("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

/**
 * Request another verification email for a signed-in customer.
 * The backend enforces its resend cooldown.
 */
/**
 * Read email verification state using the customer's JWT.
 */
export function getCustomerVerificationStatus(customerToken) {
  return apiRequest("/auth/verification-status", {
    method: "GET",
    customerToken,
  });
}

export function resendVerificationEmail(customerToken) {
  return apiRequest("/auth/resend-verification", {
    method: "POST",
    customerToken,
  });
}

export function getAdminCustomers(
  adminToken,
  limit = 25,
  offset = 0,
  filters = {}
) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    date_preset: filters.datePreset || "all",
  });

  if (filters.datePreset === "custom") {
    if (filters.dateFrom) {
      params.set("date_from", filters.dateFrom);
    }
    if (filters.dateTo) {
      params.set("date_to", filters.dateTo);
    }
  }

  if (filters.timeFrom) {
    params.set("time_from", filters.timeFrom);
  }
  if (filters.timeTo) {
    params.set("time_to", filters.timeTo);
  }
  if (filters.search) params.set("search", filters.search);
  if (filters.status && filters.status !== "all") params.set("account_status", filters.status);
  if (filters.verification && filters.verification !== "all") params.set("verification_status", filters.verification);

  return apiRequest(`/admin/customers?${params.toString()}`, {
    adminToken,
  });
}

// Admin JWT mode: these endpoints are feature-gated on the backend.
export function loginAdmin(email, password) {
  return apiRequest("/admin/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getAdminProfile(adminToken) {
  return apiRequest("/admin/auth/me", { adminToken });
}

export function logoutAdmin(adminToken) {
  return apiRequest("/admin/auth/logout", {
    method: "POST",
    adminToken,
  });
}


// Role-checked staff management; server independently enforces permissions.
const queryString = (filters = {}) => new URLSearchParams(
  Object.entries(filters).filter(([, v]) => v !== '' && v !== null && v !== undefined)
).toString();
export function listManagedAdmins(adminToken, filters = {}) {
  return apiRequest(`/admin/management/admins?${queryString(filters)}`, {adminToken});
}
export function createManagedAdmin(adminToken, data) {
  return apiRequest('/admin/management/admins', {method:'POST', adminToken, body:JSON.stringify(data)});
}
export function setManagedAdminStatus(adminToken, id, active, reason) {
  return apiRequest(`/admin/management/admins/${encodeURIComponent(id)}/status?active=${active}`, {method:'POST', adminToken, body:JSON.stringify({reason})});
}
export function deleteManagedAdmin(adminToken, id, reason) {
  return apiRequest(`/admin/management/admins/${encodeURIComponent(id)}`, {method:'DELETE', adminToken, body:JSON.stringify({reason})});
}
export function getManagedAdminActivity(adminToken, filters = {}) {
  return apiRequest(`/admin/management/activity?${queryString(filters)}`, {adminToken});
}
export function getManagedCustomerDetails(adminToken, id) {
  return apiRequest(`/admin/management/customers/${encodeURIComponent(id)}`, {adminToken});
}
export function setManagedCustomerStatus(adminToken, id, active, reason) {
  return apiRequest(`/admin/management/customers/${encodeURIComponent(id)}/status?active=${active}`, {method:'POST', adminToken, body:JSON.stringify({reason})});
}
export function deleteManagedCustomer(adminToken, id, reason) {
  return apiRequest(`/admin/management/customers/${encodeURIComponent(id)}`, {method:'DELETE', adminToken, body:JSON.stringify({reason})});
}
