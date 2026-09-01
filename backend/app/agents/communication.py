"""
Generative AI Communication Agent
Generates context-aware, bilingual Hinglish customer recovery communications.
Strictly DPDPA consent-gated and checked by the Deterministic Policy Gate before dispatch.
"""

from typing import Dict, Optional, Any
import os
import json


class CommunicationAgent:
    """
    Generative AI Agent for Customer Recovery Outreach.
    Produces contextual Hinglish messaging based on diagnosed failure modes.
    """

    # Base structured templates
    TEMPLATES = {
        "LOW_BALANCE": {
            "hi": "Namaste! Aapke ₹{amount} ke subscription payment ke debit time par balance kam tha. Please aap account mein funds add kar dein taaki next eligible date par debit successfully ho sake.",
            "en": "Hello! Your ₹{amount} mandate debit could not settle due to low balance. Please ensure sufficient funds in your account for the next scheduled attempt."
        },
        "NPCI_WINDOW_VIOLATION": {
            "hi": "Namaste! Payment attempt technical timing issue ki wajah se complete nahi hua. Humne ise compliant execution window mein reschedule kar diya hai. Aapko koi action lene ki zarurat nahi hai.",
            "en": "Hello! The payment attempt failed due to execution timing windows. We have automatically rescheduled it for the next valid slot. No action needed from your side."
        },
        "PIN_REAUTH_REQUIRED": {
            "hi": "Namaste! ₹{amount} ka payment RBI guidelines ke mutabik UPI PIN re-authorization chahta hai. Please apne UPI app mein jakar payment ko approve karein: {link}",
            "en": "Hello! Per RBI guidelines, payments above ₹15,000 require UPI PIN authorization. Please approve the payment in your UPI app: {link}"
        },
        "PORTABILITY_BREAKAGE": {
            "hi": "Namaste! Aapke UPI AutoPay mandate ka app link refresh hona hai. Please is direct link par click karke mandate re-confirm karein: {link}",
            "en": "Hello! Your UPI AutoPay mandate link requires an app refresh. Please re-confirm your mandate using this secure link: {link}"
        },
        "BANK_TECHNICAL_DECLINE": {
            "hi": "Namaste! Aapka ₹{amount} ka payment bank network issue ki wajah se nahi ho paaya. Hum eligible off-peak window mein automatically retry karenge.",
            "en": "Hello! Your ₹{amount} debit encountered a temporary bank network issue. We will retry automatically during the next eligible processing window."
        }
    }

    def __init__(self, default_language: str = "hi"):
        self.default_language = default_language
        self.openai_key = os.getenv("OPENAI_API_KEY")

    def generate_personalized_nudge(
        self,
        failure_category: str,
        amount: float,
        bank_code: str,
        customer_vpa: str,
        consent_for_outreach: bool,
        action_link: Optional[str] = "https://upi.pay/m/approve",
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates personalized customer outreach.
        Returns suppression notice if DPDPA consent is False.
        """
        # Hard DPDPA Consent Check
        if not consent_for_outreach:
            return {
                "status": "SUPPRESSED_NO_CONSENT",
                "message": None,
                "reason": "Outreach suppressed per DPDPA compliance: Customer has not granted outreach consent.",
                "dpdpa_compliant": True
            }

        lang = language or self.default_language
        template_group = self.TEMPLATES.get(failure_category, self.TEMPLATES["BANK_TECHNICAL_DECLINE"])
        base_text = template_group.get(lang, template_group["hi"])

        # Slot filling
        slots = {
            "amount": f"{amount:,.0f}",
            "bank": bank_code,
            "link": action_link
        }
        filled_message = base_text.format(**slots)

        # Polish with LLM if OpenAI API Key is configured
        final_message = self._polish_with_llm(filled_message, failure_category, amount, bank_code)

        return {
            "status": "GENERATED_FOR_DISPATCH",
            "failure_category": failure_category,
            "language": lang,
            "message": final_message,
            "target_vpa": customer_vpa,
            "dpdpa_consent_verified": True,
            "policy_status": "PENDING_COMPLIANCE_GATE"
        }

    def _polish_with_llm(self, base_message: str, category: str, amount: float, bank: str) -> str:
        """Invokes LLM for natural language tone polishing if key is available"""
        if not self.openai_key:
            return base_message

        try:
            import openai
            client = openai.OpenAI(api_key=self.openai_key)
            prompt = (
                f"You are the customer recovery voice assistant for Razorpay UPI AutoPay. "
                f"Refine this customer recovery message into courteous, concise, and helpful Hinglish:\n"
                f"Context: {category} for ₹{amount:,.0f} on {bank}.\n"
                f"Base text: '{base_message}'\n"
                f"Return ONLY the refined message text in 1-2 sentences."
            )
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[CommunicationAgent] LLM polish fallback: {e}")
            return base_message
