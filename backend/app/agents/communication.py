"""
Hinglish Communication Templates with LLM Tone Polish
Handles customer outreach with compliant, contextual messaging
"""

from typing import Dict, Optional
import json


class CommunicationAgent:
    """
    Generates Hinglish communication templates for customer outreach.
    Uses slot-filled templates with LLM tone polish for natural language.
    """

    # Base templates with slots for code-injected values
    TEMPLATES = {
        "low_balance": {
            "hi": "Namaste! Aapke mandate debit ke liye balance kam hai. ₹{amount} ka payment {date} ko fail ho gaya. Please aap account mein balance add kar dein taaki next attempt successful ho.",
            "en": "Hello! Your mandate debit failed due to low balance. The ₹{amount} payment on {date} was unsuccessful. Please add funds to your account so the next attempt succeeds."
        },
        "npci_window_violation": {
            "hi": "Namaste! Aapke payment timing issue ki wajah se fail ho gaya. Hum automatically optimal time par retry kar rahe hain. Koi action ki zaroorat nahi hai.",
            "en": "Hello! Your payment failed due to timing issues. We are automatically retrying at the optimal time. No action needed from your end."
        },
        "pin_reauth_required": {
            "hi": "Namaste! ₹{amount} ka payment ke liye UPI PIN re-authentication chahiye. Please aap apne UPI app mein PIN enter karein taaki payment process ho sake.",
            "en": "Hello! The ₹{amount} payment requires UPI PIN re-authentication. Please enter your PIN in your UPI app so the payment can be processed."
        },
        "portability_breakage": {
            "hi": "Namaste! Aapke mandate portability issue ki wajah se fail ho gaya. Please aap mandate dobara register karein ya customer support se contact karein.",
            "en": "Hello! Your mandate failed due to a portability issue. Please re-register your mandate or contact customer support."
        },
        "promise_reminder": {
            "hi": "Namaste! Aapne ₹{amount} ka payment {date} tak karne ka promise kiya tha. Please ensure karein ki balance available hai.",
            "en": "Hello! You had promised to make the ₹{amount} payment by {date}. Please ensure that the balance is available."
        },
        "recovery_success": {
            "hi": "Shubh news! Aapka ₹{amount} ka payment successfully recover ho gaya hai. Thank you for your patience.",
            "en": "Good news! Your ₹{amount} payment has been successfully recovered. Thank you for your patience."
        }
    }

    def __init__(self, default_language: str = "hi"):
        """
        Initialize communication agent
        
        Args:
            default_language: Default language ("hi" for Hinglish, "en" for English)
        """
        self.default_language = default_language

    def generate_message(self, template_key: str, slots: Dict, language: Optional[str] = None) -> str:
        """
        Generate message from template with slot filling
        
        Args:
            template_key: Key to select template
            slots: Dictionary of slot values to fill
            language: Language to use ("hi" or "en")
            
        Returns:
            Generated message with slots filled
        """
        language = language or self.default_language
        
        if template_key not in self.TEMPLATES:
            raise ValueError(f"Template key '{template_key}' not found")
        
        if language not in self.TEMPLATES[template_key]:
            raise ValueError(f"Language '{language}' not available for template '{template_key}'")
        
        template = self.TEMPLATES[template_key][language]
        
        # Fill slots
        try:
            message = template.format(**slots)
        except KeyError as e:
            raise ValueError(f"Missing slot for template: {e}")
        
        return message

    def polish_with_llm(self, message: str, tone: str = "polite") -> str:
        """
        Polish message with LLM for natural tone (placeholder for actual LLM integration)
        
        Args:
            message: Base message to polish
            tone: Desired tone ("polite", "urgent", "friendly")
            
        Returns:
            Polished message
        """
        # In production, this would call an LLM API
        # For now, return the base message
        # This is a placeholder for the actual LLM integration
        
        tone_modifiers = {
            "polite": "Please ",
            "urgent": "URGENT: ",
            "friendly": "Hey! "
        }
        
        if tone in tone_modifiers:
            return tone_modifiers[tone] + message
        
        return message

    def generate_nudge(self, failure_category: str, amount: float, date: str, 
                      language: str = "hi", tone: str = "polite") -> Dict:
        """
        Generate complete nudge message
        
        Args:
            failure_category: Category of failure
            amount: Payment amount
            date: Date of payment
            language: Language for message
            tone: Tone for message
            
        Returns:
            Dictionary with generated message and metadata
        """
        # Map failure category to template key
        template_mapping = {
            "LOW_BALANCE": "low_balance",
            "NPCI_WINDOW_VIOLATION": "npci_window_violation",
            "PIN_REAUTH_REQUIRED": "pin_reauth_required",
            "PORTABILITY_BREAKAGE": "portability_breakage"
        }
        
        template_key = template_mapping.get(failure_category, "low_balance")
        
        # Generate base message
        slots = {
            "amount": f"{amount:,.0f}",
            "date": date
        }
        
        base_message = self.generate_message(template_key, slots, language)
        
        # Polish with LLM
        polished_message = self.polish_with_llm(base_message, tone)
        
        return {
            "failure_category": failure_category,
            "language": language,
            "tone": tone,
            "message": polished_message,
            "slots": slots,
            "dpdpa_consent_note": "Message sent per DPDPA consent framework"
        }

    def generate_promise_reminder(self, amount: float, promised_date: str, 
                                  language: str = "hi", tone: str = "polite") -> Dict:
        """
        Generate promise-to-pay reminder message
        
        Args:
            amount: Promised amount
            promised_date: Date payment was promised
            language: Language for message
            tone: Tone for message
            
        Returns:
            Dictionary with generated message and metadata
        """
        slots = {
            "amount": f"{amount:,.0f}",
            "date": promised_date
        }
        
        base_message = self.generate_message("promise_reminder", slots, language)
        polished_message = self.polish_with_llm(base_message, tone)
        
        return {
            "type": "promise_reminder",
            "language": language,
            "tone": tone,
            "message": polished_message,
            "slots": slots
        }

    def generate_recovery_confirmation(self, amount: float, language: str = "hi", 
                                      tone: str = "friendly") -> Dict:
        """
        Generate recovery success confirmation message
        
        Args:
            amount: Recovered amount
            language: Language for message
            tone: Tone for message
            
        Returns:
            Dictionary with generated message and metadata
        """
        slots = {
            "amount": f"{amount:,.0f}"
        }
        
        base_message = self.generate_message("recovery_success", slots, language)
        polished_message = self.polish_with_llm(base_message, tone)
        
        return {
            "type": "recovery_confirmation",
            "language": language,
            "tone": tone,
            "message": polished_message,
            "slots": slots
        }


if __name__ == "__main__":
    print("Communication Agent Module")
    print("This agent generates Hinglish communication templates with LLM tone polish.")
