
import React, { useState } from "react";
import {
  Bot,
  Send,
  LoaderCircle,
  ShieldCheck,
  MessageSquareText,
} from "lucide-react";


// Safely render simple Markdown bold text without interpreting HTML.
function renderChatText(content) {
  const text = String(content ?? "");
  const parts = text.split(/(\*{2}[^*\r\n]+\*{2})/g);

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

export default function ChatPanel({
  messages = [],
  onSend,
  loading = false,
  ticketId = null,
  ticketStatus = "open",
}) {
  const [message, setMessage] = useState("");

  const awaitingApproval = ticketStatus === "pending_approval";
  const ticketClosed =
    ticketStatus === "approved" ||
    ticketStatus === "rejected";

  const chatDisabled = loading || awaitingApproval || ticketClosed;

  async function handleSubmit(event) {
    event.preventDefault();

    const text = message.trim();

    if (!text || text.length < 2 || chatDisabled) return;

    try {
      await onSend(text);
      setMessage("");
    } catch {
      // Parent component handles and displays API errors.
      // Keep the typed message so the user can retry.
    }
  }

  return (
    <section className="chatpanel">
      {/* Chat header */}
      <div className="paneltop">
        <div className="avatar">
          <Bot size={20} />
        </div>

        <div>
          <strong>SupportFlow AI Assistant</strong>
          <small>
            Intelligent customer support
          </small>
        </div>

        <span className="tag">
          {ticketId ? `Ticket #${ticketId}` : "New conversation"}
        </span>
      </div>

      {/* Conversation messages */}
      <div className="messages" role="log" aria-live="polite">
        {messages.length === 0 && (
          <div className="empty">
            <MessageSquareText size={32} />
            <h3>How can we help you today?</h3>
            <p>
              Ask about orders, deliveries, cancellations,
              refunds, or general support.
            </p>
          </div>
        )}

        {messages.map((item, index) => (
          <div
            key={item.id ?? index}
            className={`bubble ${
              item.role === "user" ? "user" : "assistant"
            }`}
          >
            <div className="bubblelabel">
              {item.role === "user" ? "YOU" : "SUPPORTFLOW AI"}
            </div>

            <div style={{ whiteSpace: "pre-wrap" }}>
              {renderChatText(item.content)}
            </div>
          </div>
        ))}

        {loading && (
          <div className="bubble assistant">
            <LoaderCircle
              size={18}
              className="loading-icon"
            />
            <span> Thinking...</span>
          </div>
        )}
      </div>

      {/* Approval status */}
      {awaitingApproval && (
        <div className="chat-notice">
          <ShieldCheck size={18} />
          <span>
            This request requires human approval.
            Your ticket is awaiting review.
          </span>
        </div>
      )}

      {ticketClosed && (
        <div className="chat-notice">
          <ShieldCheck size={18} />
          <span>
            This ticket is {ticketStatus}.
            Start a new conversation to continue.
          </span>
        </div>
      )}

      {/* Message composer */}
      <div className="compose">
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            value={message}
            onChange={(event) =>
              setMessage(event.target.value)
            }
            placeholder={
              chatDisabled
                ? "Conversation unavailable"
                : "Type your message..."
            }
            minLength={2}
            maxLength={3000}
            disabled={chatDisabled}
            aria-label="Message"
            required
          />

          <button
            type="submit"
            disabled={
              chatDisabled ||
              message.trim().length < 2
            }
          >
            {loading ? (
              <LoaderCircle size={17} />
            ) : (
              <Send size={17} />
            )}
            Send
          </button>
        </form>

        <p className="hint">
          AI-generated responses may require human review.
        </p>
      </div>
    </section>
  );
}
