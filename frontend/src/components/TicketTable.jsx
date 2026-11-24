import React from "react";
import { Eye, Ticket } from "lucide-react";

const TIMEZONE = "Asia/Karachi";

function displayDate(value) {
  if (!value || typeof value !== "string") return "—";
  // Backend uses datetime.now(timezone.utc); handle a driver that
  // serializes the same UTC value without an explicit offset.
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
    ? value
    : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TIMEZONE,
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

function readable(value) {
  return String(value || "—")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function TicketTable({
  tickets = [],
  selectedTicketId = null,
  onSelectTicket,
  loading = false,
}) {
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Ticket</th>
            <th scope="col">Customer</th>
            <th scope="col">Summary</th>
            <th scope="col">Intent</th>
            <th scope="col">Status</th>
            <th scope="col">Created At (PKT)</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody>
          {tickets.length === 0 ? (
            <tr>
              <td colSpan={7}>
                <div className="empty">
                  {loading ? "Loading support tickets..." : "No matching tickets found."}
                </div>
              </td>
            </tr>
          ) : tickets.map((ticket) => (
            <tr
              key={ticket.id}
              className={selectedTicketId === ticket.id ? "selected" : ""}
            >
              <td><strong>#{ticket.id}</strong></td>
              <td>#{ticket.customer_id ?? "—"}</td>
              <td>
                <strong>{ticket.summary || "Support request"}</strong>
                {ticket.order_id && <small>Order: {ticket.order_id}</small>}
              </td>
              <td>{readable(ticket.intent)}</td>
              <td>
                <span className={`pill ${ticket.status || ""}`}>
                  {readable(ticket.status)}
                </span>
              </td>
              <td><time dateTime={ticket.created_at || undefined}>{displayDate(ticket.created_at)}</time></td>
              <td>
                <button
                  type="button"
                  className="ticket-view-button"
                  onClick={() => onSelectTicket?.(ticket.id)}
                  disabled={loading}
                  aria-label={`View ticket ${ticket.id}`}
                >
                  <Eye size={15} /> View
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
