"""
SQLAlchemy models for Reclaim database schema
"""

from sqlalchemy import Column, String, DateTime, Float, Integer, Text, Boolean, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from . import Base


class MandateStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    PAUSED = "PAUSED"


class DebitStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class FailureCategory(str, enum.Enum):
    NPCI_WINDOW_VIOLATION = "NPCI_WINDOW_VIOLATION"
    LOW_BALANCE = "LOW_BALANCE"
    PORTABILITY_BREAKAGE = "PORTABILITY_BREAKAGE"
    PRE_DEBIT_OPT_OUT = "PRE_DEBIT_OPT_OUT"
    BANK_TECHNICAL_DECLINE = "BANK_TECHNICAL_DECLINE"
    PIN_REAUTH_REQUIRED = "PIN_REAUTH_REQUIRED"


class RecoveryState(str, enum.Enum):
    FAILED = "FAILED"
    DIAGNOSED = "DIAGNOSED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    RETRYING = "RETRYING"
    RECOVERED = "RECOVERED"
    EXHAUSTED = "EXHAUSTED"
    NEEDS_USER_ACTION = "NEEDS_USER_ACTION"


class PromiseToPayStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROMISED = "PROMISED"
    CHECKED_BACK = "CHECKED_BACK"
    RECOVERED = "RECOVERED"
    ESCALATED = "ESCALATED"


class Mandate(Base):
    __tablename__ = "mandates"

    id = Column(String, primary_key=True)
    customer_vpa = Column(String, nullable=False, index=True)
    merchant_id = Column(String, nullable=False, index=True)
    bank_code = Column(String, nullable=False, index=True)
    psp_app = Column(String, nullable=False)  # GPay, PhonePe, Paytm, etc.
    amount = Column(Float, nullable=False)
    frequency = Column(String, nullable=False)  # daily, weekly, monthly, etc.
    category = Column(String, nullable=False, default="subscription")
    status = Column(SQLEnum(MandateStatus), default=MandateStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_successful_debit = Column(DateTime, nullable=True)
    pin_reauth_required = Column(Boolean, default=False)
    consent_for_outreach = Column(Boolean, default=True)
    portability_cooldown_until = Column(DateTime, nullable=True)

    # Relationships
    debit_attempts = relationship("DebitAttempt", back_populates="mandate")
    retry_recommendations = relationship("RetryRecommendation", back_populates="mandate")
    recovery_outcomes = relationship("RecoveryOutcome", back_populates="mandate", uselist=False)
    promise_to_pay = relationship("PromiseToPay", back_populates="mandate", uselist=False)


class DebitAttempt(Base):
    __tablename__ = "debit_attempts"

    id = Column(String, primary_key=True)
    mandate_id = Column(String, ForeignKey("mandates.id"), nullable=False, index=True)
    scheduled_at = Column(DateTime, nullable=False)
    executed_at = Column(DateTime, nullable=True)
    amount = Column(Float, nullable=False)
    status = Column(SQLEnum(DebitStatus), default=DebitStatus.PENDING)
    attempt_number = Column(Integer, nullable=False)  # 1 = original, 2-4 = retries
    idempotency_key = Column(String, nullable=False, unique=True)
    response_code = Column(String, nullable=True)
    response_message = Column(Text, nullable=True)

    # Relationships
    mandate = relationship("Mandate", back_populates="debit_attempts")
    failure_events = relationship("FailureEvent", back_populates="debit_attempt")


class FailureEvent(Base):
    __tablename__ = "failure_events"

    id = Column(String, primary_key=True)
    debit_attempt_id = Column(String, ForeignKey("debit_attempts.id"), nullable=False, index=True)
    category = Column(SQLEnum(FailureCategory), nullable=False)
    confidence = Column(Float, nullable=False)  # Model confidence score
    shap_explanation = Column(Text, nullable=True)  # JSON string of SHAP values
    detected_at = Column(DateTime, default=datetime.utcnow)
    raw_error_code = Column(String, nullable=True)
    context = Column(Text, nullable=True)  # Additional context

    # Relationships
    debit_attempt = relationship("DebitAttempt", back_populates="failure_events")


class RetryRecommendation(Base):
    __tablename__ = "retry_recommendations"

    id = Column(String, primary_key=True)
    mandate_id = Column(String, ForeignKey("mandates.id"), nullable=False, index=True)
    failure_event_id = Column(String, ForeignKey("failure_events.id"), nullable=True)
    recommended_at = Column(DateTime, default=datetime.utcnow)
    retry_window_start = Column(DateTime, nullable=False)
    retry_window_end = Column(DateTime, nullable=False)
    priority_score = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    complies_with_npci = Column(Boolean, default=True)
    rule_violations = Column(Text, nullable=True)  # JSON string of any violations

    # Relationships
    mandate = relationship("Mandate", back_populates="retry_recommendations")


class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"

    id = Column(String, primary_key=True)
    mandate_id = Column(String, ForeignKey("mandates.id"), nullable=False, unique=True, index=True)
    state = Column(SQLEnum(RecoveryState), default=RecoveryState.FAILED)
    recovery_attempts = Column(Integer, default=0)
    final_amount_recovered = Column(Float, nullable=True)
    final_outcome = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    mandate = relationship("Mandate", back_populates="recovery_outcomes")


class PromiseToPay(Base):
    __tablename__ = "promise_to_pay"

    id = Column(String, primary_key=True)
    mandate_id = Column(String, ForeignKey("mandates.id"), nullable=False, unique=True, index=True)
    status = Column(SQLEnum(PromiseToPayStatus), default=PromiseToPayStatus.PENDING)
    promised_amount = Column(Float, nullable=True)
    promised_date = Column(DateTime, nullable=True)
    nudge_sent_at = Column(DateTime, nullable=True)
    check_back_scheduled_at = Column(DateTime, nullable=True)
    check_back_completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    mandate = relationship("Mandate", back_populates="promise_to_pay")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True)
    mandate_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)  # CLASSIFICATION, RETRY, NUDGE, STOP, etc.
    event_data = Column(Text, nullable=True)  # JSON string of event details
    reason = Column(Text, nullable=False)
    actor = Column(String, nullable=False)  # SYSTEM, AGENT_NAME, etc.
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    compliant = Column(Boolean, default=True)
    compliance_notes = Column(Text, nullable=True)
