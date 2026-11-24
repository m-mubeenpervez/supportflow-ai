POLICIES = [
    ("refund", "Refunds may be requested within 14 days of delivery for damaged or incorrect products. Verify the order and issue details; supporting evidence, such as product photographs, may be requested when necessary. Eligible requests are submitted for human review, and refund execution always requires authorized human approval."),
    ("returns", "Damaged or incorrect items should be reported within 14 days. Provide the order ID and issue details; photographic evidence may be requested. Eligibility must be verified before authorization."),
    ("cancel", "Orders may be cancelled only before shipment. Shipped orders cannot be cancelled and may be directed to the returns process. Cancellation requires authentication, ownership verification and human approval."),
    ("shipping", "An exact arrival time cannot be confirmed without verified shipment information. Check the shipment status for delivery questions and escalate delayed, missing, unknown or conflicting tracking information. Order-specific information requires authentication."),
    ("payments", "No. Never share full card numbers, CVV/security codes, OTPs or passwords. Authenticate through the supported account flow. Payment support covers status, duplicate charges, billing and refund status. Suspected duplicate charges require investigation by authorized staff; disclose only verified records, never promise an immediate refund or settlement timeline, and require human approval for actual refund execution."),
    ("privacy", "Customers may access only their own account information. Never reveal another customer's orders, payment data or personal information; business tools must enforce customer-specific access."),
    ("disputes", "Disputes may cover damaged or incorrect products, delayed or missing deliveries, refunds, cancellations and billing. Authenticate, record and verify the issue, request necessary evidence, and escalate unresolved or sensitive outcomes to authorized human review."),
]


def search_policies(query: str):
    tokens = set(query.lower().split())
    ranked = sorted(
        POLICIES,
        key=lambda p: len(tokens & set((p[0] + " " + p[1]).lower().split())),
        reverse=True,
    )
    return [{"source": key, "text": text} for key, text in ranked[:3]]
